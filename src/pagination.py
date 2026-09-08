"""Paginasi seragam untuk seluruh respons daftar.

Menyediakan konstanta batas bawaan/maksimum, alias tipe parameter query siap
pakai untuk router (`hal`/`batas`), serta `potong()` yang memotong daftar
menjadi satu halaman beserta `Meta` amplop yang sesuai.

Nilai bawaan TIDAK ditaruh di dalam `Query()` — FastAPI melarang `default=`
di dalam `Annotated` (AssertionError saat registrasi rute). Pakai di
signature handler: `hal: ParamHal = 1, batas: ParamBatas = BATAS_BAWAAN`.
"""

from typing import Annotated, TypeVar

from fastapi import Query

from src.models import Meta

BATAS_BAWAAN = 50
BATAS_MAKS = 500
# Pada BATAS_BAWAAN=50, HAL_MAKS berarti offset maksimum 500.000 baris —
# jauh di atas artefak terbesar proyek ini (indeks kartu, 17.467 desa),
# jadi tak ada pemanggil sah yang bisa menyentuhnya. Membatasi `hal` di
# sini mencegah `hal` sangat besar memaksa PostgREST/Postgres berjalan dan
# membuang jutaan baris sebelum membalas halaman kosong.
HAL_MAKS = 10_000

ParamHal = Annotated[int, Query(ge=1, le=HAL_MAKS, description="Nomor halaman")]
ParamBatas = Annotated[
    int,
    Query(ge=1, le=BATAS_MAKS, description="Ukuran halaman"),
]

T = TypeVar("T")


def potong(daftar: list[T], hal: int, batas: int) -> tuple[list[T], Meta]:
    """Potong `daftar` menjadi satu halaman tanpa memutasi daftar asal."""

    awal = (hal - 1) * batas
    akhir = awal + batas
    potongan = daftar[awal:akhir]
    meta = Meta(total=len(daftar), hal=hal, batas=batas)
    return potongan, meta
