"""Enumerasi varian dan tipe parameter rute Jalur Ekonomi.

Deskripsi parameter dipertahankan apa adanya — deskripsi terbit ke
`/openapi.json` yang merupakan bagian kontrak publik (PRD §3).
"""

from enum import Enum
from typing import Annotated

from fastapi import Query

from src.params import POLA_IDDESA, POLA_IDKAB


class VarianJalurEkonomi(str, Enum):
    """Varian jalur ekonomi yang didukung sebagai parameter path `varian`."""

    KOMODITAS = "komoditas"
    GUDANG_KOPDES = "gudang-kopdes"
    COLD_STORAGE = "cold-storage"
    WISATA = "wisata"


ParamKab = Annotated[
    str | None, Query(pattern=POLA_IDKAB, description="Filter kabupaten (4 digit)")
]
ParamIddesaFilter = Annotated[
    str | None,
    Query(
        pattern=POLA_IDDESA,
        description="Filter desa (poros atau anggota), 10 digit",
    ),
]
