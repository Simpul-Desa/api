"""Skema respons rute wilayah (provinsi, kabupaten, desa, ringkasan)."""

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
