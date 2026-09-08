"""Uji unit model dokumen Laporan Desa (`src/laporan/schemas.py`).

Fokus: diskriminator `Seksi` (`SeksiRingkas | SeksiTabel`) benar-benar
dipakai Pydantic saat parse, bukan cuma saat konstruksi langsung — makanya
uji utamanya lewat `model_validate(model_dump())`, bukan `SeksiTabel(...)`
langsung.
"""

import pytest
from pydantic import ValidationError

from src.laporan.schemas import (
    BarisNilai,
    RingkasanLaporan,
    SeksiRingkas,
    SeksiTabel,
)


@pytest.mark.unit
def test_diskriminator_seksi_bertahan_lewat_round_trip() -> None:
    laporan = RingkasanLaporan(
        judul="Laporan Desa Contoh",
        subjudul="Kecamatan Contoh",
        seksi=[
            SeksiRingkas(
                judul="Identitas",
                baris=[BarisNilai(label="Nama Desa", nilai="Contoh")],
            ),
            SeksiTabel(
                judul="Potensi Dominan",
                kepala=["Sektor", "Skor"],
                baris=[["Pertanian", "0.8"]],
            ),
        ],
        catatan_kaki="Dibuat otomatis.",
    )

    ulang = RingkasanLaporan.model_validate(laporan.model_dump())

    assert isinstance(ulang.seksi[0], SeksiRingkas)
    assert ulang.seksi[0].jenis == "ringkas"
    assert isinstance(ulang.seksi[1], SeksiTabel)
    assert ulang.seksi[1].jenis == "tabel"
    assert ulang.seksi[1].kepala == ["Sektor", "Skor"]
    assert ulang.seksi[1].baris == [["Pertanian", "0.8"]]


@pytest.mark.unit
def test_seksi_ringkas_jenis_bawaan() -> None:
    seksi = SeksiRingkas(judul="Identitas", baris=[])

    assert seksi.jenis == "ringkas"


@pytest.mark.unit
def test_seksi_tabel_jenis_bawaan() -> None:
    seksi = SeksiTabel(judul="Logistik", kepala=["Kolom"], baris=[])

    assert seksi.jenis == "tabel"


@pytest.mark.unit
def test_baris_nilai_menolak_field_hilang() -> None:
    with pytest.raises(ValidationError):
        BarisNilai(label="Nama Desa")  # type: ignore[call-arg]
