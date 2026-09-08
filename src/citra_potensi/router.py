"""Rute Citra Potensi Desa: daftar sel model dan detail sel.

`GET /api/model/citra-potensi` mengembalikan metadata sel indeks (paginasi,
filter opsional `prov`/`target`). `GET /api/model/citra-potensi/sel` (kedua
parameter wajib) mengembalikan metadata sel + `format_skor` + `skor` dari
berkas produksi — blok `meta`/`validasi`/`model` internal berkas TIDAK ikut
(PRD §5: "berkas produksi tidak pernah dikirim utuh").
"""

from typing import Any

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from src.citra_potensi.schemas import (
    ParamProv,
    ParamProvWajib,
    ParamTarget,
    ParamTargetWajib,
)
from src.citra_potensi.service import baca_sel_citra
from src.datastore import Simpanan, ambil_simpanan, wajib
from src.exceptions import TIDAK_DITEMUKAN, GalatAPI
from src.models import Amplop, sukses
from src.pagination import BATAS_BAWAAN, ParamBatas, ParamHal, potong

router = APIRouter(prefix="/api/model/citra-potensi", tags=["citra-potensi"])


@router.get("", response_model=Amplop[list[dict[str, Any]]])
async def daftar_sel(
    prov: ParamProv = None,
    target: ParamTarget = None,
    hal: ParamHal = 1,
    batas: ParamBatas = BATAS_BAWAAN,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[list[dict[str, Any]]]:
    """Daftar sel citra potensi (metadata saja), filter opsional `prov`/`target`."""
    citra_indeks = wajib(simpanan.citra_indeks, "indeks citra potensi")

    sel: list[dict[str, Any]] = citra_indeks.get("sel", [])
    # `.get` pada kunci penyaring: satu entri sel cacat cukup TIDAK cocok
    # dengan filter, bukan menjatuhkan seluruh daftar jadi 500.
    if prov is not None:
        sel = [s for s in sel if s.get("prov") == prov]
    if target is not None:
        sel = [s for s in sel if s.get("target") == target]

    potongan, meta = potong(sel, hal, batas)
    return sukses(potongan, meta)


@router.get("/sel", response_model=Amplop[dict[str, Any]])
async def detail_sel(
    prov: ParamProvWajib,
    target: ParamTargetWajib,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[dict[str, Any]]:
    """Detail satu sel: metadata indeks + `format_skor` + `skor` berkas produksi."""
    citra_indeks = wajib(simpanan.citra_indeks, "indeks citra potensi")

    sel = next(
        (
            s
            for s in citra_indeks.get("sel", [])
            if s.get("prov") == prov and s.get("target") == target
        ),
        None,
    )
    if sel is None:
        raise GalatAPI(
            TIDAK_DITEMUKAN,
            f"sel citra potensi prov={prov} target={target} tidak ditemukan",
            404,
        )

    isi = wajib(
        await run_in_threadpool(baca_sel_citra, str(simpanan.dir_data), sel["berkas"]),
        f"sel citra potensi {sel['berkas']}",
    )

    # Berkas produksi tanpa `format_skor`/`skor` bukan berkas skor sel:
    # 503 DATA_BELUM_SIAP, bukan KeyError yang dilaporkan 500.
    data = {
        **sel,
        "format_skor": wajib(
            isi.get("format_skor"), f"format skor sel citra potensi {sel['berkas']}"
        ),
        "skor": wajib(isi.get("skor"), f"skor sel citra potensi {sel['berkas']}"),
    }
    return sukses(data)
