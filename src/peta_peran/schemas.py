"""Tipe parameter dan enumerasi zona rute Peta Peran Desa.

Deskripsi parameter dipertahankan apa adanya — deskripsi terbit ke
`/openapi.json` yang merupakan bagian kontrak publik (PRD §3). Lima nama
zona persis mengikuti GLOSSARY akar; nilai lain otomatis 422.
"""

from typing import Annotated, Literal

from fastapi import Query

from src.params import POLA_IDKAB, POLA_IDPROV

ParamProv = Annotated[
    str | None, Query(pattern=POLA_IDPROV, description="Kode provinsi 2 digit")
]
ParamKab = Annotated[
    str | None, Query(pattern=POLA_IDKAB, description="Kode kabupaten 4 digit")
]

ZonaPetaPeran = Literal[
    "Zona Pemerintah",
    "Zona Mitra",
    "Zona Poros",
    "Zona Bantuan",
    "Belum Terpetakan",
]
