"""Akses data Berita Desa untuk jalur baca: SELECT PostgREST per desa.

Klien async milik `app.state` dipakai di sini; jalur panen memakai klien
sinkron sendiri di `harvest/store.py` karena berjalan di threadpool.
"""

import logging

import httpx
from pydantic import ValidationError

from src.berita.constants import KOLOM
from src.berita.schemas import ItemBerita
from src.config import ambil_pengaturan
from src.exceptions import DATA_BELUM_SIAP, GalatAPI

logger = logging.getLogger(__name__)


async def baris_berita(klien: httpx.AsyncClient, iddesa: str) -> list[ItemBerita]:
    """Seluruh berita `iddesa` dari PostgREST, urut `terbit_pada` menurun.

    Kegagalan jaringan, balasan bukan daftar, atau baris berbentuk asing
    seluruhnya menjadi 503 `DATA_BELUM_SIAP` — data eksternal divalidasi di
    batas, bukan diteruskan.
    """
    pengaturan = ambil_pengaturan()
    kunci = pengaturan.supabase_service_role_key.get_secret_value()
    try:
        respons = await klien.get(
            f"{pengaturan.supabase_url}/rest/v1/berita_desa",
            params={
                "iddesa": f"eq.{iddesa}",
                "select": KOLOM,
                "order": "terbit_pada.desc.nullslast",
            },
            headers={"apikey": kunci, "Authorization": f"Bearer {kunci}"},
        )
        respons.raise_for_status()
        baris = respons.json()
        if not isinstance(baris, list):
            raise TypeError(f"bentuk balasan berita: {type(baris).__name__}")
        return [ItemBerita.model_validate(b) for b in baris]
    except (httpx.HTTPError, TypeError, ValueError, ValidationError) as exc:
        logger.warning("PostgREST berita tidak terjangkau atau rusak: %s", exc)
        raise GalatAPI(DATA_BELUM_SIAP, "data berita tidak terjangkau", 503) from exc
