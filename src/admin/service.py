"""Akses data PostgREST untuk rute admin: pengguna, peran, hapus berita, cacah.

Klien async milik `app.state.klien_supabase` dipakai di sini, mengikuti pola
`src/berita/service.py`. Kegagalan jaringan, status galat, atau balasan
berbentuk asing selalu menjadi 503 `DATA_BELUM_SIAP` — divalidasi di batas,
tidak pernah diteruskan apa adanya ke pemanggil rute.
"""

import logging
from datetime import UTC, datetime

import httpx
from pydantic import ValidationError

from src.admin.constants import (
    BARIS_SAMPEL_PENYEGARAN,
    KOLOM_PENGGUNA,
    MAKS_DESA_PENYEGARAN_TERAKHIR,
)
from src.admin.schemas import ItemPengguna, PenyegaranDesa
from src.config import Pengaturan, ambil_pengaturan
from src.exceptions import DATA_BELUM_SIAP, GalatAPI

logger = logging.getLogger(__name__)

_GALAT_LAYANAN = "layanan data admin tidak terjangkau"


def _header(pengaturan: Pengaturan) -> dict[str, str]:
    """Header service-role PostgREST; kunci tidak pernah masuk log."""
    kunci = pengaturan.supabase_service_role_key.get_secret_value()
    return {"apikey": kunci, "Authorization": f"Bearer {kunci}"}


def _escape_like(q: str) -> str:
    """Escape metakarakter SQL LIKE (`_` dan `%`) supaya `q` dicari literal.

    `POLA_CARI_PENGGUNA` sudah menutup metakarakter filter PostgREST
    (`, ( ) : %`, dsb.) - ini BUKAN perbaikan keamanan/injeksi, `_` cuma
    wildcard LIKE "satu karakter apa saja" yang lolos pola karena bukan
    metakarakter filter. Backslash WAJIB diescape lebih dulu: kalau `_`/`%`
    diescape duluan, backslash yang baru disisipkan ikut ter-escape lagi di
    langkah berikutnya dan pola jadi dobel-escape (rusak).
    """
    return q.replace("\\", "\\\\").replace("_", "\\_").replace("%", "\\%")


def _total_dari_content_range(nilai: str | None) -> int:
    """Ambil total baris dari header `Content-Range` PostgREST.

    Bentuknya `0-9/42` (total 42 baris), `*/0` (hasil kosong), atau `*/*`
    (count tidak diminta). Bagian setelah "/" yang bukan digit dianggap
    0 baris; header yang tidak ada juga 0.
    """
    if nilai is None:
        # Header hilang: mungkin `Prefer: count=exact` diabaikan PostgREST atau
        # proxy di depannya menyaring header. Total 0 tetap dikembalikan (bukan
        # raise - lihat docstring modul), tapi divergensi `meta.total` vs
        # `data` yang bisa non-kosong wajib tercatat, tidak boleh diam.
        logger.warning("header Content-Range tidak ada, total dianggap 0")
        return 0
    bagian = nilai.split("/")[-1]
    if not bagian.isdigit():
        # `*/*` (count tidak diminta) atau bentuk lain yang tidak terurai -
        # sama seperti header hilang: tetap 0, tapi tercatat supaya kelihatan.
        logger.warning(
            "header Content-Range %r tidak bisa diurai, total dianggap 0", nilai
        )
        return 0
    return int(bagian)


async def hapus_berita(klien: httpx.AsyncClient, id_berita: int) -> bool:
    """Hapus satu baris `berita_desa` lewat `id`; `False` bila tidak ada."""
    pengaturan = ambil_pengaturan()
    try:
        respons = await klien.delete(
            f"{pengaturan.supabase_url}/rest/v1/berita_desa",
            params={"id": f"eq.{id_berita}"},
            headers={**_header(pengaturan), "Prefer": "return=representation"},
        )
        respons.raise_for_status()
        baris = respons.json()
        if not isinstance(baris, list):
            raise TypeError(f"bentuk balasan hapus berita: {type(baris).__name__}")
        return len(baris) > 0
    except (httpx.HTTPError, TypeError, ValueError, ValidationError) as exc:
        logger.warning("PostgREST hapus berita tidak terjangkau atau rusak: %s", exc)
        raise GalatAPI(DATA_BELUM_SIAP, _GALAT_LAYANAN, 503) from exc


async def daftar_pengguna(
    klien: httpx.AsyncClient, q: str | None, hal: int, batas: int
) -> tuple[list[ItemPengguna], int]:
    """Daftar `profil` terpaginasi sisi server, opsional disaring `q` (ilike email)."""
    pengaturan = ambil_pengaturan()
    parameter: dict[str, str] = {
        "select": KOLOM_PENGGUNA,
        "order": "email.asc.nullslast",
        "limit": str(batas),
        "offset": str((hal - 1) * batas),
    }
    if q:
        parameter["email"] = f"ilike.*{_escape_like(q)}*"
    try:
        respons = await klien.get(
            f"{pengaturan.supabase_url}/rest/v1/profil",
            params=parameter,
            headers={**_header(pengaturan), "Prefer": "count=exact"},
        )
        respons.raise_for_status()
        baris = respons.json()
        if not isinstance(baris, list):
            raise TypeError(f"bentuk balasan daftar pengguna: {type(baris).__name__}")
        total = _total_dari_content_range(respons.headers.get("content-range"))
        if total == 0 and baris:
            # FIX 2: header tak terurai/hilang TAPI baris balasan tidak kosong
            # — `meta.total = 0` di samping `data` berisi baris adalah
            # kontradiksi yang lebih menyesatkan daripada angka perkiraan.
            # Floor ini BUKAN total sebenarnya (baris di halaman berikutnya
            # tidak diketahui), hanya batas bawah yang dijamin >= baris yang
            # sungguh dikembalikan, dipilih supaya `meta.total` tidak pernah
            # lebih kecil dari `len(data)`.
            total = (hal - 1) * batas + len(baris)
        return [ItemPengguna.model_validate(b) for b in baris], total
    except (httpx.HTTPError, TypeError, ValueError, ValidationError) as exc:
        logger.warning("PostgREST daftar pengguna tidak terjangkau atau rusak: %s", exc)
        raise GalatAPI(DATA_BELUM_SIAP, _GALAT_LAYANAN, 503) from exc


async def ubah_peran(klien: httpx.AsyncClient, id_pengguna: str, peran: str) -> bool:
    """Ubah `peran` satu baris `profil`; `False` bila `id_pengguna` tidak ada."""
    pengaturan = ambil_pengaturan()
    try:
        respons = await klien.patch(
            f"{pengaturan.supabase_url}/rest/v1/profil",
            params={"id": f"eq.{id_pengguna}"},
            json={"peran": peran, "diubah_pada": datetime.now(UTC).isoformat()},
            headers={**_header(pengaturan), "Prefer": "return=representation"},
        )
        respons.raise_for_status()
        baris = respons.json()
        if not isinstance(baris, list):
            raise TypeError(f"bentuk balasan ubah peran: {type(baris).__name__}")
        return len(baris) > 0
    except (httpx.HTTPError, TypeError, ValueError, ValidationError) as exc:
        logger.warning("PostgREST ubah peran tidak terjangkau atau rusak: %s", exc)
        raise GalatAPI(DATA_BELUM_SIAP, _GALAT_LAYANAN, 503) from exc


async def cacah_baris(klien: httpx.AsyncClient, tabel: str) -> int:
    """Total baris `tabel` lewat header `Content-Range`, tanpa mengunduh isinya.

    Memakai `count=estimated`, BUKAN `count=exact`: hitungan tepat memaksa
    Postgres memindai seluruh tabel, dan `/api/admin/status` memanggil fungsi
    ini dua kali setiap kali halaman dimuat, sementara `berita_desa` sengaja
    tanpa batas retensi (lihat migrasi 20260907130000). `estimated` memakai
    perkiraan planner hanya bila melewati ambang PostgREST dan jatuh ke
    hitungan tepat di bawahnya, jadi tabel kecil tetap akurat. Konsekuensi
    yang diterima: begitu tabel besar, cacah yang dilihat admin adalah
    perkiraan. Paginasi `daftar_pengguna` TETAP `count=exact` — di sana
    totalnya menentukan jumlah halaman.
    """
    pengaturan = ambil_pengaturan()
    try:
        respons = await klien.get(
            f"{pengaturan.supabase_url}/rest/v1/{tabel}",
            params={"select": "id", "limit": "1"},
            headers={**_header(pengaturan), "Prefer": "count=estimated"},
        )
        respons.raise_for_status()
        return _total_dari_content_range(respons.headers.get("content-range"))
    except (httpx.HTTPError, TypeError, ValueError, ValidationError) as exc:
        logger.warning("PostgREST cacah baris tidak terjangkau atau rusak: %s", exc)
        raise GalatAPI(DATA_BELUM_SIAP, _GALAT_LAYANAN, 503) from exc


async def penyegaran_terakhir(klien: httpx.AsyncClient) -> list[PenyegaranDesa]:
    """Penyegaran terakhir per desa: kemunculan pertama, dipotong ke ambang."""
    pengaturan = ambil_pengaturan()
    try:
        respons = await klien.get(
            f"{pengaturan.supabase_url}/rest/v1/berita_desa",
            params={
                "select": "iddesa,dipanen_pada",
                "order": "dipanen_pada.desc",
                "limit": str(BARIS_SAMPEL_PENYEGARAN),
            },
            headers=_header(pengaturan),
        )
        respons.raise_for_status()
        baris = respons.json()
        if not isinstance(baris, list):
            raise TypeError(
                f"bentuk balasan penyegaran terakhir: {type(baris).__name__}"
            )
        dilihat: set[str] = set()
        hasil: list[PenyegaranDesa] = []
        for b in baris:
            item = PenyegaranDesa.model_validate(b)
            if item.iddesa in dilihat:
                continue
            dilihat.add(item.iddesa)
            hasil.append(item)
            if len(hasil) >= MAKS_DESA_PENYEGARAN_TERAKHIR:
                break
        return hasil
    except (httpx.HTTPError, TypeError, ValueError, ValidationError) as exc:
        logger.warning(
            "PostgREST penyegaran terakhir tidak terjangkau atau rusak: %s", exc
        )
        raise GalatAPI(DATA_BELUM_SIAP, _GALAT_LAYANAN, 503) from exc
