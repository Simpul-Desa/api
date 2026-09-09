"""Rute Jalur Ekonomi: daftar dan detail grup per varian.

Varian: `komoditas`, `gudang-kopdes`, `cold-storage`, `wisata` (Enum path
param — nilai lain otomatis 422). `GET /api/model/jalur-ekonomi/{varian}`
meratakan seluruh grup jadi baris ringkas (lihat `src.jalur_ekonomi.service.ratakan`),
dengan filter opsional `kab`/`iddesa` dan `meta.parameter` diisi blok
`parameter` berkas hasil. `GET .../{varian}/{id_jalur}` mengembalikan grup
utuh (lihat `src.jalur_ekonomi.service.cari_grup`).
"""

from typing import Any

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from src.datastore import Simpanan, ambil_simpanan, wajib
from src.exceptions import TIDAK_DITEMUKAN, WILAYAH_TIDAK_ADA, GalatAPI
from src.jalur_ekonomi.schemas import (
    ParamIddesaFilter,
    ParamKab,
    VarianJalurEkonomi,
)
from src.jalur_ekonomi.service import (
    anggota_iddesa,
    baca_jalur,
    cari_grup,
    ratakan,
)
from src.models import Amplop, sukses
from src.pagination import BATAS_BAWAAN, ParamBatas, ParamHal, potong

router = APIRouter(prefix="/api/model/jalur-ekonomi", tags=["Jalur Ekonomi"])


async def _muat_hasil(simpanan: Simpanan, varian_str: str) -> dict[str, Any]:
    """Baca `jalur-ekonomi/hasil_<varian>.json`; 503 `DATA_BELUM_SIAP` bila hilang.

    Pembacaan berkas dilempar ke threadpool: ia memblokir, dan rute
    pemanggilnya `async`.
    """
    return wajib(
        await run_in_threadpool(baca_jalur, str(simpanan.dir_data), varian_str),
        f"jalur ekonomi varian {varian_str}",
    )


def _grup_dari_baris(
    hasil: dict[str, Any], varian_str: str, baris: dict[str, Any]
) -> dict[str, Any]:
    """Ambil grup mentah untuk satu baris ringkas hasil `ratakan()`.

    Selalu ada — `baris["id_jalur"]` berasal dari `hasil` yang sama. Bila
    ternyata tidak ada, itu cacat internal: dilempar sebagai galat eksplisit
    (bukan `assert`, yang hilang saat Python dijalankan dengan `-O` dan
    menyisakan `TypeError` buram di pemanggil) supaya handler galat global
    mencatat jejaknya dan membalas 500 beramplop.
    """
    grup = cari_grup(hasil, varian_str, baris["id_jalur"])
    if grup is None:
        raise RuntimeError(
            f"grup jalur ekonomi {varian_str} id {baris['id_jalur']} hilang "
            "dari hasil yang sama — cacat internal ratakan/cari_grup"
        )
    return grup


@router.get("/{varian}", response_model=Amplop[list[dict[str, Any]]])
async def daftar_jalur(
    varian: VarianJalurEkonomi,
    kab: ParamKab = None,
    iddesa: ParamIddesaFilter = None,
    hal: ParamHal = 1,
    batas: ParamBatas = BATAS_BAWAAN,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[list[dict[str, Any]]]:
    """Daftar baris ringkas jalur ekonomi, filter opsional `kab`/`iddesa`."""
    varian_str = varian.value
    hasil = await _muat_hasil(simpanan, varian_str)

    if kab is not None and kab not in hasil.get("kabupaten", {}):
        raise GalatAPI(
            WILAYAH_TIDAK_ADA,
            f"kabupaten {kab} tidak dikenal pada jalur ekonomi {varian_str}",
            404,
        )

    baris = ratakan(hasil, varian_str)

    if kab is not None:
        baris = [b for b in baris if b["idkab"] == kab]

    if iddesa is not None:
        baris = [
            b
            for b in baris
            if iddesa
            in anggota_iddesa(_grup_dari_baris(hasil, varian_str, b), varian_str)
        ]

    potongan, meta = potong(baris, hal, batas)
    meta = meta.model_copy(update={"parameter": hasil.get("parameter")})
    return sukses(potongan, meta)


@router.get("/{varian}/{id_jalur}", response_model=Amplop[dict[str, Any]])
async def detail_jalur(
    varian: VarianJalurEkonomi,
    id_jalur: str,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[dict[str, Any]]:
    """Detail satu grup jalur ekonomi utuh (apa adanya + `id_jalur`)."""
    varian_str = varian.value
    hasil = await _muat_hasil(simpanan, varian_str)

    grup = cari_grup(hasil, varian_str, id_jalur)
    if grup is None:
        raise GalatAPI(
            TIDAK_DITEMUKAN,
            f"jalur ekonomi {varian_str} id {id_jalur} tidak ditemukan",
            404,
        )

    return sukses(grup)
