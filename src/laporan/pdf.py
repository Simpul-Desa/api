"""Render model dokumen Laporan Desa menjadi byte PDF (reportlab Platypus).

Font bawaan reportlab (Helvetica) berenkode Latin-1: karakter di
luarnya dicetak sebagai kotak hitam, BUKAN galat, sehingga cacatnya
hanya terlihat di berkas jadi. Karena itu setiap teks melewati
`_aman()` sebelum masuk halaman. Menyematkan font TTF menghindarinya
tetapi berarti menambah aset biner ke repo - ditolak untuk MVP.
"""

import io
from typing import Final
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.laporan.schemas import RingkasanLaporan, SeksiRingkas, SeksiTabel

_MARGIN: float = 18 * mm
_LEBAR_TEKS_HALAMAN: float = A4[0] - 2 * _MARGIN

# Karakter tipografis yang realistis muncul di teks pemerintah Indonesia
# (termasuk data hasil panen `data-salinan/kartu-ekonomi/` — em dash marak di
# `fakta_program.catatan` dan `potensi.dominan`). Semuanya di luar Latin-1,
# jadi tanpa tabel ini `_aman` menjatuhkannya ke "?" lewat fallback di bawah.
_TRANSLITERASI: Final[dict[str, str]] = {
    "—": "-",  # em dash —
    "–": "-",  # en dash –
    "’": "'",  # kutip tunggal lengkung kanan '
    "‘": "'",  # kutip tunggal lengkung kiri '
    "“": '"',  # kutip ganda lengkung kiri "
    "”": '"',  # kutip ganda lengkung kanan "
    "…": "...",  # elipsis …
    "≥": ">=",  # ≥
    "≤": "<=",  # ≤
}


def _aman(teks: str) -> str:
    """Bikin teks aman dicetak di halaman PDF Helvetica.

    Urutan WAJIB: transliterasi karakter tipografis DULU, lalu ganti sisa
    karakter di luar Latin-1 (jaring terakhir, mis. CJK/emoji) sebagai
    fallback, escape markup Paragraph TERAKHIR. Kalau escape dipindah ke
    depan, `&amp;` hasilnya ikut ter-replace oleh langkah-langkah di atas
    dan rusak.
    """
    for asli, pengganti in _TRANSLITERASI.items():
        teks = teks.replace(asli, pengganti)
    latin1 = teks.encode("latin-1", "replace").decode("latin-1")
    return escape(latin1)


def _gaya() -> dict[str, ParagraphStyle]:
    dasar = getSampleStyleSheet()
    return {
        "judul": dasar["Title"],
        "subjudul": dasar["Heading3"],
        "judul_seksi": dasar["Heading2"],
        "normal": dasar["BodyText"],
        "catatan_kaki": dasar["Italic"],
    }


def _flow_ringkas(
    seksi: SeksiRingkas, gaya: dict[str, ParagraphStyle]
) -> list[Flowable]:
    flow: list[Flowable] = [Paragraph(_aman(seksi.judul), gaya["judul_seksi"])]
    for baris in seksi.baris:
        teks = f"<b>{_aman(baris.label)}:</b> {_aman(baris.nilai)}"
        flow.append(Paragraph(teks, gaya["normal"]))
    flow.append(Spacer(1, 4 * mm))
    return flow


def _flow_tabel(seksi: SeksiTabel, gaya: dict[str, ParagraphStyle]) -> list[Flowable]:
    flow: list[Flowable] = [Paragraph(_aman(seksi.judul), gaya["judul_seksi"])]
    if not seksi.baris:
        flow.append(Spacer(1, 4 * mm))
        return flow

    n_kolom = len(seksi.kepala)
    lebar_kolom = _LEBAR_TEKS_HALAMAN / n_kolom
    data = [[Paragraph(_aman(sel), gaya["normal"]) for sel in seksi.kepala]] + [
        [Paragraph(_aman(sel), gaya["normal"]) for sel in baris]
        for baris in seksi.baris
    ]
    tabel = Table(data, colWidths=[lebar_kolom] * n_kolom)
    tabel.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    flow.append(tabel)
    flow.append(Spacer(1, 4 * mm))
    return flow


def bangun_pdf(ringkasan: RingkasanLaporan) -> bytes:
    """Render `RingkasanLaporan` menjadi byte PDF siap unduh."""
    buf = io.BytesIO()
    dokumen = SimpleDocTemplate(
        buf,
        pagesize=A4,
        title=ringkasan.judul,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
    )
    gaya = _gaya()

    cerita: list[Flowable] = [
        Paragraph(_aman(ringkasan.judul), gaya["judul"]),
        Paragraph(_aman(ringkasan.subjudul), gaya["subjudul"]),
        Spacer(1, 6 * mm),
    ]
    for seksi in ringkasan.seksi:
        if isinstance(seksi, SeksiRingkas):
            cerita.extend(_flow_ringkas(seksi, gaya))
        else:
            cerita.extend(_flow_tabel(seksi, gaya))
    cerita.append(Spacer(1, 4 * mm))
    cerita.append(Paragraph(_aman(ringkasan.catatan_kaki), gaya["catatan_kaki"]))

    dokumen.build(cerita)
    return buf.getvalue()
