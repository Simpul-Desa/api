"""Tipe parameter query rute Citra Potensi Desa.

Deskripsi tiap parameter dipertahankan apa adanya — deskripsi terbit ke
`/openapi.json` yang merupakan bagian kontrak publik (PRD §3).
"""

from typing import Annotated

from fastapi import Query

from src.params import POLA_IDPROV

ParamProv = Annotated[
    str | None, Query(pattern=POLA_IDPROV, description="Filter provinsi (2 digit)")
]
ParamTarget = Annotated[
    str | None, Query(description="Filter target komoditas (persis)")
]
ParamProvWajib = Annotated[
    str, Query(pattern=POLA_IDPROV, description="Provinsi (2 digit), wajib")
]
ParamTargetWajib = Annotated[str, Query(min_length=1, description="Target, wajib")]
