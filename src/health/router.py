"""Rute kesehatan (health check) untuk memantau status API dan data panen."""

from typing import Any

from fastapi import APIRouter, Request

from src.health.schemas import DataKesehatan
from src.models import Amplop, sukses

router = APIRouter(tags=["Kesehatan"])


# `HEAD` didaftarkan sebagai rute KEDUA di luar skema, bukan lewat satu
# `api_route(methods=["GET", "HEAD"])`: FastAPI menghitung `unique_id`
# per-rute, bukan per-metode, sehingga satu rute dua metode membuat `get` dan
# `head` berbagi `operationId` yang sama di `/openapi.json` — kontrak publik
# yang dibaca `dokumentasi/` jadi rusak. Pendaftaran terpisah juga menjaga
# `/openapi.json` persis seperti sebelumnya.
#
# `HEAD` perlu didaftarkan sama sekali karena FastAPI mendaftarkan persis
# metode yang diminta dan TIDAK menambahkannya otomatis seperti `Route` bawaan
# Starlette — tanpa ini `HEAD /health` membalas 405. Badan respons dipotong
# server HTTP (h11), handler tidak perlu membedakan keduanya.
#
# Manifest yang belum termuat (`request.app.state.manifest is None`) tetap 200
# dengan kedua field bernilai None — sengaja, bukan 503: rute ini dipakai
# pemantau untuk membedakan "proses hidup" dari "data siap".
@router.get("/health", response_model=Amplop[DataKesehatan])
@router.head("/health", response_model=Amplop[DataKesehatan], include_in_schema=False)
async def kesehatan(request: Request) -> Amplop[DataKesehatan]:
    """Kembalikan status hidup API beserta versi dan tanggal data panen.

    Selalu membalas 200, termasuk ketika salinan data belum termuat di
    server — dalam kondisi itu `versi_data` dan `tanggal_data` bernilai
    `null`, jadi keduanya sekaligus penanda kesiapan data.

    `HEAD /health` juga dilayani, dengan badan respons dipotong.
    """
    manifest: dict[str, Any] | None = request.app.state.manifest

    data = DataKesehatan(
        status="hidup",
        versi_data=manifest.get("hash") if manifest else None,
        tanggal_data=manifest.get("tanggal") if manifest else None,
    )
    return sukses(data)
