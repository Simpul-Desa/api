"""Skema Berita Desa: payload respons rute dan tipe antar-tahap pipeline panen.

Dikumpulkan di satu berkas karena keempat tipe pipeline dipakai lintas
berkas di dalam `harvest/`, dan `HasilPanen` menyeberang keluar modul —
rute admin penyegaran fase 7 memanggil `panen_desa` dan membaca hasilnya.
"""

from dataclasses import dataclass
from datetime import datetime

from src.models import ModelDasar


class ItemBerita(ModelDasar):
    """Satu berita tersimpan; `perangkum` = gemini / ekstraktif / judul-rss."""

    id: int
    judul: str
    url: str
    sumber: str
    terbit_pada: datetime | None
    dipanen_pada: datetime
    rangkuman: str | None
    kategori: list[str]
    perangkum: str


class ItemRSS(ModelDasar):
    """Satu item hasil RSS; `terbit_pada` None bila pubDate tak terparse."""

    judul: str
    link: str
    terbit_pada: datetime | None
    sumber: str


class HasilSaring(ModelDasar):
    """Vonis penyaring per artikel; `kategori` memakai nama persis daftar MASUK."""

    relevan: bool
    kategori: list[str]
    rangkuman: str
    desa_benar: bool
    alasan: str


class BarisBerita(ModelDasar):
    """Satu baris tabel `berita_desa` (tanpa `id`), siap upsert."""

    iddesa: str
    judul: str
    url: str
    sumber: str
    terbit_pada: datetime | None
    dipanen_pada: datetime
    rangkuman: str | None
    kategori: list[str]
    perangkum: str


@dataclass(frozen=True)
class HasilPanen:
    """Ringkasan panen satu desa.

    `n_dibuang` = tak lolos saring/verifikasi (vonis editorial: berita
    memang tidak relevan/tidak tentang desa ini). `n_gagal` = artikel yang
    MELEMPAR saat diolah (galat teknis: dekode link, ambil HTML, dsb) —
    dipisah dari `n_dibuang` (FIX 1) supaya admin bisa membedakan "minggu
    ini memang sepi berita" dari "pipeline sedang rusak untuk semua
    artikel".
    """

    iddesa: str
    n_baru: int
    n_duplikat: int
    n_dibuang: int
    n_gagal: int
