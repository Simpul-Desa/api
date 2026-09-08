"""Skema Asisten Desa: kontrak `POST /api/chat`.

`model`, `putaran_alat`, dan `peringatan` sengaja ditaruh di dalam
`DataJawaban` (jadi bagian `data`), BUKAN di `meta` amplop. `src/models.Meta`
mewajibkan `total`/`hal`/`batas` — ketiganya milik paginasi (PRD bagian 6:
"meta hanya terisi pada respons berpaginasi"), dan chat tidak berpaginasi
sama sekali. Menumpangkannya di `Meta` akan memaksa field paginasi palsu
untuk endpoint yang tidak pernah dipaginasi.
"""

from typing import Annotated, Any, Literal

from pydantic import Field

from src.config import ambil_pengaturan
from src.models import ModelDasar

# Dibaca SEKALI saat modul ini diimpor. Mengubah CHAT_MAKS_PESAN atau
# CHAT_MAKS_KARAKTER lewat environment variable di tengah proses (mis. di
# tengah sesi uji) tidak berpengaruh tanpa reload modul ini — uji ambang
# harus memakai nilai bawaan `Pengaturan`, bukan menyuntik env baru.
_pengaturan = ambil_pengaturan()


class Pesan(ModelDasar):
    """Satu giliran percakapan yang dikirim klien.

    "system" sengaja TIDAK diizinkan: `Content.role` Gemini hanya mengenal
    user/model, dan system prompt milik server, bukan klien.
    """

    role: Literal["user", "model"]
    isi: Annotated[str, Field(min_length=1, max_length=_pengaturan.chat_maks_karakter)]


class PermintaanChat(ModelDasar):
    """Badan permintaan chat. Stateless: riwayat dikirim ulang tiap kali."""

    messages: Annotated[
        list[Pesan], Field(min_length=1, max_length=_pengaturan.chat_maks_pesan)
    ]
    temperature: Annotated[float, Field(ge=0.0, le=1.0)] = 0.4


class JejakFungsi(ModelDasar):
    """Satu pemanggilan fungsi yang benar-benar terjadi - jejak asal angka."""

    fungsi: str
    argumen: dict[str, Any]
    status: Literal["sukses", "gagal"]


class DataJawaban(ModelDasar):
    """Muatan `data` respons chat, termasuk jejak dan peringatan."""

    jawaban: str
    jejak_fungsi: list[JejakFungsi]
    model: str
    putaran_alat: int
    peringatan: list[str]
