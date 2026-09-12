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
from src.laporan.service import cari_citra_unggulan, rakit_ringkasan
from src.models import RESPONS_VALIDASI
from src.params import ParamIddesa

router = APIRouter(tags=["Laporan Desa"])


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
    summary="Laporan PDF Desa",
    response_description="Berkas PDF laporan desa",
    responses={**RESPONS_VALIDASI, 200: {"content": {"application/pdf": {}}}},
)
async def laporan_desa(
    request: Request,
    iddesa: ParamIddesa,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Response:
    """PDF satu desa, gabungan Peta Peran dan Kartu Ekonomi.

    Dibuat saat diminta, tanpa cache. `iddesa` yang tidak dikenal, tidak
    mempunyai data Kartu Ekonomi, atau tidak mempunyai baris Peta Peran,
    sama-sama dijawab 404 `DESA_TIDAK_ADA`.
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

    citra_unggulan = await run_in_threadpool(
        cari_citra_unggulan,
        iddesa,
        idkab,
        str(simpanan.dir_data),
        simpanan.citra_indeks,
        kartu.get("potensi"),
    )

    ringkasan = rakit_ringkasan(
        kartu,
        pp,
        request.app.state.manifest,
        _nama_provinsi(simpanan, idkab),
        citra_unggulan,
    )
    pdf = await run_in_threadpool(bangun_pdf, ringkasan)

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="laporan-desa-{iddesa}.pdf"'
        },
    )
