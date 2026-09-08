"""Pembantu bersama uji autentikasi: pengaturan uji, klien mock, env Supabase."""

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastapi import Depends, FastAPI

from src.config import Pengaturan, ambil_pengaturan
from src.exceptions import daftarkan_handler

SUPABASE_URL_UJI = "https://uji.supabase.co"
SUB_UJI = "11111111-2222-3333-4444-555555555555"


def pengaturan_uji() -> Pengaturan:
    """Pengaturan dengan kredensial Supabase palsu, tanpa membaca .env."""
    return Pengaturan(
        _env_file=None,
        supabase_url=SUPABASE_URL_UJI,
        supabase_service_role_key="kunci-uji",
    )


def klien_mock(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.AsyncClient:
    """Klien httpx async yang menjawab lewat `handler`, tanpa jaringan."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def pasang_env_supabase(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isi env Supabase dan bersihkan cache `ambil_pengaturan`."""
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL_UJI)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "kunci-uji")
    ambil_pengaturan.cache_clear()


def app_uji(dependensi: Callable[..., Any]) -> FastAPI:
    """App minimal dengan satu rute `/uji` yang dijaga `dependensi`."""
    app = FastAPI()
    daftarkan_handler(app)

    @app.get("/uji", dependencies=[Depends(dependensi)])
    async def _rute() -> dict[str, str]:
        return {"ok": "ya"}

    return app
