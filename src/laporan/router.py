"""Rute PDF Laporan Desa (`GET /api/laporan/{iddesa}`).

Dirakit dari Kartu Ekonomi Desa + baris Peta Peran setiap kali diminta,
tanpa cache (PRD §5) — bukan amplop JSON, balasannya byte PDF. Akses
dibatasi pemerintah ke atas lewat dependensi `wajib_pemerintah` yang
dipasang di titik `include_router` (`src/main.py`), bukan di berkas ini.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from src.datastore import Simpanan, ambil_simpanan, wajib
from src.exceptions import DESA_TIDAK_ADA, GalatAPI
from src.kartu.service import baca_kartu_kab
from src.laporan.pdf import bangun_pdf
from src.laporan.service import rakit_ringkasan
from src.params import ParamIddesa

router = APIRouter()


def _nama_provinsi(simpanan: Simpanan, idkab: str) -> str | None:
    """Nama provinsi dari `wilayah.json` untuk `idkab`, atau None.

    Sengaja TIDAK memakai `wajib()`: nama provinsi hanya hiasan judul
    laporan. Artefak wilayah yang hilang tidak boleh menjatuhkan rute
    menjadi 503 — kartu sudah membawa kode provinsinya sendiri sebagai
    cadangan.
    """
    wilayah = simpanan.wilayah or {}
    idprov = idkab[:2]
    for prov in wilayah.get("provinsi", []):
        if prov.get("idprov") == idprov:
            nama: str | None = prov.get("nama")
            return nama
    return None


@router.get(
    "/api/laporan/{iddesa}",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def laporan_desa(
    request: Request,
    iddesa: ParamIddesa,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Response:
    """PDF satu desa: Peta Peran + Kartu Ekonomi (PRD bagian 5).

    Dibuat saat diminta, tanpa cache. `iddesa` tak dikenal di indeks
    kartu, tak ada di berkas kartu kabupatennya, atau tak punya baris
    Peta Peran sama-sama 404 `DESA_TIDAK_ADA`.
    """
    indeks_per_desa = wajib(simpanan.indeks_per_desa, "indeks kartu ekonomi")
    baris = indeks_per_desa.get(iddesa)
    if baris is None:
        raise GalatAPI(DESA_TIDAK_ADA, f"desa {iddesa} tidak dikenal", 404)

    # Baris indeks tanpa `idkab` = indeks kartu cacat: 503 DATA_BELUM_SIAP,
    # bukan KeyError yang dilaporkan 500 GALAT_SERVER.
    idkab = wajib(baris.get("idkab"), "idkab pada indeks kartu ekonomi")
    kartu_kab = wajib(
        await run_in_threadpool(baca_kartu_kab, str(simpanan.dir_data), idkab),
        f"kartu ekonomi kab {idkab}",
    )
    kartu = kartu_kab.get(iddesa)
    if kartu is None:
        raise GalatAPI(DESA_TIDAK_ADA, f"desa {iddesa} tidak dikenal", 404)

    peta_peran_per_desa = wajib(simpanan.peta_peran_per_desa, "peta peran")
    pp = peta_peran_per_desa.get(iddesa)
    if pp is None:
        raise GalatAPI(DESA_TIDAK_ADA, f"desa {iddesa} tidak dikenal", 404)

    ringkasan = rakit_ringkasan(
        kartu, pp, request.app.state.manifest, _nama_provinsi(simpanan, idkab)
    )
    pdf = await run_in_threadpool(bangun_pdf, ringkasan)

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="laporan-desa-{iddesa}.pdf"'
        },
    )
