"""Rute Desa Kembar: tetangga terdekat precompute per desa."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from starlette.concurrency import run_in_threadpool

from src.datastore import Simpanan, ambil_simpanan, wajib
from src.desa_kembar.constants import KETERANGAN_TANPA_VEKTOR
from src.desa_kembar.schemas import DataDesaKembar
from src.desa_kembar.service import (
    baca_kembar_kab,
    potong_tetangga,
    tetangga_terjoin,
)
from src.exceptions import DESA_TIDAK_ADA, GalatAPI
from src.models import RESPONS_VALIDASI, Amplop, sukses
from src.params import POLA_IDDESA

router = APIRouter(tags=["Desa Kembar"])


@router.get(
    "/api/model/desa-kembar/{iddesa}",
    response_model=Amplop[DataDesaKembar],
    summary="Tetangga Desa Kembar",
    response_description="Tetangga terdekat beserta persentase kemiripan",
    responses=RESPONS_VALIDASI,
)
async def desa_kembar(
    iddesa: Annotated[str, Path(pattern=POLA_IDDESA)],
    k: Annotated[int | None, Query(ge=1)] = None,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[DataDesaKembar]:
    """Kembalikan tetangga desa kembar terdekat untuk satu `iddesa`.

    `iddesa` yang tidak dikenal di indeks kartu ekonomi dijawab 404
    `DESA_TIDAK_ADA`. Desa yang dikenal tetapi belum punya data kemiripan
    tetangga tetap dijawab 200, dengan `tetangga` kosong dan `keterangan`
    yang menjelaskan sebabnya.
    """
    indeks_per_desa = wajib(simpanan.indeks_per_desa, "indeks kartu ekonomi")

    baris = indeks_per_desa.get(iddesa)
    if baris is None:
        raise GalatAPI(DESA_TIDAK_ADA, f"desa {iddesa} tidak dikenal", 404)

    idkab = baris["idkab"]
    kembar_kab = await run_in_threadpool(baca_kembar_kab, str(simpanan.dir_data), idkab)
    # `.get("desa")`: berkas kembar tanpa kunci `desa` diperlakukan sama
    # dengan desa tanpa vektor fitur — jalur anggun 200 + `keterangan` yang
    # sudah ada di bawah, bukan 500. Rute ini sengaja tidak 503: kontraknya
    # (keputusan desain fase 3 butir 6) adalah data kosong berketerangan.
    peta_kembar = (kembar_kab or {}).get("desa") or {}
    baris_tetangga = peta_kembar.get(iddesa)

    if baris_tetangga is None:
        data = DataDesaKembar(
            iddesa=iddesa, tetangga=[], keterangan=KETERANGAN_TANPA_VEKTOR
        )
        return sukses(data)

    tetangga = potong_tetangga(tetangga_terjoin(baris_tetangga, indeks_per_desa), k)
    return sukses(DataDesaKembar(iddesa=iddesa, tetangga=tetangga))
