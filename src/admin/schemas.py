"""Skema modul admin: payload permintaan dan respons rute `src/admin/router.py`.

Seluruhnya turunan `ModelDasar`. `Field(min_length=..., max_length=...)` di
sini aman karena dipakai di dalam body model Pydantic, bukan di dalam
`Annotated` parameter rute FastAPI (yang melarang `default=` di dalamnya —
jebakan fase 3 di `pagination.py`).
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from src.admin.constants import MAKS_DESA_SEGARKAN
from src.models import ModelDasar
from src.params import POLA_IDDESA


class PermintaanSegarkan(ModelDasar):
    iddesa: Annotated[
        list[Annotated[str, StringConstraints(pattern=POLA_IDDESA)]],
        Field(min_length=1, max_length=MAKS_DESA_SEGARKAN),
    ]


class TerimaSegarkan(ModelDasar):
    id_pekerjaan: str
    n_desa: int
    keadaan: str


# `n_gagal` (FIX 1) memisahkan artikel yang melempar galat saat diolah dari
# `n_dibuang` (penolakan editorial saring/verifikasi); lihat docstring
# `HasilPanen` di `src/berita/schemas.py`.
class HasilPenyegaranDesa(ModelDasar):
    """Ringkasan satu desa dalam badan `/api/admin/status`.

    `n_gagal` menghitung artikel yang gagal diproses karena galat, terpisah
    dari `n_dibuang` yang menghitung artikel yang ditolak saat penyaringan
    atau verifikasi editorial.
    """

    iddesa: str
    n_baru: int
    n_duplikat: int
    n_dibuang: int
    n_gagal: int
    galat: str | None


class StatusPekerjaan(ModelDasar):
    id_pekerjaan: str
    keadaan: Literal["berjalan", "selesai"]
    total: int
    selesai: int
    mulai_pada: datetime
    selesai_pada: datetime | None
    hasil: list[HasilPenyegaranDesa]


class BeritaTerhapus(ModelDasar):
    id: int
    terhapus: bool


class ItemPengguna(ModelDasar):
    id: str
    email: str | None
    peran: str
    dibuat_pada: datetime
    diubah_pada: datetime


class PermintaanUbahPeran(ModelDasar):
    peran: Literal["tamu", "pemerintah", "swasta", "admin"]


class PeranDiubah(ModelDasar):
    id: str
    peran: str


class CacahSistem(ModelDasar):
    pengguna: int
    berita: int


class PenyegaranDesa(ModelDasar):
    iddesa: str
    dipanen_pada: datetime


# `gemini` = kunci panen Berita Desa (`GEMINI_API_KEY`). `gemini_chat` =
# kunci Asisten Desa (`GEMINI_API_KEY_CHAT`). Keduanya sengaja terpisah
# supaya kuota Gemini tidak saling menghabiskan (lihat
# `Pengaturan.gemini_api_key_chat`): satu penyegaran berita besar tidak
# boleh menghabiskan kuota yang sedang dipakai pengguna chat, dan
# sebaliknya. `gemini` tidak dinamai ulang menjadi `gemini_berita` di sini
# karena itu memutus kontrak respons `/api/admin/status` sejak fase 7.
# `gemini_chat` adalah penambahan aditif.
class KonfigurasiSiap(ModelDasar):
    """Bendera boolean kesiapan konfigurasi untuk halaman `/admin`.

    `gemini` menandai kunci API untuk panen Berita Desa, `gemini_chat`
    untuk Asisten Desa. Keduanya kunci terpisah, jadi satu bisa terisi
    sementara yang lain belum.
    """

    supabase: bool
    gemini: bool
    gemini_chat: bool


class DataStatus(ModelDasar):
    versi_data: str | None
    tanggal_data: str | None
    cacah: CacahSistem
    penyegaran: StatusPekerjaan | None
    penyegaran_terakhir: list[PenyegaranDesa]
    konfigurasi: KonfigurasiSiap
