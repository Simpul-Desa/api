"""Skema profil akun: identitas dan peran akun yang sedang masuk."""

from src.models import ModelDasar


class ProfilSaya(ModelDasar):
    """Akun yang sedang masuk: id pengguna dan perannya."""

    id: str
    peran: str
