"""Rute pencarian desa lintas kabupaten (`GET /api/desa/cari`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.datastore import Simpanan, ambil_simpanan, wajib
from src.desa.schemas import BarisIndeksKartu
from src.desa.service import kunci_urutan
from src.models import RESPONS_VALIDASI, Amplop, sukses
from src.pagination import BATAS_BAWAAN, ParamBatas, ParamHal, potong
from src.params import POLA_IDKAB

router = APIRouter(tags=["Pencarian Desa"])


@router.get(
    "/api/desa/cari",
    response_model=Amplop[list[BarisIndeksKartu]],
    summary="Cari Desa",
    response_description="Daftar desa yang cocok, berpaginasi",
    responses=RESPONS_VALIDASI,
)
async def cari_desa(
    q: Annotated[str, Query(min_length=2)],
    kab: Annotated[str | None, Query(pattern=POLA_IDKAB)] = None,
    hal: ParamHal = 1,
    batas: ParamBatas = BATAS_BAWAAN,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[list[BarisIndeksKartu]]:
    """Cari desa lewat substring nama (`q`, tak peka kapital, minimal 2 huruf).

    Peringkat: baris yang `nmdesa`-nya berawalan `q` ditempatkan di atas
    baris yang cuma mengandung `q`, seri diurutkan menaik lewat `iddesa`.
    Filter `kab` opsional menyaring hasil ke satu kabupaten. Baris yang
    dikembalikan adalah baris indeks kartu ekonomi utuh (sudah bawa
    `idkab`+`nmkab`).
    """
    indeks_kartu = wajib(simpanan.indeks_kartu, "indeks kartu ekonomi")

    q_casefold = q.casefold()
    kandidat = [b for b in indeks_kartu if q_casefold in b["nmdesa"].casefold()]
    if kab is not None:
        kandidat = [b for b in kandidat if b["idkab"] == kab]

    kandidat_terurut = sorted(kandidat, key=lambda b: kunci_urutan(b, q_casefold))

    potongan, meta = potong(kandidat_terurut, hal, batas)
    return sukses([BarisIndeksKartu(**baris) for baris in potongan], meta)
