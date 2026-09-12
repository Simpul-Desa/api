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
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.laporan.schemas import RingkasanLaporan, SeksiRingkas, SeksiTabel

_MARGIN: float = 14 * mm
_LEBAR_TEKS_HALAMAN: float = A4[0] - 2 * _MARGIN

# Palet warna Simpul Desa
C_TEAL = HexColor("#0f766e")
C_TEAL_DARK = HexColor("#115e59")
C_TEAL_LIGHT = HexColor("#f0fdfa")
C_SLATE_900 = HexColor("#0f172a")
C_SLATE_700 = HexColor("#334155")
C_SLATE_500 = HexColor("#64748b")
C_SLATE_200 = HexColor("#e2e8f0")
C_SLATE_100 = HexColor("#f1f5f9")
C_SLATE_50 = HexColor("#f8fafc")
C_WHITE = HexColor("#ffffff")
C_CALLOUT_BG = HexColor("#f0fdf4")
C_CALLOUT_BORDER = HexColor("#059669")
C_SKY_BG = HexColor("#f0f9ff")
C_SKY_BORDER = HexColor("#0284c7")

WARNA_ZONA_MAP: Final[dict[str, tuple[HexColor, HexColor]]] = {
    "Zona Poros": (HexColor("#00a9bf"), HexColor("#e0f7fa")),
    "Zona Penyangga": (HexColor("#059669"), HexColor("#d1fae5")),
    "Zona Mandiri": (HexColor("#10b981"), HexColor("#d1fae5")),
    "Zona Berkembang": (HexColor("#f59e0b"), HexColor("#fef3c7")),
    "Zona Bantuan": (HexColor("#ef4444"), HexColor("#fee2e2")),
    "Zona Mitra": (HexColor("#3b82f6"), HexColor("#dbeafe")),
    "Zona Pemerintah": (HexColor("#8b5cf6"), HexColor("#ede9fe")),
    "Belum Terpetakan": (HexColor("#64748b"), HexColor("#f1f5f9")),
}

_TRANSLITERASI: Final[dict[str, str]] = {
    "—": "-",
    "–": "-",
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "…": "...",
    "≥": ">=",
    "≤": "<=",
}


def _aman(teks: str) -> str:
    """Bikin teks aman dicetak di halaman PDF Helvetica."""
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
        "brand": ParagraphStyle(
            "Brand",
            parent=dasar["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            textColor=C_TEAL,
            leading=10,
        ),
        "doc_judul": ParagraphStyle(
            "DocJudul",
            parent=dasar["Normal"],
            fontName="Helvetica-Bold",
            fontSize=15,
            textColor=C_SLATE_900,
            leading=18,
        ),
        "doc_sub": ParagraphStyle(
            "DocSub",
            parent=dasar["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            textColor=C_SLATE_500,
            leading=12,
        ),
        "seksi_judul": ParagraphStyle(
            "SeksiJudul",
            parent=dasar["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=C_TEAL,
            leading=13,
            spaceBefore=6,
            spaceAfter=3,
        ),
        "sub_seksi": ParagraphStyle(
            "SubSeksi",
            parent=dasar["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=C_SLATE_700,
            leading=10.5,
            spaceBefore=2,
            spaceAfter=2,
        ),
        "tabel_kepala": ParagraphStyle(
            "TabelKepala",
            parent=dasar["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            textColor=C_WHITE,
            leading=9.5,
        ),
        "tabel_sel": ParagraphStyle(
            "TabelSel",
            parent=dasar["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            textColor=C_SLATE_900,
            leading=9.5,
        ),
        "tabel_sel_bold": ParagraphStyle(
            "TabelSelBold",
            parent=dasar["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            textColor=C_SLATE_900,
            leading=9.5,
        ),
        "tabel_label": ParagraphStyle(
            "TabelLabel",
            parent=dasar["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            textColor=C_SLATE_500,
            leading=9.5,
        ),
        "kpi_label": ParagraphStyle(
            "KpiLabel",
            parent=dasar["Normal"],
            fontName="Helvetica-Bold",
            fontSize=6.5,
            textColor=C_SLATE_500,
            leading=8,
            alignment=1,
        ),
        "kpi_nilai": ParagraphStyle(
            "KpiNilai",
            parent=dasar["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=C_SLATE_900,
            leading=12,
            alignment=1,
        ),
        "kpi_sub": ParagraphStyle(
            "KpiSub",
            parent=dasar["Normal"],
            fontName="Helvetica",
            fontSize=6.5,
            textColor=C_SLATE_500,
            leading=8,
            alignment=1,
        ),
        "callout": ParagraphStyle(
            "Callout",
            parent=dasar["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            textColor=HexColor("#065f46"),
            leading=10.5,
        ),
        "chip": ParagraphStyle(
            "Chip",
            parent=dasar["Normal"],
            fontName="Helvetica",
            fontSize=7,
            textColor=C_SLATE_700,
            leading=9,
        ),
    }


def _flow_kpi_cards(
    ringkasan: RingkasanLaporan, gaya: dict[str, ParagraphStyle]
) -> Flowable | None:
    pp = ringkasan.peta_peran
    citra = ringkasan.citra_unggulan
    if not pp and not citra:
        return None

    zona = str(pp.get("zona") or "Belum Terpetakan")
    warna_teks, warna_bg = WARNA_ZONA_MAP.get(
        zona, (C_SLATE_700, C_SLATE_100)
    )

    gaya_zona_nilai = ParagraphStyle(
        "KpiZonaNilai",
        parent=gaya["kpi_nilai"],
        textColor=warna_teks,
        fontSize=9.5,
    )

    nomor_zona = pp.get("nomor_zona")
    sub_zona = f"Zona {nomor_zona}" if nomor_zona is not None else "Zona Peran"

    # Card 1: Zona
    c1 = [
        Paragraph("ZONA PETA PERAN", gaya["kpi_label"]),
        Spacer(1, 1 * mm),
        Paragraph(_aman(zona), gaya_zona_nilai),
        Spacer(1, 1 * mm),
        Paragraph(_aman(sub_zona), gaya["kpi_sub"]),
    ]

    # Card 2: Skor Potensi (SP)
    sp = pp.get("SP")
    sp_teks = f"{sp:.2f}" if isinstance(sp, float) else str(sp or "-")
    desil_sp = pp.get("desil_sp")
    sub_sp = f"Desil {desil_sp}" if desil_sp is not None else "Indeks Potensi"
    c2 = [
        Paragraph("SKOR POTENSI (SP)", gaya["kpi_label"]),
        Spacer(1, 1 * mm),
        Paragraph(_aman(sp_teks), gaya["kpi_nilai"]),
        Spacer(1, 1 * mm),
        Paragraph(_aman(sub_sp), gaya["kpi_sub"]),
    ]

    # Card 3: Skor Kesiapan (SK)
    sk = pp.get("SK")
    sk_teks = f"{sk:.2f}" if isinstance(sk, float) else str(sk or "-")
    idm_status = pp.get("idm_status")
    sub_sk = f"IDM: {idm_status}" if idm_status else "Indeks Kesiapan"
    c3 = [
        Paragraph("SKOR KESIAPAN (SK)", gaya["kpi_label"]),
        Spacer(1, 1 * mm),
        Paragraph(_aman(sk_teks), gaya["kpi_nilai"]),
        Spacer(1, 1 * mm),
        Paragraph(_aman(sub_sk), gaya["kpi_sub"]),
    ]

    # Card 4: Citra Unggulan
    komoditas = (citra or {}).get("komoditas") or "-"
    rank = (citra or {}).get("peringkat_dlm_kab")
    sub_citra = f"Peringkat #{rank} Kab" if rank is not None else "Komoditas Unggul"
    c4 = [
        Paragraph("CITRA UNGGULAN (AI)", gaya["kpi_label"]),
        Spacer(1, 1 * mm),
        Paragraph(_aman(komoditas), gaya["kpi_nilai"]),
        Spacer(1, 1 * mm),
        Paragraph(_aman(sub_citra), gaya["kpi_sub"]),
    ]

    col_w = _LEBAR_TEKS_HALAMAN / 4.0
    tabel_kpi = Table([[c1, c2, c3, c4]], colWidths=[col_w] * 4)
    tabel_kpi.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), warna_bg),
                ("BACKGROUND", (1, 0), (3, 0), C_SLATE_50),
                ("BOX", (0, 0), (-1, -1), 0.5, C_SLATE_200),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, C_SLATE_200),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return tabel_kpi


def _flow_ringkas(
    seksi: SeksiRingkas, gaya: dict[str, ParagraphStyle], tampilkan_judul: bool = True
) -> list[Flowable]:
    flow: list[Flowable] = []
    if tampilkan_judul:
        flow.append(Paragraph(f"<b>{_aman(seksi.judul)}</b>", gaya["seksi_judul"]))
        flow.append(
            HRFlowable(
                width="100%", thickness=1, color=C_TEAL, spaceBefore=1, spaceAfter=4
            )
        )

    if not seksi.baris:
        flow.append(Spacer(1, 2 * mm))
        return flow

    # Jika teks nilai panjang (> 150 karakter), render langsung sebagai Paragraph
    # agar ReportLab dapat memenggal halaman tanpa batasan Table row height
    if any(len(b.nilai) > 150 for b in seksi.baris):
        for baris in seksi.baris:
            teks = f"<b>{_aman(baris.label)}:</b> {_aman(baris.nilai)}"
            flow.append(Paragraph(teks, gaya["normal"]))
        flow.append(Spacer(1, 3 * mm))
        return flow

    # Khusus Rekomendasi: render sebagai Callout Box berbingkai hijau
    if len(seksi.baris) == 1 and seksi.baris[0].label == "Rekomendasi":
        teks_rek = (
            f"<b>Arahan Rekomendasi Kebijakan:</b> {_aman(seksi.baris[0].nilai)}"
        )
        callout_tabel = Table(
            [[Paragraph(teks_rek, gaya["callout"])]],
            colWidths=[_LEBAR_TEKS_HALAMAN],
        )
        callout_tabel.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), C_CALLOUT_BG),
                    ("LINEBEFORE", (0, 0), (0, -1), 3, C_CALLOUT_BORDER),
                    ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#bbf7d0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        flow.append(callout_tabel)
        flow.append(Spacer(1, 3 * mm))
        return flow

    # Khusus Citra Potensi Unggulan: render sebagai Highlight Box biru muda
    if seksi.judul == "Citra Potensi Unggulan":
        data_citra = [
            [
                Paragraph(f"<b>{_aman(b.label)}</b>", gaya["tabel_label"]),
                Paragraph(_aman(b.nilai), gaya["tabel_sel_bold"] if i == 0 else gaya["tabel_sel"]),
            ]
            for i, b in enumerate(seksi.baris)
        ]
        tabel_citra = Table(
            data_citra, colWidths=[42 * mm, _LEBAR_TEKS_HALAMAN - 42 * mm]
        )
        tabel_citra.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), C_SKY_BG),
                    ("BOX", (0, 0), (-1, -1), 0.75, C_SKY_BORDER),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, HexColor("#bae6fd")),
                    ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        flow.append(tabel_citra)
        flow.append(Spacer(1, 3 * mm))
        return flow

    # Default SeksiRingkas: 2 pasang kolom (Label 1, Nilai 1, Label 2, Nilai 2)
    # Jika baris genap/banyak, jadikan grid 4 kolom untuk menghemat ruang
    if len(seksi.baris) >= 4:
        baris_tabel: list[list[Paragraph]] = []
        n = len(seksi.baris)
        separuh = (n + 1) // 2
        col1_items = seksi.baris[:separuh]
        col2_items = seksi.baris[separuh:]
        for idx in range(separuh):
            b1 = col1_items[idx]
            b2 = col2_items[idx] if idx < len(col2_items) else None
            baris_tabel.append(
                [
                    Paragraph(_aman(b1.label), gaya["tabel_label"]),
                    Paragraph(_aman(b1.nilai), gaya["tabel_sel"]),
                    Paragraph(_aman(b2.label), gaya["tabel_label"]) if b2 else Paragraph("", gaya["tabel_sel"]),
                    Paragraph(_aman(b2.nilai), gaya["tabel_sel"]) if b2 else Paragraph("", gaya["tabel_sel"]),
                ]
            )
        w_label = 38 * mm
        w_nilai = (_LEBAR_TEKS_HALAMAN - 2 * w_label) / 2.0
        tabel_grid = Table(
            baris_tabel, colWidths=[w_label, w_nilai, w_label, w_nilai]
        )
        tabel_grid.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, C_SLATE_200),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, C_SLATE_100),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("ROWBACKGROUNDS", (0, 0), (-1, -1), [C_WHITE, C_SLATE_50]),
                ]
            )
        )
        flow.append(tabel_grid)
        flow.append(Spacer(1, 3 * mm))
        return flow

    # Tabel sederhana 2 kolom
    data_2col = [
        [
            Paragraph(_aman(b.label), gaya["tabel_label"]),
            Paragraph(_aman(b.nilai), gaya["tabel_sel"]),
        ]
        for b in seksi.baris
    ]
    tabel_2col = Table(
        data_2col, colWidths=[45 * mm, _LEBAR_TEKS_HALAMAN - 45 * mm]
    )
    tabel_2col.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, C_SLATE_200),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, C_SLATE_100),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [C_WHITE, C_SLATE_50]),
            ]
        )
    )
    flow.append(tabel_2col)
    flow.append(Spacer(1, 3 * mm))
    return flow


def _flow_tabel(
    seksi: SeksiTabel, gaya: dict[str, ParagraphStyle], tampilkan_judul: bool = True
) -> list[Flowable]:
    flow: list[Flowable] = []
    if tampilkan_judul:
        flow.append(Paragraph(f"<b>{_aman(seksi.judul)}</b>", gaya["seksi_judul"]))
        flow.append(
            HRFlowable(
                width="100%", thickness=1, color=C_TEAL, spaceBefore=1, spaceAfter=4
            )
        )
    elif seksi.judul == "Kartu Ekonomi Desa":
        flow.append(Paragraph("<b>Potensi Subsektor Ekonomi</b>", gaya["sub_seksi"]))
        flow.append(Spacer(1, 1 * mm))

    if not seksi.baris:
        flow.append(Spacer(1, 2 * mm))
        return flow

    warna_header = (
        C_SLATE_900 if seksi.judul == "Desa Kembar" else C_TEAL
    )
    n_kolom = len(seksi.kepala)
    lebar_kolom = _LEBAR_TEKS_HALAMAN / n_kolom
    data = [[Paragraph(f"<b>{_aman(sel)}</b>", gaya["tabel_kepala"]) for sel in seksi.kepala]] + [
        [
            Paragraph(
                _aman(sel),
                gaya["tabel_sel_bold"] if col_idx == 0 or (seksi.judul == "Desa Kembar" and col_idx == 3) else gaya["tabel_sel"],
            )
            for col_idx, sel in enumerate(baris)
        ]
        for baris in seksi.baris
    ]

    tabel = Table(data, colWidths=[lebar_kolom] * n_kolom)
    tabel.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), warna_header),
                ("BOX", (0, 0), (-1, -1), 0.5, C_SLATE_200),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, C_SLATE_200),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_SLATE_50]),
            ]
        )
    )
    flow.append(tabel)
    flow.append(Spacer(1, 3 * mm))
    return flow


def bangun_pdf(ringkasan: RingkasanLaporan) -> bytes:
    """Render `RingkasanLaporan` menjadi byte PDF komprehensif & dipercantik."""
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

    cerita: list[Flowable] = []

    # Brand Header Bar
    brand_teks = "<b>SIMPUL DESA</b> &nbsp;·&nbsp; Portal Intelijen Ekonomi Desa &amp; Pemodelan Spasial"
    cerita.append(Paragraph(brand_teks, gaya["brand"]))
    cerita.append(
        HRFlowable(
            width="100%", thickness=1, color=C_TEAL, spaceBefore=2, spaceAfter=5
        )
    )

    # Hero Box (Nama Desa & Hirarki Wilayah)
    identitas = ringkasan.identitas
    if identitas and identitas.get("nama"):
        tipe = str(identitas.get("tipe") or "wilayah").capitalize()
        nama_desa = f"{tipe} {_aman(str(identitas.get('nama')))}"
        sub_hirarki = (
            f"Kecamatan {_aman(str(identitas.get('kecamatan') or '-'))} &nbsp;·&nbsp; "
            f"Kabupaten {_aman(str(identitas.get('kabupaten') or '-'))} &nbsp;·&nbsp; "
            f"Provinsi {_aman(str(identitas.get('provinsi') or '-'))}"
        )

        chips_data = [
            [
                Paragraph(f"<b>Kode BPS:</b> {_aman(str(identitas.get('iddesa') or '-'))}", gaya["chip"]),
                Paragraph(f"<b>Kode Dagri:</b> {_aman(str(identitas.get('kode_dagri') or '-'))}", gaya["chip"]),
                Paragraph(f"<b>Luas:</b> {_aman(str(identitas.get('luas_km2') or '-'))} km²", gaya["chip"]),
                Paragraph(f"<b>Koordinat:</b> {_aman(str(identitas.get('lat') or '-'))}, {_aman(str(identitas.get('lon') or '-'))}", gaya["chip"]),
            ]
        ]
        w_chip = _LEBAR_TEKS_HALAMAN / 4.0
        tabel_chips = Table(chips_data, colWidths=[w_chip] * 4)
        tabel_chips.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), C_WHITE),
                    ("BOX", (0, 0), (-1, -1), 0.5, C_SLATE_200),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, C_SLATE_200),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        hero_content = [
            [Paragraph(nama_desa, gaya["doc_judul"])],
            [Spacer(1, 1 * mm)],
            [Paragraph(sub_hirarki, gaya["doc_sub"])],
            [Spacer(1, 2 * mm)],
            [tabel_chips],
        ]
        tabel_hero = Table(hero_content, colWidths=[_LEBAR_TEKS_HALAMAN])
        tabel_hero.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), C_SLATE_50),
                    ("BOX", (0, 0), (-1, -1), 0.5, C_SLATE_200),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        cerita.append(tabel_hero)
        cerita.append(Spacer(1, 3 * mm))
    else:
        # Fallback untuk pengujian dengan model ringkasan minimal
        cerita.append(Paragraph(_aman(ringkasan.judul), gaya["judul"]))
        cerita.append(Paragraph(_aman(ringkasan.subjudul), gaya["subjudul"]))
        cerita.append(Spacer(1, 3 * mm))

    # KPI Grid Bar
    kpi_bar = _flow_kpi_cards(ringkasan, gaya)
    if kpi_bar is not None:
        cerita.append(kpi_bar)
        cerita.append(Spacer(1, 3 * mm))

    # Seksi-seksi Laporan
    judul_sebelumnya: str | None = None
    for seksi in ringkasan.seksi:
        tampilkan_judul = (seksi.judul != judul_sebelumnya)
        judul_sebelumnya = seksi.judul
        if isinstance(seksi, SeksiRingkas):
            blok = _flow_ringkas(seksi, gaya, tampilkan_judul=tampilkan_judul)
        else:
            blok = _flow_tabel(seksi, gaya, tampilkan_judul=tampilkan_judul)

        if seksi.judul in ("Citra Potensi Unggulan", "Desa Kembar"):
            cerita.append(KeepTogether(blok))
        else:
            cerita.extend(blok)

    cerita.append(Spacer(1, 2 * mm))
    cerita.append(
        HRFlowable(
            width="100%", thickness=0.5, color=C_SLATE_200, spaceBefore=2, spaceAfter=3
        )
    )
    cerita.append(Paragraph(_aman(ringkasan.catatan_kaki), gaya["catatan_kaki"]))

    dokumen.build(cerita)
    return buf.getvalue()

