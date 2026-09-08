"""Skema respons pencarian desa (`GET /api/desa/cari`)."""

from src.models import ModelDasar


class BarisIndeksKartu(ModelDasar):
    """Baris indeks kartu ekonomi utuh — payload hasil pencarian desa."""

    iddesa: str
    nmdesa: str
    nmkec: str
    idkab: str
    nmkab: str
    zona: str
    keyakinan: str
    potensi_dominan: str
    desil_sp: int
    desil_sk: int
    n_program: int
