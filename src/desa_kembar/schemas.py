"""Skema respons Desa Kembar (`GET /api/model/desa-kembar/{iddesa}`)."""

from src.models import ModelDasar


class TetanggaKembar(ModelDasar):
    """Satu desa tetangga dalam hasil desa kembar.

    Identitas tetangga (`nmdesa`, `nmkec`, `idkab`, `nmkab`) diambil dari
    indeks kartu ekonomi. Bila `iddesa` tetangga tidak ada di sana, keempat
    field itu bernilai `null` sementara `persen` tetap terisi.
    """

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
