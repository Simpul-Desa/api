"""Rute GeoJSON batas desa per kabupaten — respons berkas gzip, bukan amplop JSON."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import FileResponse

from src.datastore import Simpanan, ambil_simpanan, wajib
from src.exceptions import TIDAK_DITEMUKAN, GalatAPI
from src.models import RESPONS_VALIDASI
from src.params import POLA_IDKAB
from src.wilayah.service import wajib_kab_dikenal

router = APIRouter(tags=["Batas Desa"])


# Header `Content-Encoding: gzip` diset manual karena berkas sumber sudah
# terkompresi gzip. `FileResponse` dipanggil TANPA `filename=` supaya
# FastAPI tidak menambahkan `Content-Disposition: attachment`, yang
# memaksa unduh berkas alih-alih menampilkannya inline di klien.
@router.get(
    "/api/geo/desa/{idkab}",
    summary="Batas Desa Kabupaten",
    response_description="Berkas GeoJSON batas desa, terkompresi gzip",
    responses=RESPONS_VALIDASI,
)
async def geo_desa(
    idkab: Annotated[str, Path(pattern=POLA_IDKAB)],
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> FileResponse:
    """Sajikan berkas GeoJSON batas desa satu kabupaten, sudah terkompresi gzip.

    `idkab` yang tidak dikenal menghasilkan galat 404 (amplop JSON) dengan
    kode `WILAYAH_TIDAK_ADA`. `idkab` dikenal tetapi berkas batas desa
    kabupaten itu belum tersedia menghasilkan galat 404 (amplop JSON)
    dengan kode `TIDAK_DITEMUKAN`. Respons yang berhasil membawa header
    `Content-Encoding: gzip` dan tidak memaksa unduh berkas.
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
