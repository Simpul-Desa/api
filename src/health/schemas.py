"""Skema respons endpoint kesehatan (`GET /health`)."""

from src.models import ModelDasar


class DataKesehatan(ModelDasar):
    """Payload data untuk endpoint `GET /health`."""

    status: str
    versi_data: str | None
    tanggal_data: str | None
