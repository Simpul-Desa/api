"""Skema respons Desa Kembar (`GET /api/model/desa-kembar/{iddesa}`)."""

from src.models import ModelDasar


class TetanggaKembar(ModelDasar):
    """Satu tetangga desa kembar; identitas di-join dari indeks kartu ekonomi."""

    iddesa: str
    nmdesa: str | None
    nmkec: str | None
    idkab: str | None
    nmkab: str | None
    persen: float


class DataDesaKembar(ModelDasar):
    """Payload data untuk `GET /api/model/desa-kembar/{iddesa}`."""

    iddesa: str
    tetangga: list[TetanggaKembar]
    keterangan: str | None = None
