"""Skema respons rute wilayah (provinsi, kabupaten, desa, ringkasan)."""

from typing import Annotated

from pydantic import Field

from src.models import ModelDasar


class Provinsi(ModelDasar):
    """Satu baris provinsi dari `wilayah.json`."""

    idprov: str
    nama: str


class Kabupaten(ModelDasar):
    """Satu baris kabupaten dari `wilayah.json`."""

    idkab: str
    nmkab: str
    idprov: str


class DesaRingkas(ModelDasar):
    """Baris ringkas desa untuk daftar `GET /api/wilayah/desa`."""

    iddesa: str
    nmdesa: str
    nmkec: str


class PerProvinsiRingkasan(ModelDasar):
    """Rincian satu provinsi di dalam ringkasan wilayah."""

    idprov: str
    nama: str
    n_kabupaten: int
    n_desa: int


class RingkasanWilayah(ModelDasar):
    """Payload `GET /api/wilayah/ringkasan` — dihitung sekali saat startup."""

    n_provinsi: int
    n_kabupaten: int
    n_desa: int
    per_provinsi: list[PerProvinsiRingkasan]


class PusatKabupaten(ModelDasar):
    """Pusat peta satu kabupaten + cacah desanya."""

    idkab: str
    nmkab: str
    idprov: str
    pusat: Annotated[list[float], Field(min_length=2, max_length=2)]  # [lng, lat]
    n_desa: int


class PusatProvinsi(ModelDasar):
    """Pusat peta satu provinsi (rerata kabupaten) + cacahnya."""

    idprov: str
    nama: str
    pusat: Annotated[list[float], Field(min_length=2, max_length=2)]  # [lng, lat]
    n_desa: int
    n_kabupaten: int


class PusatWilayah(ModelDasar):
    """Payload `GET /api/wilayah/pusat` untuk lingkaran berjenjang `app/`."""

    provinsi: list[PusatProvinsi]
    kabupaten: list[PusatKabupaten]
