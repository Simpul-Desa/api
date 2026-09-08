"""Skema autentikasi: identitas pemanggil yang lolos penegakan peran."""

from src.models import ModelDasar


class Identitas(ModelDasar):
    """Pemanggil terverifikasi: `id` dari klaim `sub`, `peran` dari tabel `profil`."""

    id: str
    peran: str
