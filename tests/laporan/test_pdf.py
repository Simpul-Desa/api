"""Uji unit render PDF Laporan Desa (`src/laporan/pdf.py`).

Tidak membandingkan byte dengan fixture — byte PDF reportlab tidak
deterministik (`/CreationDate`, `/ID` berubah tiap build). Uji ini hanya
memeriksa penanda struktural: awalan/akhiran format PDF, build tidak
melempar untuk karakter di luar Latin-1 dan markup mentah, serta
pemenggalan halaman untuk teks panjang.
"""

import base64
import re
import zlib

import pytest

from src.laporan.pdf import _aman, bangun_pdf
from src.laporan.schemas import BarisNilai, RingkasanLaporan, SeksiRingkas, SeksiTabel


def _ringkasan_dasar(**override: object) -> RingkasanLaporan:
    dasar: dict[str, object] = {
        "judul": "Laporan Desa Contoh",
        "subjudul": "Kecamatan Contoh, Kabupaten Contoh",
        "seksi": [
            SeksiRingkas(
                judul="Identitas",
                baris=[BarisNilai(label="Nama Desa", nilai="Desa Contoh")],
            ),
            SeksiTabel(
                judul="Potensi Dominan",
                kepala=["Sektor", "Skor"],
                baris=[["Pertanian", "0.8"]],
            ),
        ],
        "catatan_kaki": "Dibuat otomatis oleh SIMPUL DESA.",
    }
    dasar.update(override)
    return RingkasanLaporan.model_validate(dasar)


@pytest.mark.unit
def test_aman_escape_markup_dan_ganti_karakter_non_latin1() -> None:
    assert _aman("A & B") == "A &amp; B"
    # Karakter di luar tabel transliterasi maupun Latin-1 (mis. CJK) tetap
    # jatuh ke "?" lewat fallback encode("latin-1", "replace") — tidak melempar.
    assert _aman("A 漢 B") == "A ? B"


@pytest.mark.unit
def test_aman_transliterasi_karakter_tipografis_tidak_sisakan_tanda_tanya() -> None:
    """Karakter tipografis yang realistis muncul di teks pemerintah Indonesia
    (em/en dash, kutip lengkung, elipsis, >=/<=) wajib diganti ke padanan
    ASCII-nya, BUKAN jatuh ke "?" lewat fallback Latin-1."""
    hasil = _aman("A—B–C’D‘E“F”G…H≥I≤J")

    # ">"/"<" hasil transliterasi ≥/≤ ikut kena escape markup Paragraph
    # (urutan WAJIB: transliterasi dulu, escape TERAKHIR) — makanya bukan
    # ">="/"<=" mentah di akhir.
    assert hasil == "A-B-C'D'E\"F\"G...H&gt;=I&lt;=J"
    assert "?" not in hasil


@pytest.mark.unit
def test_aman_karakter_di_luar_tabel_dan_latin1_jatuh_ke_tanda_tanya() -> None:
    """CJK dan emoji tidak ada di tabel transliterasi maupun Latin-1 — fallback
    lawas (encode latin-1 replace) tetap berlaku sebagai jaring terakhir,
    tidak melempar galat."""
    assert _aman("laporan 漢字 desa") == "laporan ?? desa"
    assert _aman("emoji 😀 desa") == "emoji ? desa"


@pytest.mark.unit
def test_aman_escape_tetap_terakhir_walau_ada_em_dash() -> None:
    """Urutan WAJIB: transliterasi/Latin-1 dulu, escape markup TERAKHIR.
    Kalau dibalik, `&amp;` hasil escape ikut ter-replace dan rusak."""
    hasil = _aman("A & B — C")

    assert hasil == "A &amp; B - C"


@pytest.mark.unit
def test_pdf_berawalan_dan_berakhiran_penanda() -> None:
    hasil = bangun_pdf(_ringkasan_dasar())

    assert hasil.startswith(b"%PDF-")
    assert b"%%EOF" in hasil[-1024:]
    assert len(hasil) > 1000


@pytest.mark.unit
def test_karakter_di_luar_latin1_tidak_melempar() -> None:
    ringkasan = _ringkasan_dasar(
        seksi=[
            SeksiRingkas(
                judul="Identitas",
                baris=[
                    BarisNilai(
                        label="Nama Desa",
                        nilai="Desa Contoh–Baru’s Café… suhu 20°",
                    )
                ],
            ),
        ],
    )

    hasil = bangun_pdf(ringkasan)

    assert hasil.startswith(b"%PDF-")


@pytest.mark.unit
def test_karakter_markup_tidak_melempar() -> None:
    ringkasan = _ringkasan_dasar(
        seksi=[
            SeksiRingkas(
                judul="Identitas",
                baris=[BarisNilai(label="Nama Desa", nilai="DESA A & B <TEST>")],
            ),
        ],
    )

    hasil = bangun_pdf(ringkasan)

    assert hasil.startswith(b"%PDF-")


@pytest.mark.unit
def _cacah_halaman(pdf: bytes) -> int:
    """Cacah halaman dari simpul pohon halaman PDF (`/Count N /Kids [...]`).

    JANGAN memakai `pdf.count(b"/Type /Page")`: simpul pohon halaman
    bertipe `/Type /Pages`, yang MEMUAT `/Type /Page` sebagai substring.
    PDF satu halaman pun menghasilkan cacah 2, sehingga assert `>= 2`
    lolos tanpa membuktikan apa-apa. Terbukti empiris saat tinjauan
    fase 8.
    """
    cocok = re.search(rb"/Count (\d+) /Kids", pdf)
    assert cocok is not None, "simpul pohon halaman tidak ditemukan di PDF"
    return int(cocok.group(1))


@pytest.mark.unit
def test_teks_panjang_membungkus_bukan_terpotong() -> None:
    """Nilai yang jauh lebih panjang dari satu halaman harus memenggal, bukan hilang.

    Panjangnya sengaja jauh di atas ambang: ~2.000 karakter masih muat di
    satu halaman A4, jadi angka itu tidak menguji apa pun.
    """
    nilai_panjang = "Lorem ipsum dolor sit amet. " * 800  # ~22.400 karakter
    ringkasan = _ringkasan_dasar(
        seksi=[
            SeksiRingkas(
                judul="Identitas",
                baris=[BarisNilai(label="Deskripsi", nilai=nilai_panjang)],
            ),
        ],
    )

    hasil = bangun_pdf(ringkasan)

    assert hasil.startswith(b"%PDF-")
    assert _cacah_halaman(hasil) >= 2


@pytest.mark.unit
def test_satu_halaman_tidak_dianggap_dua() -> None:
    """Penjaga atas cacat assert yang ditemukan tinjauan fase 8.

    Dokumen sependek ini WAJIB satu halaman. Uji ini gagal bila seseorang
    mengembalikan cacah halaman ke `pdf.count(b"/Type /Page")`.
    """
    hasil = bangun_pdf(_ringkasan_dasar())

    assert _cacah_halaman(hasil) == 1
    assert hasil.count(b"/Type /Page") == 2  # /Type /Page + /Type /Pages


def _teks_isi_pdf(pdf: bytes) -> bytes:
    """Dekompres seluruh content stream (`ASCII85Decode` + `FlateDecode`,
    filter bawaan `SimpleDocTemplate`) dan gabungkan jadi satu blob byte.

    Bukti empiris (tinjauan fase 8): stream reportlab TIDAK diawali baris
    baru sebelum `endstream` (`~>endstream` langsung tersambung), jadi
    regex tidak mensyaratkan `\\n` di sana — hanya `rstrip` sisa newline
    sebelum decode.
    """
    gabungan = b""
    for blok in re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.DOTALL):
        blok = blok.rstrip(b"\r\n")
        try:
            gabungan += zlib.decompress(base64.a85decode(blok, adobe=True))
        except (zlib.error, ValueError):
            continue
    return gabungan


@pytest.mark.unit
def test_pdf_tidak_mengandung_tanda_tanya_dari_em_dash() -> None:
    """Ujung ke ujung: em dash di teks sumber TIDAK boleh muncul sebagai
    "?" di content stream PDF jadi — itulah cacat nyata FIX 1 (lihat
    `data-salinan/kartu-ekonomi/kartu/*.json`, field `fakta_program.catatan`
    dan `potensi.dominan` memuat ribuan em dash)."""
    ringkasan = _ringkasan_dasar(
        seksi=[
            SeksiRingkas(
                judul="Identitas",
                baris=[
                    BarisNilai(label="Marka", nilai="MARKAWAL — MARKAKHIR"),
                ],
            ),
        ],
    )

    hasil = bangun_pdf(ringkasan)
    teks = _teks_isi_pdf(hasil)

    assert b"MARKAWAL - MARKAKHIR" in teks
    assert b"MARKAWAL ? MARKAKHIR" not in teks


@pytest.mark.unit
def test_tabel_kosong_dilewati() -> None:
    ringkasan = _ringkasan_dasar(
        seksi=[
            SeksiTabel(judul="Logistik", kepala=["Kolom"], baris=[]),
        ],
    )

    hasil = bangun_pdf(ringkasan)

    assert hasil.startswith(b"%PDF-")
