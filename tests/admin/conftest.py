"""Fixture khusus uji rute admin.

Fixture ditaruh di sini, bukan di `tests/admin/bantu.py`: fixture yang
diimpor dari modul biasa hanya dikenali pytest bila namanya ikut terimpor
ke berkas uji, dan impor itu terbaca sebagai impor tak terpakai oleh ruff.
Pembantu yang berupa fungsi biasa tetap di `bantu.py`.
"""

from collections.abc import Iterator

import pytest

from src.config import ambil_pengaturan


@pytest.fixture
def env_admin(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isi env Supabase dan Gemini uji, lalu bersihkan cache pengaturan.

    `GEMINI_API_KEY` ikut diisi karena `GET /api/admin/status` melaporkan
    kesiapan konfigurasi sebagai bendera boolean — nilainya sendiri tidak
    pernah dikirim ke klien.
    """
    monkeypatch.setenv("SUPABASE_URL", "https://uji.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "kunci-uji")
    monkeypatch.setenv("GEMINI_API_KEY", "kunci-gemini-uji")
    ambil_pengaturan.cache_clear()

    yield

    ambil_pengaturan.cache_clear()
