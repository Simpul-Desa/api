"""Rute profil akun: identitas dan peran akun yang sedang masuk (PRD §5).

Akses tamu ditegakkan di TANDA TANGAN handler (bukan di `include_router`),
karena nilai `Identitas`-nya dipakai langsung sebagai isi respons. Respons
selalu `private, no-store` (middleware cache, PRD §5).
"""

from fastapi import APIRouter, Depends

from src.auth.dependencies import wajib_tamu
from src.auth.schemas import Identitas
from src.models import Amplop, sukses
from src.profil.schemas import ProfilSaya

router = APIRouter(tags=["Akun"])


@router.get(
    "/api/profil/saya",
    response_model=Amplop[ProfilSaya],
    summary="Profil akun yang sedang masuk",
    response_description="Id dan peran akun pemanggil",
)
async def profil_saya(
    identitas: Identitas = Depends(wajib_tamu),  # noqa: B008
) -> Amplop[ProfilSaya]:
    """Kembalikan id dan peran akun pemanggil, dibaca dari tabel `profil`."""
    return sukses(ProfilSaya(id=identitas.id, peran=identitas.peran))
