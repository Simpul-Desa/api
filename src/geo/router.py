"""Rute GeoJSON batas desa per kabupaten — respons berkas gzip, bukan amplop JSON."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import FileResponse

from src.datastore import Simpanan, ambil_simpanan, wajib
from src.exceptions import TIDAK_DITEMUKAN, GalatAPI
from src.params import POLA_IDKAB
from src.wilayah.service import wajib_kab_dikenal

router = APIRouter()


@router.get("/api/geo/desa/{idkab}")
async def geo_desa(
    idkab: Annotated[str, Path(pattern=POLA_IDKAB)],
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> FileResponse:
    """Sajikan GeoJSON batas desa pra-gzip satu kabupaten sebagai berkas.

    `idkab` yang tak dikenal di `simpanan.wilayah` menghasilkan 404 (amplop
    JSON) `WILAYAH_TIDAK_ADA`. `idkab` dikenal tapi berkas
    `geo/<idkab>.geojson.gz` belum ada menghasilkan 404 (amplop JSON)
    `TIDAK_DITEMUKAN`. Bila berkas ada, dikembalikan lewat `FileResponse`
    dengan header `Content-Encoding: gzip` diset manual (berkas sumber sudah
    ter-kompresi) — TANPA `filename=`, supaya FastAPI tidak menambahkan
    header `Content-Disposition: attachment` yang memaksa unduh berkas.
    """
    wilayah = wajib(simpanan.wilayah, "wilayah")

    wajib_kab_dikenal(wilayah, idkab)

    path = simpanan.dir_data / "geo" / f"{idkab}.geojson.gz"
    if not path.is_file():
        raise GalatAPI(TIDAK_DITEMUKAN, f"geo kabupaten {idkab} belum tersedia", 404)

    return FileResponse(
        path,
        media_type="application/geo+json",
        headers={"Content-Encoding": "gzip"},
    )
