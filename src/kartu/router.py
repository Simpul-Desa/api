"""Rute detail Kartu Ekonomi Desa (`GET /api/model/kartu/{iddesa}`).

Kartu dikembalikan utuh apa adanya — PRD §5 melarang menyisipkan berita atau
data lain ke dalamnya, dan tidak ada kolom yang disaring.
"""

from typing import Any

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from src.datastore import Simpanan, ambil_simpanan, wajib
from src.exceptions import DESA_TIDAK_ADA, GalatAPI
from src.kartu.service import baca_kartu_kab
from src.models import RESPONS_VALIDASI, Amplop, sukses
from src.params import ParamIddesa

router = APIRouter(prefix="/api/model", tags=["Kartu Ekonomi Desa"])


@router.get(
    "/kartu/{iddesa}",
    response_model=Amplop[dict[str, Any]],
    summary="Detail Kartu Ekonomi Desa",
    response_description="Satu Kartu Ekonomi Desa utuh",
    responses=RESPONS_VALIDASI,
)
async def kartu_detail(
    iddesa: ParamIddesa,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[dict[str, Any]]:
    """Kembalikan satu Kartu Ekonomi Desa utuh apa adanya: identitas,
    peta_peran, rekomendasi_aksi, potensi, kesiapan, biofisik, logistik,
    jalur_ekonomi, desa_kembar, fakta_program, dan mutu_data, tanpa
    penyaringan kolom maupun sisipan data lain.

    `iddesa` yang tidak dikenal menghasilkan galat 404 dengan kode
    `DESA_TIDAK_ADA`.
    """
    indeks_per_desa = wajib(simpanan.indeks_per_desa, "indeks kartu ekonomi")
    baris = indeks_per_desa.get(iddesa)
    if baris is None:
        raise GalatAPI(DESA_TIDAK_ADA, f"desa {iddesa} tidak dikenal", 404)

    kartu_kab = wajib(
        await run_in_threadpool(baca_kartu_kab, str(simpanan.dir_data), baris["idkab"]),
        f"kartu ekonomi kab {baris['idkab']}",
    )
    kartu = kartu_kab.get(iddesa)
    if kartu is None:
        raise GalatAPI(DESA_TIDAK_ADA, f"desa {iddesa} tidak dikenal", 404)

    return sukses(kartu)
