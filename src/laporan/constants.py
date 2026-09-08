"""Konstanta Laporan Desa: judul seksi, nilai kosong, penjaga kontrak data."""

from typing import Final

# Koordinat kantor Kemenparekraf Jakarta. Menjangkiti data Kemenpar dan
# sudah tiga kali menyesatkan proyek ini (../CLAUDE.md). Baris koordinat
# yang persis sama dengan ini TIDAK dicetak sebagai koordinat desa.
KOORDINAT_PLACEHOLDER: Final[tuple[float, float]] = (-6.2297465, 106.829518)

# Nilai yang dicetak untuk field kosong. Barisnya TETAP dicetak - kolom
# mutu tidak boleh hilang dari laporan (PRD bagian 8).
NILAI_KOSONG: Final[str] = "-"

JUDUL_SEKSI: Final[tuple[str, ...]] = (
    "Identitas",
    "Peta Peran",
    "Potensi Dominan",
    "Kesiapan",
    "Logistik",
    "Desa Kembar",
    "Fakta Program",
    "Rekomendasi Aksi",
    "Mutu Data",
)
