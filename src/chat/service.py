"""Pipeline `jawab()`: penjaga pra-LLM -> prompt fail-closed -> layanan -> penjaga pasca-LLM.

`model`, `putaran_alat`, dan `peringatan` sengaja masuk ke dalam `DataJawaban`
(bagian `data`), BUKAN ke `meta` amplop -- `src.models.Meta` mewajibkan
`total`/`hal`/`batas`, ketiganya milik paginasi, dan PRD bagian 6 menyatakan
`meta` hanya terisi pada respons berpaginasi. Chat tidak berpaginasi sama
sekali, jadi menumpangkannya di `Meta` akan memaksa field paginasi palsu.
"""

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.chat.constants import (
    AMBANG_BLOKIR,
    ANGKA_TANPA_ASAL,
    BOCOR_PROMPT,
    MARKUP_DIBUANG,
    REFUSAL_BAKU,
    SUSPEK_INJEKSI,
    SUSPEK_INJEKSI_ALAT,
)
from src.chat.guardrails import (
    angka_berasal,
    angka_dalam_teks,
    bocor_prompt,
    buang_markup,
    buang_tak_terlihat,
    deteksi_injeksi,
)
from src.chat.llm import LayananAI
from src.chat.schemas import DataJawaban, JejakFungsi, PermintaanChat
from src.chat.tools import KonteksAlat
from src.config import Pengaturan
from src.exceptions import GALAT_SERVER, GalatAPI

logger = logging.getLogger(__name__)

# Absolut relatif berkas ini, BUKAN direktori kerja -- prompt hilang senyap
# saat proses dijalankan dari direktori lain.
_DIR_PROMPT = Path(__file__).parent / "prompt"
_POLA_PLACEHOLDER = re.compile(r"\{\{[A-Z_]+\}\}")


def _bersihkan_nilai(nilai: Any) -> Any:
    """Bersihkan satu nilai `jejak_fungsi.argumen` rekursif, dengan pembersih
    KELUARAN yang sama dipakai `jawaban`.

    `argumen` adalah keluaran model yang SAMA dengan `jawaban`, dikirim ke
    klien yang SAMA -- `_argumen_sah` (`src/chat/tools.py`) cuma membatasi
    BENTUK argumen (mis. panjang `cari_desa.nama` 2-100 karakter), isinya
    bebas, jadi batas kepercayaannya wajib konsisten dengan alasan
    `buang_markup` ada: model yang diarahkan penyerang bisa memanggil
    `cari_desa(nama="<img src=x onerror=...>")` dan markup itu utuh sampai ke
    klien lewat `jejak_fungsi` walau `jawaban` sudah bersih.

    Dict/list disalin BARU dengan nilai anak yang sudah dibersihkan
    (immutability ECC) -- TIDAK memutasi `argumen` asli. `hasil_mentah` (di
    `jawab()` di bawah) SENGAJA tidak lewat sini: angka di dalamnya adalah
    kontrak `angka_berasal`.
    """
    if isinstance(nilai, str):
        # Urutan WAJIB `buang_tak_terlihat` DULU lalu `buang_markup` -- sama
        # seperti jalur `jawaban` (jebakan T3: tanpa `buang_tak_terlihat`
        # dulu, payload berisi zero-width space di sela karakter lolos
        # utuh). BUKAN `normalisasi_masukan` -- ia merapatkan `\s{2,}`
        # termasuk baris baru.
        return buang_markup(buang_tak_terlihat(nilai))[0]
    if isinstance(nilai, dict):
        return {kunci: _bersihkan_nilai(v) for kunci, v in nilai.items()}
    if isinstance(nilai, list):
        return [_bersihkan_nilai(v) for v in nilai]
    return nilai


@lru_cache(maxsize=4)
def muat_prompt(nama: str = "asisten.md") -> tuple[str, str]:
    """Muat system prompt fail-closed: gagal apa pun -> `GalatAPI` 500, tak pernah kosong.

    Kembalikan `(prompt_jadi, instruksi_mentah)`. `instruksi_mentah` adalah
    template SETELAH `{{REFUSAL}}` diganti tapi SEBELUM `{{METODOLOGI}}`
    disisipkan -- itulah yang dipakai `bocor_prompt`. Ini sudah dibuktikan
    empiris, bukan kehati-hatian teoretis: prompt jadi (`asisten.md` +
    `metodologi.md` disisipkan) berukuran 10.850 karakter, dan bila
    `bocor_prompt` diberi prompt JADI, baris metodologi yang sah (mis. baris
    berisi "20.000 token). Keenam berkas itu tetap sumber kebenarannya...")
    dituduh sebagai kebocoran dan jawaban sah diganti frasa penolakan. Bila
    diberi template MENTAH (nilai kembalian kedua di sini), baris metodologi
    tidak ikut dianggap kebocoran.
    """
    try:
        instruksi_mentah = (_DIR_PROMPT / nama).read_text(encoding="utf-8")
        metodologi = (_DIR_PROMPT / "metodologi.md").read_text(encoding="utf-8")
    except OSError as exc:
        # Sengaja TIDAK memakai kode galat yang menyebut "prompt" -- PRD
        # bagian 6 mewajibkan 5xx tanpa bocoran detail internal. Penyebab
        # sebenarnya masuk log, tidak pernah ke pemanggil.
        logger.exception("berkas prompt Asisten Desa tidak terbaca")
        raise GalatAPI(GALAT_SERVER, "terjadi galat pada server", 500) from exc

    # Ganti SEBELUM dipakai `bocor_prompt` -- REFUSAL_BAKU bukan bagian yang
    # perlu dilindungi dari kebocoran, ia sudah publik.
    instruksi_mentah = instruksi_mentah.replace("{{REFUSAL}}", REFUSAL_BAKU)
    isi = instruksi_mentah.replace("{{METODOLOGI}}", metodologi)

    if _POLA_PLACEHOLDER.search(isi):
        # Fail-closed: prompt separuh terisi lebih berbahaya daripada tidak
        # menjawab sama sekali.
        logger.error("placeholder prompt Asisten Desa belum terisi")
        raise GalatAPI(GALAT_SERVER, "terjadi galat pada server", 500)

    return isi, instruksi_mentah


async def jawab(
    permintaan: PermintaanChat,
    layanan: LayananAI,
    konteks: KonteksAlat,
    pengaturan: Pengaturan,
    nama_prompt: str = "asisten.md",
) -> DataJawaban:
    """Jalankan satu giliran Asisten Desa: penjaga pra-LLM, layanan, penjaga pasca-LLM."""
    prompt, instruksi_mentah = muat_prompt(nama_prompt)

    # Pra-LLM: filter injeksi deterministik, murah, tanpa kuota. SELURUH
    # pesan klien dipindai -- bukan hanya `role: "user"` -- karena chat ini
    # STATELESS: seluruh riwayat percakapan dikirim ULANG oleh klien tiap
    # permintaan, jadi giliran ber-`role: "model"` pun 100% dikendalikan
    # pemanggil. Riwayat yang dikirim klien tidak pernah menjadi bukti bahwa
    # model benar-benar pernah mengatakannya -- payload injeksi yang
    # disisipkan lewat giliran "model" (dialog palsu few-shot) sama
    # berbahayanya dengan giliran "user".
    # Digabung SEKALI, supaya payload yang disebar antar pesan tetap
    # terlihat DAN supaya kata sehari-hari yang sah ("abaikan", "instruksi")
    # tertahan di 1 poin untuk seluruh percakapan alih-alih terakumulasi per
    # pesan sampai ambang blokir (false refusal).
    # Isi MENTAH yang diteruskan: `deteksi_injeksi` menormalisasi sendiri,
    # tapi butuh spasi asli untuk mendeteksi varian huruf-renggang Best-of-N.
    gabungan_klien = "\n".join(p.isi for p in permintaan.messages)
    skor_total, alasan_total = deteksi_injeksi(gabungan_klien)

    if skor_total >= AMBANG_BLOKIR:
        # Layanan (LLM) TIDAK dipanggil sama sekali -- serangan terang
        # berbiaya nol kuota Gemini.
        logger.warning("injeksi terdeteksi (skor %s): %s", skor_total, alasan_total)
        return DataJawaban(
            jawaban=REFUSAL_BAKU,
            jejak_fungsi=[],
            model="",
            putaran_alat=0,
            peringatan=[SUSPEK_INJEKSI],
        )

    peringatan: list[str] = []
    if skor_total == 1:
        # Skor 1 hanya ditandai; memblokir di 1 berarti false refusal untuk
        # percakapan sah.
        logger.warning("suspek injeksi ringan (skor %s): %s", skor_total, alasan_total)
        peringatan.append(SUSPEK_INJEKSI)

    # Tidak ada `clamp_suhu` -- rentang suhu sudah ditegakkan
    # `Field(ge=0.0, le=1.0)` di `PermintaanChat`.
    hasil = await layanan.jawab(
        permintaan.messages, prompt, permintaan.temperature, konteks
    )
    peringatan += hasil.peringatan
    teks = hasil.teks

    # Pasca-LLM: karakter tak terlihat (zero-width space dkk.) dibuang DULU,
    # lalu markup, supaya kebocoran yang disisipi tag ("Kamu adalah
    # <b>Asisten Desa</b>, ...") ATAU zero-width space di sela karakter tetap
    # tertangkap setelah keduanya lenyap; urutan sebaliknya meloloskan baris
    # prompt utuh ke pengguna. Bocor mengganti SELURUH teks -- bocor selalu
    # salah.
    # PENTING: bukan `normalisasi_masukan` -- fungsi itu juga merapatkan
    # `\s{2,}` termasuk baris baru dan merusak markdown jawaban (dua baris
    # baru jadi satu spasi). `buang_tak_terlihat` hanya membuang karakter
    # tak terlihat, tidak menyentuh spasi/baris baru biasa.
    teks_bersih, dibuang = buang_markup(buang_tak_terlihat(teks))
    if bocor_prompt(teks_bersih, instruksi_mentah):
        logger.warning("kebocoran system prompt terdeteksi di jawaban")
        teks = REFUSAL_BAKU
        peringatan.append(BOCOR_PROMPT)
    else:
        teks = teks_bersih
        if dibuang:
            logger.warning("markup eksfiltrasi dibuang dari jawaban")
            peringatan.append(MARKUP_DIBUANG)

    # Angka definisional dari system prompt (metodologi) adalah sumber SAH,
    # bukan halusinasi; halusinasi skor per desa tetap tertangkap karena
    # tidak ada di prompt. Dicek terhadap teks AKHIR yang benar-benar
    # dikirim. MENANDAI, tidak memblokir -- kebijakan blokir menunggu data
    # harness.
    tanpa_asal = angka_berasal(
        teks, hasil.hasil_mentah, sumber_tambahan=angka_dalam_teks(prompt)
    )
    if tanpa_asal:
        # Daftar angkanya hanya ke LOG, tidak pernah ke pemanggil -- penjaga
        # lain di fungsi ini semua mencatat lewat `logger.warning`, ini
        # dulu tidak, jadi peringatan ANGKA_TANPA_ASAL tidak bisa
        # didiagnosis dari log (LOW-2).
        logger.warning("angka tanpa asal di jawaban: %s", tanpa_asal)
        peringatan.append(ANGKA_TANPA_ASAL)

    # Hasil alat adalah konten eksternal (OWASP) -- dipindai sebagai sinyal
    # injeksi tidak langsung, TIDAK dimutasi, karena angka di dalamnya
    # adalah kontrak untuk pencocokan angka-vs-jejak di atas. Alat
    # `berita_desa` menyajikan teks hasil scraping situs luar, jadi jalur
    # ini nyata terpakai.
    hasil_mentah_teks = json.dumps(hasil.hasil_mentah, ensure_ascii=False, default=str)
    skor_alat, alasan_alat = deteksi_injeksi(hasil_mentah_teks)
    if skor_alat >= AMBANG_BLOKIR:
        logger.warning(
            "suspek injeksi pada hasil alat (skor %s): %s", skor_alat, alasan_alat
        )
        peringatan.append(SUSPEK_INJEKSI_ALAT)

    # `jejak_fungsi.argumen` adalah keluaran model yang SAMA dengan
    # `jawaban`, dikirim ke klien yang SAMA, jadi lewat pembersih yang sama
    # (M2) -- `hasil.hasil_mentah` TETAP tidak disentuh/dimutasi di sini,
    # karena angka di dalamnya adalah kontrak `angka_berasal` di atas.
    # Objek `JejakFungsi` BARU dirakit (bukan memutasi `j.argumen` in-place)
    # supaya tetap immutable (ECC).
    jejak_bersih = [
        JejakFungsi(
            fungsi=j.fungsi, argumen=_bersihkan_nilai(j.argumen), status=j.status
        )
        for j in hasil.jejak
    ]
    if any(
        jb.argumen != j.argumen for jb, j in zip(jejak_bersih, hasil.jejak, strict=True)
    ):
        logger.warning(
            "markup atau karakter tak terlihat dibuang dari argumen jejak_fungsi"
        )

    return DataJawaban(
        jawaban=teks,
        jejak_fungsi=jejak_bersih,
        model=hasil.model,
        putaran_alat=hasil.putaran,
        peringatan=peringatan,
    )
