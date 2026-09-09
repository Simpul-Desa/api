"""Rute Peta Peran Desa: daftar, ringkasan per kabupaten, dan detail.

Rute `ringkasan` didaftarkan SEBELUM rute berparameter `{iddesa}` (keputusan
desain #10 rencana `fase-3-endpoint-baca.plan.md`) — kalau tidak, path
literal "ringkasan" akan tertangkap pola `{iddesa}` lebih dulu dan berakhir
422 alih-alih daftar ringkasan.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends

from src.datastore import Simpanan, ambil_simpanan, wajib
from src.exceptions import DESA_TIDAK_ADA, WILAYAH_TIDAK_ADA, GalatAPI
from src.models import Amplop, sukses
from src.pagination import BATAS_BAWAAN, ParamBatas, ParamHal, potong
from src.params import ParamIddesa
from src.peta_peran.schemas import ParamKab, ParamProv, ZonaPetaPeran
from src.peta_peran.service import proyeksi_ringkas
from src.wilayah.service import wajib_kab_dikenal, wajib_prov_dikenal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/model", tags=["Peta Peran"])


@router.get("/peta-peran", response_model=Amplop[list[dict[str, Any]]])
async def daftar_peta_peran(
    prov: ParamProv = None,
    kab: ParamKab = None,
    zona: ZonaPetaPeran | None = None,
    hal: ParamHal = 1,
    batas: ParamBatas = BATAS_BAWAAN,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[list[dict[str, Any]]]:
    """Daftar baris ringkas Peta Peran Desa dengan filter `prov`/`kab`/`zona`.

    `zona`, bila diisi, harus persis salah satu dari lima nama GLOSSARY — nilai
    lain otomatis 422 lewat validasi `Literal`. `prov`/`kab`, bila diisi, harus
    dikenal di `wilayah.json` (404 `WILAYAH_TIDAK_ADA` bila tidak).
    """
    if prov is not None or kab is not None:
        wilayah = wajib(simpanan.wilayah, "wilayah")
        if prov is not None:
            wajib_prov_dikenal(wilayah, prov)
        if kab is not None:
            wajib_kab_dikenal(wilayah, kab)

    peta_peran = wajib(simpanan.peta_peran, "peta peran")
    # Kunci penyaring lewat `.get`: satu baris cacat cukup tidak cocok, bukan
    # menjatuhkan seluruh daftar. Baris yang tidak bisa diproyeksikan utuh
    # DILEWATI (bukan diberi nilai default): PRD §8 melarang kolom mutu
    # hilang dari respons, dan `None` palsu tidak bisa dibedakan pembaca dari
    # nilai kosong yang sah.
    tersaring = [
        baris
        for baris in peta_peran
        if (prov is None or baris.get("idprov") == prov)
        and (kab is None or baris.get("idkab") == kab)
        and (zona is None or baris.get("zona") == zona)
    ]
    ringkas: list[dict[str, Any]] = []
    for baris in tersaring:
        proyeksi = proyeksi_ringkas(baris)
        if proyeksi is None:
            logger.warning(
                "baris peta peran %s dilewati: kolom ringkas tidak lengkap",
                baris.get("iddesa", "<tanpa iddesa>"),
            )
            continue
        ringkas.append(proyeksi)

    potongan, meta = potong(ringkas, hal, batas)
    return sukses(potongan, meta)


@router.get("/peta-peran/ringkasan", response_model=Amplop[Any])
async def ringkasan_peta_peran(
    kab: ParamKab = None,
    hal: ParamHal = 1,
    batas: ParamBatas = BATAS_BAWAAN,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[Any]:
    """Ringkasan Peta Peran per kabupaten: satu objek (`kab=`) atau daftar semua.

    Tanpa `kab`, daftar seluruh kabupaten tetap dipaginasi (keputusan desain
    #9 — daftar kecil tetap mengisi `meta.total` dengan paginasi yang sama).
    Dengan `kab`, satu objek dikembalikan tanpa `meta`. `kab` tak dikenal di
    `ringkasan_kab.json` → 404 `WILAYAH_TIDAK_ADA`.
    """
    ringkasan_kab = wajib(simpanan.ringkasan_kab, "ringkasan kab peta peran")

    if kab is not None:
        isi = ringkasan_kab.get(kab)
        if isi is None:
            raise GalatAPI(WILAYAH_TIDAK_ADA, f"kabupaten {kab} tidak dikenal", 404)
        return sukses({"idkab": kab, **isi})

    semua = [{"idkab": idkab, **isi} for idkab, isi in ringkasan_kab.items()]
    potongan, meta = potong(semua, hal, batas)
    return sukses(potongan, meta)


@router.get("/peta-peran/{iddesa}", response_model=Amplop[dict[str, Any]])
async def detail_peta_peran(
    iddesa: ParamIddesa,
    simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
) -> Amplop[dict[str, Any]]:
    """Baris penuh Peta Peran Desa (42 kolom) apa adanya — kolom mutu data
    TIDAK disaring (PRD §8: `keyakinan`, `sumber_dominan`, dan
    `alasan_belum_terpetakan` harus tetap terlihat sebagai penjaga mutu).
    """
    peta_peran_per_desa = wajib(simpanan.peta_peran_per_desa, "peta peran")
    baris = peta_peran_per_desa.get(iddesa)
    if baris is None:
        raise GalatAPI(DESA_TIDAK_ADA, f"desa {iddesa} tidak dikenal", 404)
    return sukses(baris)
