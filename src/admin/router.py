"""Rute admin SIMPUL DESA: penyegaran berita, hapus berita, pengguna, status.

Lima rute PRD §5 fase 7. Akses admin ditegakkan di titik `include_router`
(`main.py`), pola yang sama dengan router tamu fase 3/4. Rute ubah peran
JUGA meminta dependensi `wajib_admin` secara eksplisit karena butuh nilai
`identitas.id` untuk penjaga peran-sendiri — FastAPI meng-cache dependensi
per permintaan, jadi token tidak diverifikasi dua kali. Seluruh respons
`private, no-store` lewat prefiks `/api/admin` di middleware cache.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from src.admin import jobs, service
from src.admin.constants import POLA_CARI_PENGGUNA
from src.admin.schemas import (
    BeritaTerhapus,
    CacahSistem,
    DataStatus,
    ItemPengguna,
    KonfigurasiSiap,
    PeranDiubah,
    PermintaanSegarkan,
    PermintaanUbahPeran,
    TerimaSegarkan,
)
from src.auth.dependencies import wajib_admin
from src.auth.schemas import Identitas
from src.config import ambil_pengaturan
from src.datastore import Simpanan, ambil_simpanan, wajib
from src.exceptions import (
    AKSI_DITOLAK,
    BERITA_TIDAK_ADA,
    DESA_TIDAK_ADA,
    PEKERJAAN_BERJALAN,
    PENGGUNA_TIDAK_ADA,
    GalatAPI,
)
from src.models import RESPONS_VALIDASI, Amplop, Meta, sukses
from src.pagination import BATAS_BAWAAN, ParamBatas, ParamHal

router = APIRouter(prefix="/api/admin", tags=["Administrasi"])


@router.post(
    "/berita/segarkan",
    response_model=Amplop[TerimaSegarkan],
    status_code=202,
    summary="Segarkan Berita",
    response_description="Tanda pekerjaan penyegaran sudah dimulai",
    responses=RESPONS_VALIDASI,
)
async def segarkan_berita(
    request: Request,
    body: PermintaanSegarkan,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[TerimaSegarkan]:
    """Mulai pekerjaan latar penyegaran RSS untuk daftar `iddesa` yang diminta.

    Duplikat dibuang sambil mempertahankan urutan. `iddesa` pertama yang
    tidak dikenal di indeks kartu ekonomi menghentikan permintaan sebelum
    pekerjaan apa pun dimulai (404). Hanya satu pekerjaan boleh berjalan
    pada satu waktu. Permintaan kedua ditolak (409) selama pekerjaan lain
    masih berjalan. Pekerjaan sungguhan berjalan di latar; balasan ini hanya
    menandakan pekerjaan sudah dimulai (202), bukan sudah selesai.
    """
    indeks_per_desa = wajib(simpanan.indeks_per_desa, "indeks kartu ekonomi")

    desa: list[tuple[str, str, str]] = []
    for iddesa in dict.fromkeys(body.iddesa):
        baris = indeks_per_desa.get(iddesa)
        if baris is None:
            raise GalatAPI(DESA_TIDAK_ADA, f"desa {iddesa} tidak dikenal", 404)
        desa.append((iddesa, baris["nmdesa"], baris["nmkab"]))

    if jobs.sedang_berjalan(request.app):
        raise GalatAPI(
            PEKERJAAN_BERJALAN, "pekerjaan penyegaran lain sedang berjalan", 409
        )
    pekerjaan = jobs.mulai(request.app, desa)

    return sukses(
        TerimaSegarkan(
            id_pekerjaan=pekerjaan.id_pekerjaan,
            n_desa=len(desa),
            keadaan=pekerjaan.keadaan,
        )
    )


@router.delete(
    "/berita/{id_berita}",
    response_model=Amplop[BeritaTerhapus],
    summary="Hapus Berita",
    response_description="Identitas berita yang terhapus",
    responses=RESPONS_VALIDASI,
)
async def hapus_berita(
    request: Request,
    id_berita: Annotated[int, Path(ge=1)],
) -> Amplop[BeritaTerhapus]:
    """Hapus satu berita lewat `id`; membalas 404 bila `id` tidak ada."""
    terhapus = await service.hapus_berita(request.app.state.klien_supabase, id_berita)
    if not terhapus:
        raise GalatAPI(BERITA_TIDAK_ADA, f"berita {id_berita} tidak ada", 404)
    return sukses(BeritaTerhapus(id=id_berita, terhapus=True))


@router.get(
    "/pengguna",
    response_model=Amplop[list[ItemPengguna]],
    summary="Daftar Pengguna",
    response_description="Daftar pengguna beserta perannya, berpaginasi",
    responses=RESPONS_VALIDASI,
)
async def daftar_pengguna(
    request: Request,
    q: Annotated[
        str | None,
        Query(min_length=1, max_length=64, pattern=POLA_CARI_PENGGUNA),
    ] = None,
    hal: ParamHal = 1,
    batas: ParamBatas = BATAS_BAWAAN,
) -> Amplop[list[ItemPengguna]]:
    """Daftar pengguna terdaftar beserta perannya, berpaginasi.

    `q` menyaring berdasarkan email, tanpa peka kapital dan tanpa perlu cocok
    penuh. `meta.total` adalah cacah seluruh baris yang lolos saringan, bukan
    cacah baris pada halaman ini.
    """
    # Paginasi dijalankan PostgREST lewat `limit`/`offset` — `potong()`
    # sengaja tidak dipakai karena pemotongannya sudah terjadi sisi server.
    # `Meta` tetap diisi supaya bentuk amplop identik dengan rute daftar lain.
    daftar, total = await service.daftar_pengguna(
        request.app.state.klien_supabase, q, hal, batas
    )
    return sukses(daftar, Meta(total=total, hal=hal, batas=batas))


# Penjaga peran-sendiri berjalan sebelum panggilan jaringan apa pun. Konversi
# `identitas.id` ke UUID dibungkus supaya bentuk klaim `sub` yang tidak
# kanonik tidak pernah menjadi galat server; identitas selalu UUID kanonik
# dari `ambil_peran_profil`, tapi penjagaan ini tidak bergantung pada itu.
@router.post(
    "/pengguna/{id_pengguna}/peran",
    response_model=Amplop[PeranDiubah],
    summary="Ubah Peran",
    response_description="Peran baru pengguna itu",
    responses=RESPONS_VALIDASI,
)
async def ubah_peran(
    request: Request,
    id_pengguna: uuid.UUID,
    body: PermintaanUbahPeran,
    identitas: Identitas = Depends(wajib_admin),  # noqa: B008
) -> Amplop[PeranDiubah]:
    """Ubah peran satu pengguna.

    Mengubah peran diri sendiri lewat endpoint ini ditolak 403
    `AKSI_DITOLAK`. `id_pengguna` yang tidak terdaftar dijawab 404
    `PENGGUNA_TIDAK_ADA`.
    """
    try:
        id_pemanggil = str(uuid.UUID(identitas.id))
    except ValueError:
        id_pemanggil = identitas.id

    if str(id_pengguna) == id_pemanggil:
        raise GalatAPI(
            AKSI_DITOLAK, "peran sendiri tidak bisa diubah lewat endpoint ini", 403
        )

    berhasil = await service.ubah_peran(
        request.app.state.klien_supabase, str(id_pengguna), body.peran
    )
    if not berhasil:
        raise GalatAPI(PENGGUNA_TIDAK_ADA, f"pengguna {id_pengguna} tidak ada", 404)
    return sukses(PeranDiubah(id=str(id_pengguna), peran=body.peran))


@router.get(
    "/status",
    response_model=Amplop[DataStatus],
    summary="Status Sistem",
    response_description="Ringkasan status sistem",
)
async def status_sistem(request: Request) -> Amplop[DataStatus]:
    """Status sistem: versi data, cacah isi, pekerjaan latar, dan konfigurasi.

    `konfigurasi` hanya berisi bendera boolean "sudah terisi atau belum" per
    layanan. Nilai kunci dan kredensial tidak pernah dikirim ke pemanggil.
    """
    # Tiga panggilan PostgREST per pemuatan (cacah pengguna, cacah berita,
    # penyegaran terakhir) — jangan menambah panggilan keempat tanpa alasan.
    klien = request.app.state.klien_supabase
    manifest = request.app.state.manifest
    pengaturan = ambil_pengaturan()

    cacah = CacahSistem(
        pengguna=await service.cacah_baris(klien, "profil"),
        berita=await service.cacah_baris(klien, "berita_desa"),
    )
    penyegaran_terakhir = await service.penyegaran_terakhir(klien)
    penyegaran = jobs.ke_skema(getattr(request.app.state, "pekerjaan_penyegaran", None))

    data = DataStatus(
        versi_data=manifest.get("hash") if manifest else None,
        tanggal_data=manifest.get("tanggal") if manifest else None,
        cacah=cacah,
        penyegaran=penyegaran,
        penyegaran_terakhir=penyegaran_terakhir,
        konfigurasi=KonfigurasiSiap(
            supabase=bool(
                pengaturan.supabase_url
                and pengaturan.supabase_service_role_key.get_secret_value()
            ),
            gemini=bool(pengaturan.gemini_api_key.get_secret_value()),
            gemini_chat=bool(pengaturan.gemini_api_key_chat.get_secret_value()),
        ),
    )
    return sukses(data)
