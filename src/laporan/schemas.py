"""Model dokumen Laporan Desa.

BUKAN payload HTTP: rute membalas byte PDF, bukan JSON. Model ini ada
supaya isi laporan bisa diuji tanpa mem-parse PDF - `service.py`
merakitnya, `pdf.py` merendernya.
"""

from typing import Annotated, Literal

from pydantic import Field

from src.models import ModelDasar


class BarisNilai(ModelDasar):
    label: str
    nilai: str


class SeksiRingkas(ModelDasar):
    jenis: Literal["ringkas"] = "ringkas"
    judul: str
    baris: list[BarisNilai]


class SeksiTabel(ModelDasar):
    jenis: Literal["tabel"] = "tabel"
    judul: str
    kepala: list[str]
    baris: list[list[str]]


Seksi = Annotated[SeksiRingkas | SeksiTabel, Field(discriminator="jenis")]


class RingkasanLaporan(ModelDasar):
    judul: str
    subjudul: str
    seksi: list[Seksi]
    catatan_kaki: str
