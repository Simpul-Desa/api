"""Rute Berita Desa: daftar berita per desa dari Supabase (PRD §5).

Akses tamu ditegakkan di titik `include_router` (`main.py`) — pola yang sama
dengan empat router tamu fase 4. Respons selalu `private, no-store`
(middleware cache, PRD §5). Desa sah tanpa berita = daftar kosong, bukan 404.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from src.berita.schemas import ItemBerita
from src.berita.service import baris_berita
from src.datastore import Simpanan, ambil_simpanan, wajib
from src.exceptions import DESA_TIDAK_ADA, GalatAPI
from src.models import Amplop, sukses
from src.pagination import BATAS_BAWAAN, ParamBatas, ParamHal, potong
from src.params import POLA_IDDESA

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/berita/{iddesa}", response_model=Amplop[list[ItemBerita]])
async def berita_desa(
    request: Request,
    iddesa: Annotated[str, Path(pattern=POLA_IDDESA)],
    hal: ParamHal = 1,
    batas: ParamBatas = BATAS_BAWAAN,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[list[ItemBerita]]:
    """Daftar Berita Desa satu desa, berpaginasi, urut tanggal terbit menurun."""
    indeks_per_desa = wajib(simpanan.indeks_per_desa, "indeks kartu ekonomi")
    if iddesa not in indeks_per_desa:
        raise GalatAPI(DESA_TIDAK_ADA, f"desa {iddesa} tidak dikenal", 404)

    baris = await baris_berita(request.app.state.klien_supabase, iddesa)
    potongan, meta = potong(baris, hal, batas)
    return sukses(potongan, meta)
