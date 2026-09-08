"""Rute wilayah: provinsi, ringkasan, kabupaten, dan desa (data referensi)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.datastore import Simpanan, ambil_simpanan, wajib
from src.models import Amplop, sukses
from src.pagination import BATAS_BAWAAN, ParamBatas, ParamHal, potong
from src.params import POLA_IDKAB, POLA_IDPROV
from src.wilayah.schemas import (
    DesaRingkas,
    Kabupaten,
    Provinsi,
    RingkasanWilayah,
)
from src.wilayah.service import wajib_kab_dikenal, wajib_prov_dikenal

router = APIRouter()


@router.get("/api/wilayah/provinsi", response_model=Amplop[list[Provinsi]])
async def daftar_provinsi(
    hal: ParamHal = 1,
    batas: ParamBatas = BATAS_BAWAAN,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[list[Provinsi]]:
    """Daftar seluruh provinsi dari `wilayah.json`, berpaginasi."""
    wilayah = wajib(simpanan.wilayah, "wilayah")

    # `muat_json_atau_none` sengaja TIDAK memvalidasi kunci di dalam artefak
    # (docstringnya menyerahkan itu ke pemanggil). Tanpa `wajib()` di sini,
    # wilayah.json yang kehilangan kunci `provinsi` melempar KeyError dan
    # dilaporkan 500 GALAT_SERVER — padahal yang cacat build datanya, dan
    # seluruh stack ini memakai 503 DATA_BELUM_SIAP untuk itu.
    daftar_prov = wajib(wilayah.get("provinsi"), "daftar provinsi wilayah")

    potongan, meta = potong(daftar_prov, hal, batas)
    return sukses([Provinsi(**baris) for baris in potongan], meta)


@router.get("/api/wilayah/ringkasan", response_model=Amplop[RingkasanWilayah])
async def ringkasan_wilayah(
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[RingkasanWilayah]:
    """Kembalikan `simpanan.ringkasan_wilayah` apa adanya — bukan daftar, tanpa meta."""
    ringkasan = wajib(simpanan.ringkasan_wilayah, "ringkasan wilayah")
    return sukses(RingkasanWilayah(**ringkasan))


@router.get("/api/wilayah/kabupaten", response_model=Amplop[list[Kabupaten]])
async def daftar_kabupaten(
    prov: Annotated[str | None, Query(pattern=POLA_IDPROV)] = None,
    hal: ParamHal = 1,
    batas: ParamBatas = BATAS_BAWAAN,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[list[Kabupaten]]:
    """Daftar kabupaten, filter opsional `prov` (kode provinsi 2 digit).

    `prov` yang bentuknya sah tapi tak dikenal di `simpanan.wilayah`
    menghasilkan 404 `WILAYAH_TIDAK_ADA`.
    """
    wilayah = wajib(simpanan.wilayah, "wilayah")
    daftar_kab = wajib(wilayah.get("kabupaten"), "daftar kabupaten wilayah")

    if prov is not None:
        wajib_prov_dikenal(wilayah, prov)
        daftar_kab = [k for k in daftar_kab if k["idprov"] == prov]

    potongan, meta = potong(daftar_kab, hal, batas)
    return sukses([Kabupaten(**baris) for baris in potongan], meta)


@router.get("/api/wilayah/desa", response_model=Amplop[list[DesaRingkas]])
async def daftar_desa(
    kab: Annotated[str, Query(pattern=POLA_IDKAB)],
    hal: ParamHal = 1,
    batas: ParamBatas = BATAS_BAWAAN,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[list[DesaRingkas]]:
    """Daftar desa dalam satu kabupaten — `kab` wajib (kode kabupaten 4 digit).

    `kab` yang bentuknya sah tapi tak dikenal di `simpanan.wilayah`
    menghasilkan 404 `WILAYAH_TIDAK_ADA`.
    """
    wilayah = wajib(simpanan.wilayah, "wilayah")
    desa_per_kab = wajib(simpanan.desa_per_kab, "indeks kartu ekonomi")

    wajib_kab_dikenal(wilayah, kab)

    baris = desa_per_kab.get(kab, [])
    potongan, meta = potong(baris, hal, batas)
    return sukses(
        [
            DesaRingkas(iddesa=b["iddesa"], nmdesa=b["nmdesa"], nmkec=b["nmkec"])
            for b in potongan
        ],
        meta,
    )
