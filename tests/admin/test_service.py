"""Uji unit `src/admin/service.py`: panggilan PostgREST admin (Tugas 6).

PostgREST distub lewat `httpx.MockTransport` — tidak ada jaringan asli yang
tersentuh. Tiap fungsi diuji tiga jalur: sukses (parameter/header PostgREST
yang dikirim diperiksa), balasan kosong, dan jaringan mati (503
`DATA_BELUM_SIAP`), mengikuti pola `tests/berita/test_router.py`.
"""

import json
import logging
from collections.abc import Callable, Iterator

import httpx
import pytest

from src.admin import service
from src.admin.constants import (
    BARIS_SAMPEL_PENYEGARAN,
    KOLOM_PENGGUNA,
    MAKS_DESA_PENYEGARAN_TERAKHIR,
)
from src.berita.harvest.rss import MAKS_ITEM
from src.config import ambil_pengaturan
from src.exceptions import DATA_BELUM_SIAP, GalatAPI

pytestmark = pytest.mark.anyio

SUPABASE_URL_UJI = "https://uji.supabase.co"


@pytest.fixture
def env_supabase(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isi env Supabase uji supaya URL PostgREST service admin terbentuk sah."""
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL_UJI)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "kunci-uji")
    ambil_pengaturan.cache_clear()

    yield

    ambil_pengaturan.cache_clear()


def _klien_mock(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.AsyncClient:
    """Klien httpx async yang menjawab lewat `handler`, tanpa jaringan."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# _header / _total_dari_content_range (fungsi murni)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_header_mengembalikan_apikey_dan_authorization_bearer(
    env_supabase: None,
) -> None:
    pengaturan = ambil_pengaturan()

    hasil = service._header(pengaturan)

    assert hasil == {"apikey": "kunci-uji", "Authorization": "Bearer kunci-uji"}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("nilai", "diharapkan"),
    [
        (None, 0),
        ("0-9/42", 42),
        ("*/0", 0),
        ("*/*", 0),
        ("0-0/1", 1),
    ],
)
def test_total_dari_content_range(nilai: str | None, diharapkan: int) -> None:
    assert service._total_dari_content_range(nilai) == diharapkan


# ---------------------------------------------------------------------------
# hapus_berita
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_hapus_berita_sukses_mengembalikan_true_dan_kirim_parameter_benar(
    env_supabase: None,
) -> None:
    tangkapan: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tangkapan.append(request)
        return httpx.Response(200, json=[{"id": 42}])

    async with _klien_mock(handler) as klien:
        hasil = await service.hapus_berita(klien, 42)

    assert hasil is True
    req = tangkapan[0]
    assert req.method == "DELETE"
    assert req.url.params["id"] == "eq.42"
    assert req.headers["prefer"] == "return=representation"


@pytest.mark.unit
async def test_hapus_berita_balasan_kosong_mengembalikan_false(
    env_supabase: None,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with _klien_mock(handler) as klien:
        hasil = await service.hapus_berita(klien, 99)

    assert hasil is False


@pytest.mark.unit
async def test_hapus_berita_jaringan_mati_kembalikan_503(env_supabase: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("PostgREST mati")

    async with _klien_mock(handler) as klien:
        with pytest.raises(GalatAPI) as info:
            await service.hapus_berita(klien, 1)

    assert info.value.status == 503
    assert info.value.kode == DATA_BELUM_SIAP


# ---------------------------------------------------------------------------
# daftar_pengguna
# ---------------------------------------------------------------------------

_BARIS_PENGGUNA = [
    {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "a@contoh.id",
        "peran": "tamu",
        "dibuat_pada": "2026-01-01T00:00:00+00:00",
        "diubah_pada": "2026-01-01T00:00:00+00:00",
    },
    {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "b@contoh.id",
        "peran": "admin",
        "dibuat_pada": "2026-01-02T00:00:00+00:00",
        "diubah_pada": "2026-01-02T00:00:00+00:00",
    },
]


@pytest.mark.unit
async def test_daftar_pengguna_sukses_mengirim_parameter_paginasi_dan_pencarian(
    env_supabase: None,
) -> None:
    tangkapan: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tangkapan.append(request)
        return httpx.Response(
            200, json=_BARIS_PENGGUNA, headers={"Content-Range": "0-1/2"}
        )

    async with _klien_mock(handler) as klien:
        item, total = await service.daftar_pengguna(klien, "ade", 2, 10)

    assert total == 2
    assert [i.id for i in item] == [b["id"] for b in _BARIS_PENGGUNA]
    req = tangkapan[0]
    assert req.method == "GET"
    assert req.url.params["select"] == KOLOM_PENGGUNA
    assert req.url.params["order"] == "email.asc.nullslast"
    assert req.url.params["limit"] == "10"
    assert req.url.params["offset"] == "10"  # (hal=2 - 1) * batas=10
    assert req.url.params["email"] == "ilike.*ade*"
    assert req.headers["prefer"] == "count=exact"


@pytest.mark.unit
async def test_daftar_pengguna_tanpa_q_tidak_kirim_parameter_email(
    env_supabase: None,
) -> None:
    tangkapan: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tangkapan.append(request)
        return httpx.Response(
            200, json=_BARIS_PENGGUNA, headers={"Content-Range": "0-1/2"}
        )

    async with _klien_mock(handler) as klien:
        await service.daftar_pengguna(klien, None, 1, 50)

    req = tangkapan[0]
    assert "email" not in req.url.params
    assert req.url.params["offset"] == "0"


@pytest.mark.unit
async def test_daftar_pengguna_balasan_kosong_mengembalikan_daftar_kosong_dan_total_nol(
    env_supabase: None,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[], headers={"Content-Range": "*/0"})

    async with _klien_mock(handler) as klien:
        item, total = await service.daftar_pengguna(klien, None, 1, 50)

    assert item == []
    assert total == 0


@pytest.mark.unit
async def test_daftar_pengguna_tanpa_content_range_total_tidak_kontradiksi_baris(
    env_supabase: None,
) -> None:
    """FIX 2: header Content-Range hilang TAPI baris balasan tidak kosong —
    `meta.total` tidak boleh mengaku 0 sementara `data` membawa baris.
    Floor `(hal - 1) * batas + len(baris)` dipakai: hal=3, batas=10, 5 baris
    balasan -> total >= 20 + 5 = 25, bukan 0."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_BARIS_PENGGUNA[:1] * 5)  # tanpa Content-Range

    async with _klien_mock(handler) as klien:
        _, total = await service.daftar_pengguna(klien, None, 3, 10)

    assert total == 20 + 5


@pytest.mark.unit
async def test_daftar_pengguna_content_range_usable_tidak_berubah(
    env_supabase: None,
) -> None:
    """Header yang BISA diurai tidak boleh disentuh floor FIX 2 — perilaku
    lama (nilai apa adanya dari Content-Range) tetap berlaku."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=_BARIS_PENGGUNA, headers={"Content-Range": "0-9/42"}
        )

    async with _klien_mock(handler) as klien:
        _, total = await service.daftar_pengguna(klien, None, 3, 10)

    assert total == 42


@pytest.mark.unit
async def test_daftar_pengguna_q_dengan_underscore_diescape_jadi_literal(
    env_supabase: None,
) -> None:
    """`_` adalah wildcard LIKE (satu karakter apa saja) - `john_doe` yang
    diketik admin harus dicari APA ADANYA, bukan juga mencocokkan `johnXdoe`
    (FIX 4). Ini koreksi ketepatan pencarian, bukan celah keamanan: pola
    `POLA_CARI_PENGGUNA` sudah menutup semua metakarakter filter PostgREST
    lain (`, ( ) : %`) - `_` tetap lolos pola karena bukan metakarakter
    filter, cuma metakarakter SQL LIKE.
    """
    tangkapan: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tangkapan.append(request)
        return httpx.Response(200, json=[], headers={"Content-Range": "*/0"})

    async with _klien_mock(handler) as klien:
        await service.daftar_pengguna(klien, "john_doe", 1, 50)

    assert tangkapan[0].url.params["email"] == "ilike.*john\\_doe*"


@pytest.mark.unit
async def test_daftar_pengguna_q_tanpa_metakarakter_tidak_berubah(
    env_supabase: None,
) -> None:
    """Pencarian tanpa `_`/`%`/`\\` tetap seperti sebelumnya - tidak ada
    escaping ekstra yang mengubah arti pencarian polos."""
    tangkapan: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tangkapan.append(request)
        return httpx.Response(200, json=[], headers={"Content-Range": "*/0"})

    async with _klien_mock(handler) as klien:
        await service.daftar_pengguna(klien, "john", 1, 50)

    assert tangkapan[0].url.params["email"] == "ilike.*john*"


@pytest.mark.unit
async def test_daftar_pengguna_jaringan_mati_kembalikan_503(env_supabase: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("PostgREST mati")

    async with _klien_mock(handler) as klien:
        with pytest.raises(GalatAPI) as info:
            await service.daftar_pengguna(klien, None, 1, 50)

    assert info.value.status == 503
    assert info.value.kode == DATA_BELUM_SIAP


# ---------------------------------------------------------------------------
# ubah_peran
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_ubah_peran_sukses_mengembalikan_true_dan_kirim_body_benar(
    env_supabase: None,
) -> None:
    tangkapan: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tangkapan.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "id": "00000000-0000-0000-0000-000000000001",
                    "peran": "pemerintah",
                }
            ],
        )

    async with _klien_mock(handler) as klien:
        hasil = await service.ubah_peran(
            klien, "00000000-0000-0000-0000-000000000001", "pemerintah"
        )

    assert hasil is True
    req = tangkapan[0]
    assert req.method == "PATCH"
    assert req.url.params["id"] == "eq.00000000-0000-0000-0000-000000000001"
    assert req.headers["prefer"] == "return=representation"
    body = json.loads(req.content)
    assert body["peran"] == "pemerintah"
    assert "diubah_pada" in body


@pytest.mark.unit
async def test_ubah_peran_balasan_kosong_mengembalikan_false(
    env_supabase: None,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with _klien_mock(handler) as klien:
        hasil = await service.ubah_peran(klien, "id-tak-ada", "admin")

    assert hasil is False


@pytest.mark.unit
async def test_ubah_peran_jaringan_mati_kembalikan_503(env_supabase: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("PostgREST mati")

    async with _klien_mock(handler) as klien:
        with pytest.raises(GalatAPI) as info:
            await service.ubah_peran(klien, "id", "admin")

    assert info.value.status == 503
    assert info.value.kode == DATA_BELUM_SIAP


# ---------------------------------------------------------------------------
# cacah_baris
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_cacah_baris_sukses_mengembalikan_total_dari_content_range(
    env_supabase: None,
) -> None:
    tangkapan: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tangkapan.append(request)
        return httpx.Response(
            200, json=[{"id": 1}], headers={"Content-Range": "0-0/123"}
        )

    async with _klien_mock(handler) as klien:
        total = await service.cacah_baris(klien, "profil")

    assert total == 123
    req = tangkapan[0]
    assert req.method == "GET"
    assert req.url.params["select"] == "id"
    assert req.url.params["limit"] == "1"
    # count=estimated: pada tabel besar PostgREST memakai perkiraan planner
    # dan berhenti memindai seluruh tabel hanya untuk mencetak satu angka.
    assert req.headers["prefer"] == "count=estimated"


@pytest.mark.unit
async def test_daftar_pengguna_tetap_count_exact(env_supabase: None) -> None:
    """Paginasi butuh total yang tepat — hanya `cacah_baris` yang boleh perkiraan."""
    tangkapan: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tangkapan.append(request)
        return httpx.Response(200, json=[], headers={"Content-Range": "*/0"})

    async with _klien_mock(handler) as klien:
        await service.daftar_pengguna(klien, None, 1, 50)

    assert tangkapan[0].headers["prefer"] == "count=exact"


@pytest.mark.unit
async def test_cacah_baris_balasan_kosong_mengembalikan_nol(env_supabase: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[], headers={"Content-Range": "*/0"})

    async with _klien_mock(handler) as klien:
        total = await service.cacah_baris(klien, "berita_desa")

    assert total == 0


@pytest.mark.unit
async def test_cacah_baris_tanpa_content_range_kembalikan_nol_dan_warning(
    env_supabase: None, caplog: pytest.LogCaptureFixture
) -> None:
    """Header hilang: total 0 tetap dikembalikan (bukan raise), TAPI tercatat.

    Tanpa log ini, `meta.total = 0` di samping `data` yang bisa berisi baris
    lolos tanpa jejak apa pun (FIX 3) - operator tidak pernah tahu itu terjadi.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"id": 1}])  # tanpa header Content-Range

    async with _klien_mock(handler) as klien:
        with caplog.at_level(logging.WARNING):
            total = await service.cacah_baris(klien, "profil")

    assert total == 0
    assert any(record.levelno == logging.WARNING for record in caplog.records)


@pytest.mark.unit
async def test_cacah_baris_content_range_bintang_bintang_kembalikan_nol_dan_warning(
    env_supabase: None, caplog: pytest.LogCaptureFixture
) -> None:
    """`*/*` (count tidak diminta/tidak terurai) juga harus tercatat, bukan diam."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"id": 1}], headers={"Content-Range": "*/*"})

    async with _klien_mock(handler) as klien:
        with caplog.at_level(logging.WARNING):
            total = await service.cacah_baris(klien, "profil")

    assert total == 0
    assert any(record.levelno == logging.WARNING for record in caplog.records)


@pytest.mark.unit
async def test_cacah_baris_content_range_valid_tetap_diam(
    env_supabase: None, caplog: pytest.LogCaptureFixture
) -> None:
    """Header yang bisa diurai (mis. `0-9/42`) tidak boleh memicu warning baru."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=[{"id": 1}], headers={"Content-Range": "0-9/42"}
        )

    async with _klien_mock(handler) as klien:
        with caplog.at_level(logging.WARNING):
            total = await service.cacah_baris(klien, "profil")

    assert total == 42
    assert not any(record.levelno == logging.WARNING for record in caplog.records)


@pytest.mark.unit
async def test_cacah_baris_offset_lewat_akhir_tetap_diam(
    env_supabase: None, caplog: pytest.LogCaptureFixture
) -> None:
    """`*/0` (offset lewat akhir) sudah benar sebelumnya - jangan sampai FIX 3
    mengubahnya jadi warning palsu untuk kasus yang sebetulnya sah."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[], headers={"Content-Range": "*/0"})

    async with _klien_mock(handler) as klien:
        with caplog.at_level(logging.WARNING):
            total = await service.cacah_baris(klien, "profil")

    assert total == 0
    assert not any(record.levelno == logging.WARNING for record in caplog.records)


@pytest.mark.unit
async def test_cacah_baris_jaringan_mati_kembalikan_503(env_supabase: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("PostgREST mati")

    async with _klien_mock(handler) as klien:
        with pytest.raises(GalatAPI) as info:
            await service.cacah_baris(klien, "profil")

    assert info.value.status == 503
    assert info.value.kode == DATA_BELUM_SIAP


# ---------------------------------------------------------------------------
# penyegaran_terakhir
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_penyegaran_terakhir_sukses_dedup_dan_kirim_parameter_benar(
    env_supabase: None,
) -> None:
    tangkapan: list[httpx.Request] = []
    baris = [
        {"iddesa": "3301", "dipanen_pada": "2026-09-07T03:00:00+00:00"},
        {"iddesa": "3301", "dipanen_pada": "2026-09-06T03:00:00+00:00"},  # duplikat
        {"iddesa": "3302", "dipanen_pada": "2026-09-05T03:00:00+00:00"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        tangkapan.append(request)
        return httpx.Response(200, json=baris)

    async with _klien_mock(handler) as klien:
        hasil = await service.penyegaran_terakhir(klien)

    assert [h.iddesa for h in hasil] == ["3301", "3302"]
    assert hasil[0].dipanen_pada.isoformat() == "2026-09-07T03:00:00+00:00"
    req = tangkapan[0]
    assert req.method == "GET"
    assert req.url.params["select"] == "iddesa,dipanen_pada"
    assert req.url.params["order"] == "dipanen_pada.desc"
    assert req.url.params["limit"] == str(BARIS_SAMPEL_PENYEGARAN)


@pytest.mark.unit
async def test_penyegaran_terakhir_dipotong_ke_ambang_maksimum(
    env_supabase: None,
) -> None:
    baris = [
        {"iddesa": f"33{i:02d}", "dipanen_pada": "2026-09-07T03:00:00+00:00"}
        for i in range(MAKS_DESA_PENYEGARAN_TERAKHIR + 5)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=baris)

    async with _klien_mock(handler) as klien:
        hasil = await service.penyegaran_terakhir(klien)

    assert len(hasil) == MAKS_DESA_PENYEGARAN_TERAKHIR
    assert [h.iddesa for h in hasil] == [
        b["iddesa"] for b in baris[:MAKS_DESA_PENYEGARAN_TERAKHIR]
    ]


@pytest.mark.unit
async def test_penyegaran_terakhir_balasan_kosong_mengembalikan_daftar_kosong(
    env_supabase: None,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with _klien_mock(handler) as klien:
        hasil = await service.penyegaran_terakhir(klien)

    assert hasil == []


@pytest.mark.unit
async def test_penyegaran_terakhir_jaringan_mati_kembalikan_503(
    env_supabase: None,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("PostgREST mati")

    async with _klien_mock(handler) as klien:
        with pytest.raises(GalatAPI) as info:
            await service.penyegaran_terakhir(klien)

    assert info.value.status == 503
    assert info.value.kode == DATA_BELUM_SIAP


# --- Penjaga bentuk balasan: apa pun yang bukan daftar menjadi 503 ---------
#
# Padanan `test_berita_balasan_bukan_daftar_kembalikan_503` di modul berita.
# PostgREST membalas objek (bukan daftar) untuk galat terstruktur; tanpa
# penjaga ini objek itu diteruskan ke `model_validate` dan meledak sebagai
# galat server, bukan 503 yang jujur.


@pytest.mark.unit
@pytest.mark.parametrize(
    "panggil",
    [
        pytest.param(lambda klien: service.hapus_berita(klien, 42), id="hapus_berita"),
        pytest.param(
            lambda klien: service.daftar_pengguna(klien, None, 1, 50),
            id="daftar_pengguna",
        ),
        pytest.param(
            lambda klien: service.ubah_peran(klien, "id-apa-saja", "tamu"),
            id="ubah_peran",
        ),
        pytest.param(
            lambda klien: service.penyegaran_terakhir(klien),
            id="penyegaran_terakhir",
        ),
    ],
)
async def test_balasan_bukan_daftar_kembalikan_503(
    env_supabase: None, panggil: Callable[[httpx.AsyncClient], object]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": "rusak"})

    async with _klien_mock(handler) as klien:
        with pytest.raises(GalatAPI) as info:
            await panggil(klien)  # type: ignore[misc]

    assert info.value.status == 503
    assert info.value.kode == DATA_BELUM_SIAP


@pytest.mark.unit
def test_jendela_sampel_penyegaran_cukup_untuk_sepuluh_desa_teratas() -> None:
    """Kopling tersembunyi antara dua konstanta di modul berbeda.

    `penyegaran_terakhir` menurunkan "sepuluh desa terakhir disegarkan" dari
    `BARIS_SAMPEL_PENYEGARAN` baris teratas urut `dipanen_pada desc`, memakai
    kemunculan PERTAMA per desa. Satu penyegaran menaikkan `dipanen_pada`
    paling banyak `MAKS_ITEM` baris (batas artikel per panen di `rss.py`),
    jadi sepuluh desa teratas butuh paling banyak
    `MAKS_ITEM * MAKS_DESA_PENYEGARAN_TERAKHIR` baris di dalam jendela.
    Naikkan `MAKS_ITEM` di atas 50 tanpa menaikkan jendelanya dan jawaban
    rute admin mulai SALAH tanpa galat apa pun — penjaga ini yang menangkapnya.
    """
    assert MAKS_ITEM * MAKS_DESA_PENYEGARAN_TERAKHIR <= BARIS_SAMPEL_PENYEGARAN
