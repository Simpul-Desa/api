"""Guardrail level kode Asisten Desa: filter injeksi pra-LLM dan validasi keluaran pasca-LLM.

Validasi masukan (cacah pesan, panjang karakter, rentang suhu) TIDAK ada di
sini -- itu ditegakkan skema Pydantic `src/chat/schemas.py`.
"""

import base64
import re
from collections import Counter
from typing import Any

# Angka format Indonesia (1.248 · 72,4 · 68%) maupun titik-desimal (72.4).
_POLA_ANGKA = re.compile(
    r"(?<![\w,.])("
    r"\d{1,3}(?:\.\d{3})+(?:,\d+)?"  # ribuan titik, opsional desimal koma
    r"|\d+,\d+"  # desimal koma
    r"|\d+(?:\.\d+)?"  # bulat atau desimal titik
    # titik/koma penutup kalimat boleh; titik/koma lanjut digit berarti bagian
    # angka lain (jangan potong di tengah)
    r")%?(?!\w|[.,]\d)"
)

# Angka yang tidak dituntut punya asal: tahun, dan bilangan kecil 0-10
# (urutan daftar, nomor kuadran 1-4, "3 desa termirip").
_TAHUN_MIN, _TAHUN_MAKS = 1900, 2100
_KECIL_MAKS = 10


def _ke_float(mentah: str) -> tuple[float, int]:
    """Normalisasi satu token angka ke (nilai, cacah_desimal)."""
    token = mentah.rstrip("%")
    if "," in token:
        token = token.replace(".", "").replace(",", ".")
    elif "." in token:
        utuh, _, pecahan = token.rpartition(".")
        # Titik + tepat 3 digit tanpa koma = pemisah ribuan Indonesia (1.248),
        # selain itu desimal titik (72.4 / 3.14).
        if (
            len(pecahan) == 3
            and utuh
            and "." not in utuh
            and len(utuh) <= 3
            or "." in utuh
        ):
            token = token.replace(".", "")
    nilai = float(token)
    desimal = len(token.partition(".")[2])
    return nilai, desimal


def ekstrak_angka(teks: str) -> list[tuple[float, int]]:
    """Semua angka dalam teks sebagai (nilai, cacah_desimal), tanpa angka 'aman'."""
    hasil: list[tuple[float, int]] = []
    for cocok in _POLA_ANGKA.finditer(teks):
        nilai, desimal = _ke_float(cocok.group(1))
        if desimal == 0 and _TAHUN_MIN <= nilai <= _TAHUN_MAKS:
            continue
        if desimal == 0 and 0 <= nilai <= _KECIL_MAKS:
            continue
        hasil.append((nilai, desimal))
    return hasil


def _kumpul_angka_sumber(objek: Any, tampung: set[float]) -> None:
    if isinstance(objek, bool):
        return
    if isinstance(objek, (int, float)):
        tampung.add(float(objek))
    elif isinstance(objek, str):
        try:
            nilai, _ = _ke_float(objek.strip().rstrip("%"))
        except ValueError:
            return
        tampung.add(nilai)
    elif isinstance(objek, dict):
        for nilai in objek.values():
            _kumpul_angka_sumber(nilai, tampung)
    elif isinstance(objek, (list, tuple)):
        for butir in objek:
            _kumpul_angka_sumber(butir, tampung)


def angka_dalam_teks(teks: str) -> set[float]:
    """Semua angka dalam sebuah teks sumber (tanpa pengecualian angka 'aman').

    Dipakai untuk menjadikan system prompt (konteks metodologi) sumber sah:
    angka definisional seperti 17.467 desa atau skala 0-100 bukan halusinasi.
    """
    return {_ke_float(cocok.group(1))[0] for cocok in _POLA_ANGKA.finditer(teks)}


def angka_berasal(
    jawaban: str, hasil_fungsi: list[Any], sumber_tambahan: set[float] | None = None
) -> list[str]:
    """Daftar angka di jawaban yang TIDAK ditemukan pada hasil fungsi mana pun
    (atau `sumber_tambahan`, mis. angka dari system prompt).

    Toleransi: pembulatan 0,5 unit pada digit desimal terakhir jawaban
    (72,4 cocok dengan 72.44 di sumber).
    """
    sumber: set[float] = set(sumber_tambahan or ())
    for hasil in hasil_fungsi:
        _kumpul_angka_sumber(hasil, sumber)
    tanpa_asal: list[str] = []
    for nilai, desimal in ekstrak_angka(jawaban):
        toleransi = 0.5 * (10**-desimal) + 1e-9
        if not any(abs(nilai - asal) <= toleransi for asal in sumber):
            tanpa_asal.append(f"{nilai:g}")
    return tanpa_asal


# --- Deteksi injeksi (pra-LLM) ----------------------------------------------

# Karakter tak terlihat: soft hyphen (U+00AD), zero-width + penanda arah
# (U+200B-U+200F), BOM (U+FEFF), kontrol bidi (U+202A-U+202E), word joiner +
# invisible operator + isolat bidi (U+2060-U+2069), tag unicode
# (U+E0000-U+E007F) -- semua dipakai menyembunyikan payload injeksi.
_INVISIBLE = re.compile(
    "[\u00ad\u200b-\u200f\ufeff\u202a-\u202e\u2060-\u2069\U000e0000-\U000e007f]"
)

# Runtutan huruf tunggal berspasi ("a b a i k a n") -- teknik Best-of-N untuk
# melewati pencocokan pola kata utuh.
_POLA_SPASI_HURUF = re.compile(r"\b(?:[A-Za-z][ \t]){2,}[A-Za-z]\b")

_POLA_INJEKSI: list[re.Pattern[str]] = [
    # ID: perintah membuang instruksi/perintah/aturan sebelumnya
    re.compile(
        r"abaikan\s+(semua\s+|seluruh\s+)?(instruksi|perintah|aturan)", re.IGNORECASE
    ),
    # EN: ignore all previous instructions
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    # dwibahasa: mode developer / developer mode
    re.compile(r"(mode|modus)\s+developer|developer\s+mode", re.IGNORECASE),
    # EN: klaim otorisasi tingkat sistem / instruksi pengganti
    re.compile(r"system\s+override|new\s+instruction", re.IGNORECASE),
    # dwibahasa: minta bongkar system prompt (jarak maks 30 karakter)
    re.compile(
        r"(bocorkan|tuliskan|reveal|tunjukkan|repeat).{0,30}(system\s*prompt|instruksi\s+sistem)",
        re.IGNORECASE,
    ),
    # ID: klaim ganti peran paksa -- wajib diikuti kata benda peran ("kamu
    # sekarang punya data..." adalah kalimat sah, bukan ganti peran), dan
    # "asisten desa" dikecualikan (menegaskan peran resmi bukan serangan).
    re.compile(
        r"kamu\s+sekarang\s+(?:adalah\s+)?(?:seorang\s+|sebuah\s+|si\s+)?"
        r"(?!asisten\s+desa)"
        r"(?:ai\b|bot\b|chatbot|asisten\b|penasihat|pakar|ahli|model|agen|"
        r"persona|karakter|hakim|penulis|hacker|dokter)",
        re.IGNORECASE,
    ),
    # dwibahasa: minta lepas batasan/filter dalam konteks jailbreak -- bigram
    # telanjang "tanpa batasan" adalah frasa sehari-hari yang sah ("tersedia
    # tanpa batasan wilayah"), jadi wajib menempel subjek AI/perintah jawab
    # atau bentuk total "apa pun".
    re.compile(
        r"(?:ai|bot|chatbot|asisten|model|jawab\w*|menjawab|balas\w*)\s+"
        r"tanpa\s+(?:batasan|filter|sensor)"
        r"|tanpa\s+(?:batasan|filter|sensor)\s+apa\s*pun"
        r"|do\s+anything\s+now",
        re.IGNORECASE,
    ),
]

# Jailbreak "DAN" (Do Anything Now) HARUS huruf besar semua -- kata "dan"
# Indonesia terlalu umum untuk IGNORECASE -- DAN wajib dalam konteks penamaan
# persona / mode ("bernama DAN", "DAN mode"): kalimat kapital sah macam
# "SKOR POTENSI DAN SKOR KESIAPAN" tidak boleh kena (kata sebelumnya bukan
# kata penamaan). Kata konteks boleh huruf apa pun ((?i:...)), DAN-nya tidak.
_POLA_DAN = re.compile(
    r"(?i:bernama|adalah|called|named|you\s+are|act\s+as)\s+DAN\b"
    r"|\bDAN\b\s*[,:]?\s*(?i:mode|yang\s+menjawab)"
)

# Kata kunci untuk cek typoglycemia (huruf tengah diacak, sengaja salah eja) --
# lihat _mirip_kata. Satu kata cocok = skor 1, TIDAK PERNAH memblokir sendirian
# (ambang blokir ditentukan pemanggil di asisten/inti.py).
_KATA_FUZZY = [
    "abaikan",
    "instruksi",
    "ignore",
    "bypass",
    "override",
    "reveal",
    "jailbreak",
    "prompt",
]

# Frasa serangan inti dalam bentuk rapat (seluruh spasi/tanda dibuang) --
# lawan BoN spasi seragam ("a b a i k a n s e m u a ..."), yang bila
# dirapatkan menempel jadi satu token raksasa dan lolos pola multi-kata.
_FRASA_RAPAT = [
    "abaikansemuainstruksi",
    "abaikanseluruhinstruksi",
    "abaikaninstruksisebelumnya",
    "ignoreallpreviousinstructions",
    "ignorepreviousinstructions",
]
_POLA_NON_HURUF = re.compile(r"[^a-z]+")

# Token yang layak dicoba dekode sebagai payload tersembunyi.
_POLA_TOKEN_BASE64 = re.compile(r"[A-Za-z0-9+/=]{16,}")
_POLA_TOKEN_HEX = re.compile(r"[0-9a-fA-F]{20,}")


def normalisasi_masukan(teks: str) -> str:
    """Buang karakter tak terlihat dan rapatkan spasi ganda sebelum deteksi.

    Tidak mengubah huruf besar/kecil (deteksi pola memakai IGNORECASE secara
    terpisah) dan tidak menyentuh digit/tanda baca angka.
    """
    tanpa_invisible = _INVISIBLE.sub("", teks)
    return re.sub(r"\s{2,}", " ", tanpa_invisible)


def buang_tak_terlihat(teks: str) -> str:
    """Buang karakter tak terlihat dari KELUARAN model.

    `_INVISIBLE` sebelumnya hanya dipakai jalur masukan. Tanpa ini, model
    yang diperintah menyalin instruksi sistem dengan zero-width space di
    sela karakter meloloskan prompt utuh ke pengguna: `bocor_prompt` hanya
    merapikan spasi biasa, jadi baris itu tidak pernah cocok.
    """
    return _INVISIBLE.sub("", teks)


def _mirip_kata(kata: str, referensi: str) -> bool:
    """Typoglycemia (cheat sheet OWASP): huruf pertama+terakhir sama, huruf
    tengah teracak -- dengan toleransi satu huruf hilang/tambah ("intruski"
    untuk "instruksi" adalah acak MINUS satu huruf, bukan acak murni). Cocok
    persis juga True."""
    if kata == referensi:
        return True
    if len(kata) < 4 or abs(len(kata) - len(referensi)) > 1:
        return False
    if kata[0] != referensi[0] or kata[-1] != referensi[-1]:
        return False
    tengah_a = Counter(kata[1:-1])
    tengah_b = Counter(referensi[1:-1])
    selisih = sum((tengah_a - tengah_b).values()) + sum((tengah_b - tengah_a).values())
    return selisih <= 1


def _rapatkan_spasi_huruf(teks: str) -> str:
    """Gabungkan runtutan huruf tunggal berspasi jadi satu kata (lawan BoN)."""
    return _POLA_SPASI_HURUF.sub(lambda m: re.sub(r"[ \t]", "", m.group(0)), teks)


def _skor_pola(target: str, label: str) -> tuple[int, list[str]]:
    """Jumlahkan skor _POLA_INJEKSI (+ _POLA_DAN terpisah) pada satu teks."""
    skor = 0
    alasan: list[str] = []
    for pola in _POLA_INJEKSI:
        if pola.search(target):
            skor += 2
            alasan.append(f"{label}:pola:{pola.pattern[:40]}")
    if _POLA_DAN.search(target):
        skor += 2
        alasan.append(f"{label}:pola:DAN")
    return skor, alasan


def deteksi_injeksi(teks: str) -> tuple[int, list[str]]:
    """Skor risiko injeksi dan daftar alasan (untuk log, bukan untuk user).

    Skor 2 per pola dwibahasa eksplisit yang cocok (termasuk hasil dekode
    base64/hex dan varian huruf-renggang Best-of-N), skor 1 per kata fuzzy
    typoglycemia. Ambang blokir ditentukan pemanggil (asisten/inti.py).
    """
    ternormalisasi = normalisasi_masukan(teks)
    skor = 0
    alasan: list[str] = []

    tambahan_skor, tambahan_alasan = _skor_pola(ternormalisasi, "utama")
    skor += tambahan_skor
    alasan += tambahan_alasan

    # Rapatkan huruf-renggang PADA TEKS SEBELUM spasi ganda dirapatkan: spasi
    # ganda antar-kata sengaja dipakai penyerang sebagai batas kata ("a b a i
    # k a n  s e m u a" -- dua spasi antar-kata, satu spasi antar-huruf). Bila
    # dirapatkan dari `ternormalisasi` (yang sudah menyamakan semua spasi jadi
    # satu), batas kata ikut hilang dan seluruh kalimat menempel jadi satu
    # kata raksasa yang tidak lagi cocok pola multi-kata mana pun.
    tanpa_invisible = _INVISIBLE.sub("", teks)
    dirapatkan = _rapatkan_spasi_huruf(tanpa_invisible)
    if dirapatkan != tanpa_invisible:
        tambahan_skor, tambahan_alasan = _skor_pola(dirapatkan, "spasi-huruf")
        skor += tambahan_skor
        alasan += tambahan_alasan

    # Frasa serangan dalam bentuk rapat: menangkap BoN spasi seragam
    # ("a b a i k a n s e m u a ...") yang lolos dari _rapatkan_spasi_huruf.
    rapat = _POLA_NON_HURUF.sub("", tanpa_invisible.lower())
    for frasa in _FRASA_RAPAT:
        if frasa in rapat:
            skor += 2
            alasan.append(f"rapat:{frasa}")
            break

    # Fuzzy dua tingkat. Kata SALAH EJA disengaja (typoglycemia) = bukti kuat,
    # 1 poin per kata berbeda. Kata PERSIS = kata sehari-hari yang sah
    # ("abaikan", "instruksi"), total maksimum 1 poin berapa pun cacahnya --
    # kata sah tidak boleh terakumulasi sampai ambang blokir (false refusal).
    fuzzy_persis: set[str] = set()
    fuzzy_acak: set[str] = set()
    for token in re.findall(r"[A-Za-z]+", ternormalisasi):
        kecil = token.lower()
        for kata in _KATA_FUZZY:
            if kecil == kata:
                fuzzy_persis.add(kata)
                break
            if _mirip_kata(kecil, kata):
                fuzzy_acak.add(kata)
                alasan.append(f"fuzzy-acak:{kata}~{token}")
                break
    skor += len(fuzzy_acak)
    if fuzzy_persis:
        skor += 1
        alasan.append("fuzzy-persis:" + ",".join(sorted(fuzzy_persis)))

    for cocok in _POLA_TOKEN_BASE64.finditer(ternormalisasi):
        terdekode = _dekode_base64(cocok.group(0))
        if terdekode is None:
            continue
        tambahan_skor, tambahan_alasan = _skor_pola(terdekode, "base64")
        skor += tambahan_skor
        alasan += tambahan_alasan

    for cocok in _POLA_TOKEN_HEX.finditer(ternormalisasi):
        for terdekode in _dekode_hex(cocok.group(0)):
            tambahan_skor, tambahan_alasan = _skor_pola(terdekode, "hex")
            skor += tambahan_skor
            alasan += tambahan_alasan
            if tambahan_skor:
                break

    return skor, alasan


def _dekode_base64(token: str) -> str | None:
    """Dekode token base64; token tanpa padding dicoba ulang dengan padding."""
    for kandidat in (token, token + "=" * (-len(token) % 4)):
        try:
            return base64.b64decode(kandidat, validate=True).decode(
                "utf-8", errors="ignore"
            )
        except ValueError:
            continue
    return None


def _dekode_hex(heks: str) -> list[str]:
    """Dekode runtutan hex; panjang ganjil dicoba tanpa nibble depan/belakang."""
    kandidat = [heks] if len(heks) % 2 == 0 else [heks[:-1], heks[1:]]
    hasil: list[str] = []
    for calon in kandidat:
        try:
            hasil.append(bytes.fromhex(calon).decode("utf-8", errors="ignore"))
        except ValueError:
            continue
    return hasil


# --- Validasi keluaran (pasca-LLM) -------------------------------------------

_POLA_MARKER_MD = re.compile(r"[#*_`>~]")
_POLA_IMG_HTML = re.compile(r"<img[^>]*>", re.IGNORECASE)
# Wajib berbentuk tag (nama elemen setelah <) -- "skor <40 dan luas >100"
# adalah teks perbandingan sah, bukan tag, jangan ikut terhapus.
_POLA_TAG_HTML = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^>]*)?/?>")
_POLA_GAMBAR_MD = re.compile(r"!\[[^\]]*\]\([^)]*\)")
# Semua skema tautan markdown dibuang (http, data:, javascript:, //host, ...)
# -- teks tautannya disisakan.
_POLA_TAUTAN_MD = re.compile(r"\[([^\]]*)\]\([^)]*\)")
# URL telanjang (tanpa markdown) = jalur eksfiltrasi cadangan model.
_POLA_URL_TELANJANG = re.compile(r"\b\w+://\S+|\bwww\.\S+", re.IGNORECASE)

_PANJANG_BARIS_MIN = 30


def bocor_prompt(jawaban: str, prompt_instruksi: str) -> bool:
    """True bila salah satu baris template instruksi muncul verbatim di jawaban
    (case-insensitive, spasi dirapatkan); hanya baris >=30 karakter yang dicek.

    GOTCHA: `prompt_instruksi` HARUS template instruksi mentah (Railguard dkk.),
    BUKAN hasil `muat_prompt` yang sudah disisipi metodologi -- baris
    metodologi (mis. "17.467 desa") memang bahan jawaban yang sah dan tidak
    boleh dianggap kebocoran.
    """
    # Marker markdown dibuang dari DUA sisi -- kebocoran yang membungkus tiap
    # kata dengan **bold** atau menyisakan `backtick` template tetap tertangkap.
    jawaban_bersih = _POLA_MARKER_MD.sub("", jawaban)
    # Rapatkan huruf-renggang ("k a m u  a d a l a h ...") pada salinan
    # deteksi -- lawan varian Best-of-N yang menyisipkan spasi antar huruf
    # supaya baris verbatim lolos dari perapian spasi-ganda biasa di bawah.
    jawaban_bersih = _rapatkan_spasi_huruf(jawaban_bersih)
    jawaban_rapi = re.sub(r"\s+", " ", jawaban_bersih).strip().lower()
    for baris in prompt_instruksi.splitlines():
        baris_bersih = _POLA_MARKER_MD.sub("", baris)
        baris_rapi = re.sub(r"\s+", " ", baris_bersih).strip().lower()
        if len(baris_rapi) >= _PANJANG_BARIS_MIN and baris_rapi in jawaban_rapi:
            return True
    return False


def buang_markup(jawaban: str) -> tuple[str, bool]:
    """Buang markup berpotensi eksfiltrasi: tag `<img>`/HTML lain, gambar
    markdown, dan tautan markdown ke URL luar (teks tautan disisakan).

    Jawaban sah Asisten Desa tidak pernah butuh menyisipkan URL luar.
    """
    bersih = _POLA_IMG_HTML.sub("", jawaban)
    bersih = _POLA_GAMBAR_MD.sub("", bersih)
    bersih = _POLA_TAUTAN_MD.sub(r"\1", bersih)
    bersih = _POLA_TAG_HTML.sub("", bersih)
    bersih = _POLA_URL_TELANJANG.sub("", bersih)
    return bersih, bersih != jawaban
