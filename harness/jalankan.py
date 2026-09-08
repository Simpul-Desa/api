"""Runner harness: kasus YAML -> POST /api/chat in-process -> penilai -> (hakim) -> laporan.

Kenapa rel pengaman kuota di berkas ini ada: satu giliran chat bisa memakai
sampai 6 panggilan Gemini (`chat_maks_putaran_alat` = 5 putaran alat + 1
panggilan penutup tanpa tools saat putaran habis, lihat
`src/chat/llm.py::LayananGemini._jawab_satu_model`). 51 kasus
(`harness/kasus/*.yaml`) dijalankan tanpa batas berarti kira-kira
51 * 6 = 306 panggilan Gemini -- sekitar 30% kuota harian free tier --
habis dalam SATU perintah salah ketik. Rel di bawah (penomoran mengikuti
Task 11 di `.claude/PRPs/plans/fase-5-asisten-desa.plan.md`) membuat
harness ini tetap berguna tanpa bisa menghabiskan kuota secara tidak
sengaja:

- R2 bawaan KERING: tanpa `--sungguhan`, runner memuat kasus, memvalidasi
  skemanya, mencetak ringkasan, lalu keluar. NOL jaringan, NOL kuota,
  aplikasi FastAPI tidak dibangun sama sekali.
- R3 anggaran keras: `--maks-panggilan` (bawaan 60) menjumlahkan
  `data["putaran_alat"]` tiap kasus dan BERHENTI begitu anggaran tercapai;
  nilai `putaran_alat` kini mencerminkan CACAH PANGGILAN Gemini nyata
  (termasuk panggilan penutup saat putaran alat habis, lihat
  `src/chat/llm.py::LayananGemini._jawab_satu_model`), bukan `maks` semata;
  laporan parsial tetap ditulis dan menyebut berapa kasus tidak dijalankan.
- R4 hakim opt-in: bawaan TIDAK memakai hakim LLM; hanya `--hakim`
  menyalakannya (panggilan Gemini TAMBAHAN per kasus abu-abu).
- R5 contoh, bukan semua: `--contoh` (bawaan 8) mengambil kasus pertama
  tiap kategori secara DETERMINISTIK (rata per kategori); `--semua`
  menjalankan seluruh 51 kasus; `--kategori X` membatasi ke satu kategori
  dan mengabaikan `--contoh`.
- R6 model termurah: bawaan `pengaturan.model_chat_cadangan`
  (`gemini-flash-lite-latest`), ditimpa via `--model`.
- R7 serial + jeda: satu kasus pada satu waktu, jeda `--jeda` (bawaan 4.0)
  detik antar kasus, retry pada status 429/502/503 sebanyak 3 kali dengan
  backoff `10 * percobaan` detik.
- R8 tanpa server, tanpa Supabase: aplikasi dijalankan in-process lewat
  `httpx.ASGITransport`, peran dependensi dan klien Supabase ditimpa
  dengan tiruan -- harness tidak pernah menyentuh basis data produksi.
- R9 kunci wajib eksplisit: `--sungguhan` tanpa `GEMINI_API_KEY_CHAT`
  terisi gagal cepat (keluar kode 2) SEBELUM kasus pertama dijalankan,
  bukan 51 kegagalan berturut-turut.

Pakai: `../.venv/bin/python -m harness.jalankan --help`
"""

import argparse
import asyncio
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml
from httpx import ASGITransport

from harness.hakim import hakimi
from harness.penilai import Putusan, nilai
from src.config import Pengaturan, ambil_pengaturan

# `create_app`, `wajib_di_atas_tamu`, dan `Identitas` SENGAJA diimpor LOKAL
# di dalam `_jalankan_sungguhan`, bukan di sini -- `src.main` membangun
# `app = create_app()` di level modul (dipakai `uvicorn src.main:app`), jadi
# impor eager akan membangun aplikasi FastAPI utuh bahkan pada jalur kering
# (R2 mewajibkan "aplikasi tidak dibangun" tanpa `--sungguhan`).

_DIR_KASUS = Path(__file__).parent / "kasus"
_DIR_LAPORAN = Path(__file__).parent / "laporan"
_DIR_PROMPT = Path(__file__).parent.parent / "src" / "chat" / "prompt"
_MAKS_ULANG = 3
_STATUS_ULANG = {429, 502, 503}
_PERAN_SAH = frozenset({"user", "model"})


@dataclass
class HasilKasus:
    kasus: dict[str, Any]
    putusan: Putusan
    jawaban: str = ""
    jejak: list[dict[str, Any]] | None = None
    lewat_hakim: bool = False
    putaran_alat: int = 0


def muat_kasus(kategori: str | None) -> list[dict[str, Any]]:
    """Muat kasus dari `harness/kasus/*.yaml`, difilter per nama berkas bila `kategori` diisi."""
    kasus: list[dict[str, Any]] = []
    for berkas in sorted(_DIR_KASUS.glob("*.yaml")):
        if kategori and berkas.stem != kategori:
            continue
        kasus.extend(yaml.safe_load(berkas.read_text(encoding="utf-8")))
    return kasus


def pilih_kasus(semua: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Ambil contoh DETERMINISTIK untuk R5: `ceil(n / jumlah_kategori)` kasus
    pertama dari tiap kategori, distribusi rata.

    Bukan potongan N pertama dari daftar gabungan -- kalau begitu, kategori
    yang kebetulan di awal abjad ("angka") memonopoli seluruh contoh.
    """
    per_kategori: dict[str, list[dict[str, Any]]] = {}
    for k in semua:
        per_kategori.setdefault(k["kategori"], []).append(k)
    per_kat = math.ceil(n / len(per_kategori)) if per_kategori else 0
    dipilih: list[dict[str, Any]] = []
    for kategori in sorted(per_kategori):
        dipilih.extend(per_kategori[kategori][:per_kat])
    return dipilih


def _validasi_skema(kasus_list: list[dict[str, Any]]) -> list[str]:
    """Validasi bentuk minimal tiap kasus (R2) -- dijalankan di jalur kering MAUPUN sungguhan."""
    masalah: list[str] = []
    for kasus in kasus_list:
        id_kasus = kasus.get("id", "?")
        for kunci in ("id", "kategori", "percakapan"):
            if kunci not in kasus:
                masalah.append(f"{id_kasus}: field '{kunci}' hilang")
        for p in kasus.get("percakapan") or []:
            if "role" not in p or "isi" not in p:
                masalah.append(f"{id_kasus}: percakapan tanpa 'role'/'isi'")
            elif p["role"] not in _PERAN_SAH:
                masalah.append(f"{id_kasus}: role tidak dikenal {p['role']!r}")
    return masalah


def _cetak_ringkasan_kering(dipilih: list[dict[str, Any]]) -> None:
    per_kategori: dict[str, int] = {}
    for k in dipilih:
        per_kategori[k["kategori"]] = per_kategori.get(k["kategori"], 0) + 1
    print(
        f"kering (dry-run): {len(dipilih)} kasus dipilih, skema sah, "
        "0 panggilan jaringan, 0 kuota dipakai."
    )
    for kategori, n in sorted(per_kategori.items()):
        print(f"  {kategori}: {n}")


async def _panggil_chat(
    klien: httpx.AsyncClient, kasus: dict[str, Any]
) -> dict[str, Any]:
    """POST /api/chat dengan retry pada 429/502/503, backoff `10 * percobaan` detik (R7)."""
    payload = {
        "messages": [{"role": p["role"], "isi": p["isi"]} for p in kasus["percakapan"]]
    }
    for percobaan in range(1, _MAKS_ULANG + 1):
        respons = await klien.post("/api/chat", json=payload, timeout=180.0)
        if respons.status_code not in _STATUS_ULANG or percobaan == _MAKS_ULANG:
            hasil: dict[str, Any] = respons.json()
            return hasil
        await asyncio.sleep(10.0 * percobaan)
    raise AssertionError("tak terjangkau")  # tak tercapai, memuaskan mypy


async def _nilai_kasus(
    klien: httpx.AsyncClient,
    kasus: dict[str, Any],
    pakai_hakim: bool,
    pengaturan: Pengaturan,
) -> HasilKasus:
    body = await _panggil_chat(klien, kasus)
    if not body.get("sukses"):
        galat = (body.get("galat") or {}).get("kode", "?")
        return HasilKasus(
            kasus, Putusan(lulus=False, alasan=f"permintaan gagal: {galat}")
        )
    data = body["data"]
    # `peringatan` dibaca dari `data`, BUKAN `meta` -- lihat docstring
    # harness/penilai.py: `meta` chat selalu null, jejak dan peringatan
    # tinggal di dalam `data` (kontrak `DataJawaban`).
    putusan = nilai(kasus, data["jawaban"], data["jejak_fungsi"], data["peringatan"])
    lewat_hakim = False
    if putusan.abu_abu and pakai_hakim:
        putusan = await hakimi(kasus, data["jawaban"], pengaturan)
        lewat_hakim = True
    return HasilKasus(
        kasus=kasus,
        putusan=putusan,
        jawaban=data["jawaban"],
        jejak=data["jejak_fungsi"],
        lewat_hakim=lewat_hakim,
        putaran_alat=data["putaran_alat"],
    )


def _tulis_laporan(
    hasil: list[HasilKasus],
    nama_prompt: str,
    model: str,
    total_dipilih: int,
    pemakaian: int,
    anggaran: int,
    pakai_hakim: bool,
) -> Path:
    stempel = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tujuan = _DIR_LAPORAN / f"{stempel}-{Path(nama_prompt).stem}.md"
    terlewat = total_dipilih - len(hasil)
    baris = [
        f"# Laporan harness — {stempel}",
        "",
        (
            f"Prompt: `{nama_prompt}` · model: `{model}` · "
            f"kasus: {len(hasil)}/{total_dipilih} · "
            f"panggilan: {pemakaian}/{anggaran} · "
            f"hakim: {'aktif' if pakai_hakim else 'nonaktif'}"
        ),
        "",
    ]
    if terlewat > 0:
        baris += [
            (
                f"> PERINGATAN: anggaran panggilan tercapai -- {terlewat} dari "
                f"{total_dipilih} kasus TIDAK dijalankan. Cakupan laporan ini PARSIAL."
            ),
            "",
        ]
    baris += ["| kategori | lulus | gagal |", "|---|---|---|"]
    per_kategori: dict[str, list[HasilKasus]] = {}
    for h in hasil:
        per_kategori.setdefault(h.kasus["kategori"], []).append(h)
    for kategori, daftar in sorted(per_kategori.items()):
        lulus = sum(1 for h in daftar if h.putusan.lulus)
        baris.append(f"| {kategori} | {lulus} | {len(daftar) - lulus} |")
    gagal = [h for h in hasil if not h.putusan.lulus]
    if gagal:
        baris += ["", "## Kegagalan", ""]
        for h in gagal:
            baris += [
                f"### {h.kasus['id']} ({h.kasus['kategori']})"
                + (" — diputus hakim" if h.lewat_hakim else ""),
                "",
                f"- Alasan: {h.putusan.alasan}",
                f"- Pertanyaan terakhir: {h.kasus['percakapan'][-1]['isi']}",
                f"- Jejak fungsi: {h.jejak}",
                f"- Jawaban: {h.jawaban[:1500]}",
                "",
            ]
    tujuan.write_text("\n".join(baris), encoding="utf-8")
    return tujuan


async def _jalankan_sungguhan(
    dipilih: list[dict[str, Any]],
    pengaturan: Pengaturan,
    model: str,
    anggaran: int,
    jeda: float,
    pakai_hakim: bool,
    nama_prompt: str,
) -> int:
    # Impor lokal (lihat komentar di atas modul): jalur ini HANYA tercapai
    # dari --sungguhan, jadi `src.main` (dan app FastAPI-nya) baru dibangun
    # persis di sini, tidak pernah pada jalur kering.
    from src.auth.dependencies import wajib_di_atas_tamu
    from src.auth.schemas import Identitas
    from src.main import create_app

    app = create_app()
    # R8: peran dependensi dan klien Supabase ditimpa dengan tiruan --
    # harness tidak boleh butuh token Supabase asli ataupun menyentuh basis
    # data produksi.
    app.dependency_overrides[wajib_di_atas_tamu] = lambda: Identitas(
        id="harness", peran="pemerintah"
    )

    hasil: list[HasilKasus] = []
    pemakaian = 0
    async with app.router.lifespan_context(app):
        # `_lifespan` (src/main.py) MENIMPA `app.state.klien_supabase` dengan
        # klien Supabase ASLI saat masuk -- gantinya harus terjadi SETELAH
        # lifespan masuk, bukan sebelum, kalau tidak tertimpa balik.
        app.state.klien_supabase = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json=[]))
        )
        # R6: paksa SATU model saja. Sengaja TIDAK menyunting
        # src/chat/llm.py -- `_model_coba` ditimpa langsung di instance yang
        # sudah dibangun lifespan, supaya cacah panggilan Gemini per giliran
        # bisa diprediksi anggaran (tanpa eskalasi otomatis ke model lain).
        app.state.layanan_ai._model_coba = [model]
        # `--prompt` benar-benar menukar system prompt yang dipakai
        # `POST /api/chat` (lihat `src/chat/router.py`) -- bukan cuma label
        # laporan. Ditimpa di sini, SETELAH lifespan masuk, dengan alasan
        # yang sama seperti `klien_supabase` dan `_model_coba` di atas.
        app.state.nama_prompt_chat = nama_prompt

        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://harness"
        ) as klien:
            for i, kasus in enumerate(dipilih, start=1):
                h = await _nilai_kasus(klien, kasus, pakai_hakim, pengaturan)
                hasil.append(h)
                pemakaian += h.putaran_alat
                tanda = "lulus" if h.putusan.lulus else f"GAGAL ({h.putusan.alasan})"
                print(
                    f"[{i}/{len(dipilih)}] {kasus['id']}: {tanda} "
                    f"(panggilan {pemakaian}/{anggaran})",
                    flush=True,
                )
                if pemakaian >= anggaran:
                    sisa = len(dipilih) - i
                    if sisa > 0:
                        print(
                            f"PERINGATAN: anggaran panggilan ({anggaran}) tercapai -- "
                            f"{sisa} kasus TIDAK dijalankan.",
                            file=sys.stderr,
                        )
                    break
                if i < len(dipilih):
                    await asyncio.sleep(jeda)

    laporan = _tulis_laporan(
        hasil, nama_prompt, model, len(dipilih), pemakaian, anggaran, pakai_hakim
    )
    total_lulus = sum(1 for h in hasil if h.putusan.lulus)
    terlewat = len(dipilih) - len(hasil)
    print(
        f"\n{total_lulus}/{len(hasil)} lulus (dari {len(dipilih)} dipilih, "
        f"{terlewat} tidak dijalankan) — laporan: {laporan}"
    )
    return 0 if total_lulus == len(hasil) and terlewat == 0 else 1


async def utama(argumen: argparse.Namespace) -> int:
    pengaturan = ambil_pengaturan()

    # R9: kunci wajib eksplisit, dicek SEBELUM kasus pertama dijalankan.
    if argumen.sungguhan and not pengaturan.gemini_api_key_chat.get_secret_value():
        print(
            "GEMINI_API_KEY_CHAT kosong -- isi dulu di .env sebelum memakai --sungguhan.",
            file=sys.stderr,
        )
        return 2

    # `--prompt` kini benar-benar menukar system prompt (lewat
    # `app.state.nama_prompt_chat`, lihat `_jalankan_sungguhan`) -- berkas
    # hilang dicek DI SINI, sebelum kasus pertama dijalankan. Tanpa penjagaan
    # ini, prompt hilang baru ketahuan saat runtime lewat 500 pada TIAP
    # kasus: 51 kegagalan identik yang menyembunyikan penyebabnya.
    if argumen.sungguhan and not (_DIR_PROMPT / argumen.prompt).is_file():
        print(
            f"berkas prompt tidak ditemukan: {_DIR_PROMPT / argumen.prompt}",
            file=sys.stderr,
        )
        return 2

    if argumen.kategori is not None:
        # R5: --kategori mengabaikan --contoh, jalankan seluruh kategori itu.
        dipilih = muat_kasus(argumen.kategori)
        if not dipilih:
            print(
                f"tidak ada kasus untuk kategori {argumen.kategori!r}", file=sys.stderr
            )
            return 2
    elif argumen.semua:
        dipilih = muat_kasus(None)
    else:
        dipilih = pilih_kasus(muat_kasus(None), argumen.contoh)

    masalah = _validasi_skema(dipilih)
    if masalah:
        for m in masalah:
            print(f"skema tidak sah: {m}", file=sys.stderr)
        return 2

    if not argumen.sungguhan:
        # R2: kering, keluar di sini -- NOL jaringan, NOL kuota.
        _cetak_ringkasan_kering(dipilih)
        return 0

    model = argumen.model or pengaturan.model_chat_cadangan
    return await _jalankan_sungguhan(
        dipilih,
        pengaturan,
        model,
        argumen.maks_panggilan,
        argumen.jeda,
        argumen.hakim,
        argumen.prompt,
    )


def _buat_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Runner harness eval Asisten Desa")
    parser.add_argument(
        "--sungguhan",
        action="store_true",
        help="panggil Gemini sungguhan (R9: GEMINI_API_KEY_CHAT wajib terisi)",
    )
    parser.add_argument("--kategori", default=None, help="jalankan satu kategori saja")
    parser.add_argument(
        "--contoh",
        type=int,
        default=8,
        help="cacah kasus contoh, deterministik (bawaan 8, R5)",
    )
    parser.add_argument(
        "--semua", action="store_true", help="jalankan seluruh 51 kasus"
    )
    parser.add_argument(
        "--maks-panggilan",
        type=int,
        default=60,
        help="anggaran keras panggilan Gemini, dihitung dari data.putaran_alat (bawaan 60, R3)",
    )
    parser.add_argument(
        "--hakim",
        action="store_true",
        help="nyalakan hakim LLM untuk kasus abu-abu (R4)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="timpa model (bawaan pengaturan.model_chat_cadangan, R6)",
    )
    parser.add_argument(
        "--jeda",
        type=float,
        default=4.0,
        help="jeda detik antar kasus, serial (bawaan 4.0, R7)",
    )
    parser.add_argument(
        "--prompt",
        default="asisten.md",
        help="berkas prompt di src/chat/prompt/ yang dipakai POST /api/chat (bawaan asisten.md)",
    )
    return parser


def main() -> None:
    argumen = _buat_parser().parse_args()
    sys.exit(asyncio.run(utama(argumen)))


if __name__ == "__main__":
    main()
