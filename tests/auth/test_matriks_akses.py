"""Uji integrasi matriks akses PRD akar §3 pada aplikasi nyata (fase 4).

Berbeda dari fixture `klien` (yang meng-override `wajib_tamu` menjadi tamu
supaya uji fase 1-3 tetap jalan), seluruh uji di berkas ini memakai
`klien_matriks` TANPA override — verifikasi token dan pembacaan peran
berjalan sungguhan, hanya kunci JWKS dan lookup PostgREST-nya yang distub:

- `_kunci_penandatangan` → kunci publik ES256 uji (fixture `kunci_es256`);
- `ambil_peran_profil` → peta `sub` → peran di memori (`_PERAN_PER_SUB`).
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

import src.auth.service
from src.config import Pengaturan, ambil_pengaturan
from src.main import create_app
from tests.conftest import D1, PembuatKlien

pytestmark = pytest.mark.anyio

SUPABASE_URL_UJI = "https://uji.supabase.co"

SUB_TAMU = "00000000-0000-0000-0000-000000000001"
SUB_PEMERINTAH = "00000000-0000-0000-0000-000000000002"
SUB_SWASTA = "00000000-0000-0000-0000-000000000003"
SUB_ADMIN = "00000000-0000-0000-0000-000000000004"
SUB_TANPA_PROFIL = "00000000-0000-0000-0000-000000000009"
SUB_PERAN_ASING = "00000000-0000-0000-0000-000000000008"

_PERAN_PER_SUB: dict[str, str] = {
    SUB_PERAN_ASING: "penyusup",
    SUB_TAMU: "tamu",
    SUB_PEMERINTAH: "pemerintah",
    SUB_SWASTA: "swasta",
    SUB_ADMIN: "admin",
}

# Satu rute wakil per router tamu (empat router fase 3 yang ditutup fase 4).
RUTE_TAMU = (
    "/api/model/peta-peran",
    "/api/model/citra-potensi",
    "/api/model/jalur-ekonomi/komoditas",
    f"/api/model/desa-kembar/{D1}",
    f"/api/berita/{D1}",
)

# Rute wakil tiap router anonim — harus tetap 200 tanpa token.
RUTE_ANONIM = (
    "/health",
    "/api/wilayah/provinsi",
    "/api/desa/cari?q=desa",
    f"/api/model/kartu/{D1}",
    "/api/geo/desa/1801",
)

# Rute wakil router admin (fase 7) — gerbangnya `wajib_admin`, bukan `wajib_tamu`.
RUTE_ADMIN = (
    ("POST", "/api/admin/berita/segarkan"),
    ("DELETE", "/api/admin/berita/1"),
    ("GET", "/api/admin/pengguna"),
    ("POST", f"/api/admin/pengguna/{SUB_TAMU}/peran"),
    ("GET", "/api/admin/status"),
)

# Rute laporan (fase 8) — gerbangnya `wajib_pemerintah`, satu-satunya rute
# yang memutus pewarisan peran: swasta punya seluruh akses tamu tetapi
# TIDAK punya laporan. Sengaja bukan bagian RUTE_TAMU maupun RUTE_ADMIN.
RUTE_LAPORAN = f"/api/laporan/{D1}"

# Rute chat (fase 5) — gerbangnya `wajib_di_atas_tamu`: semua peran login
# KECUALI tamu (PRD akar bagian 3). Sengaja bukan bagian RUTE_TAMU (tamu
# DITOLAK, bukan diizinkan di sini) maupun RUTE_ADMIN (bukan admin-saja).
RUTE_CHAT = (("POST", "/api/chat"),)


async def _peran_stub(
    klien: httpx.AsyncClient, pengaturan: Pengaturan, id_pengguna: str
) -> str | None:
    """Stub `ambil_peran_profil`: baca peta di memori, tanpa jaringan."""
    return _PERAN_PER_SUB.get(id_pengguna)


@pytest.fixture
def auth_stub(
    monkeypatch: pytest.MonkeyPatch, kunci_es256: tuple[str, Any]
) -> Iterator[None]:
    """Stub kunci JWKS + lookup profil dan isi env Supabase uji.

    Verifikasi tanda tangan, aud, iss, dan exp tetap berjalan sungguhan
    lewat `verifikasi_token` — hanya sumber kunci dan PostgREST yang diganti.
    """
    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        src.auth.service,
        "_kunci_penandatangan",
        lambda token, pengaturan: kunci_publik,
    )
    monkeypatch.setattr(src.auth.service, "ambil_peran_profil", _peran_stub)
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL_UJI)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "kunci-uji")
    ambil_pengaturan.cache_clear()

    yield

    ambil_pengaturan.cache_clear()


@pytest.fixture
async def klien_matriks(
    dir_data_lengkap: Path, auth_stub: None, buat_klien: PembuatKlien
) -> httpx.AsyncClient:
    """Klien aplikasi nyata TANPA override dependensi peran.

    `klien_supabase` diganti transport tiruan yang menjawab daftar kosong:
    rute berita (fase 6) butuh PostgREST untuk 200 — yang diuji berkas ini
    matriks aksesnya, bukan datanya. Penggantian dilakukan SETELAH lifespan
    berjalan, supaya klien sungguhan yang dipasang lifespan tertimpa.
    """
    app = create_app()
    klien = await buat_klien(app, lifespan=True)
    app.state.klien_supabase = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[]))
    )
    return klien


def _header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Anonim vs rute tamu ------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("rute", RUTE_TAMU)
async def test_anonim_ke_rute_tamu_kembalikan_401(
    rute: str, klien_matriks: httpx.AsyncClient
) -> None:
    respons = await klien_matriks.get(rute)

    assert respons.status_code == 401
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "TIDAK_BERWENANG"


@pytest.mark.integration
@pytest.mark.parametrize("rute", RUTE_ANONIM)
async def test_anonim_ke_rute_anonim_tetap_200(
    rute: str, klien_matriks: httpx.AsyncClient
) -> None:
    respons = await klien_matriks.get(rute)

    assert respons.status_code == 200


# --- Peran sah + pewarisan ----------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("rute", RUTE_TAMU)
async def test_token_tamu_ke_rute_tamu_kembalikan_200(
    rute: str, klien_matriks: httpx.AsyncClient, buat_token: Callable[..., str]
) -> None:
    token = buat_token(SUB_TAMU)

    respons = await klien_matriks.get(rute, headers=_header(token))

    assert respons.status_code == 200
    assert respons.json()["sukses"] is True


@pytest.mark.integration
@pytest.mark.parametrize("rute", RUTE_TAMU)
@pytest.mark.parametrize("sub", [SUB_PEMERINTAH, SUB_SWASTA, SUB_ADMIN])
async def test_peran_lebih_tinggi_mewarisi_akses_tamu(
    sub: str,
    rute: str,
    klien_matriks: httpx.AsyncClient,
    buat_token: Callable[..., str],
) -> None:
    respons = await klien_matriks.get(rute, headers=_header(buat_token(sub)))

    assert respons.status_code == 200


@pytest.mark.integration
@pytest.mark.parametrize("rute", RUTE_ANONIM)
async def test_token_tamu_ke_rute_anonim_tetap_200(
    rute: str, klien_matriks: httpx.AsyncClient, buat_token: Callable[..., str]
) -> None:
    """Rute anonim tidak berubah perilaku saat token ikut terkirim."""
    respons = await klien_matriks.get(rute, headers=_header(buat_token(SUB_TAMU)))

    assert respons.status_code == 200


@pytest.mark.integration
async def test_peran_di_luar_daftar_sah_kembalikan_403(
    klien_matriks: httpx.AsyncClient, buat_token: Callable[..., str]
) -> None:
    """Peran asing dari stub profil tidak pernah masuk himpunan izin mana pun."""
    respons = await klien_matriks.get(
        "/api/model/peta-peran", headers=_header(buat_token(SUB_PERAN_ASING))
    )

    assert respons.status_code == 403
    assert respons.json()["galat"]["kode"] == "PERAN_KURANG"


# --- Token rusak / profil bermasalah ------------------------------------


@pytest.mark.integration
async def test_token_kedaluwarsa_kembalikan_401(
    klien_matriks: httpx.AsyncClient, buat_token: Callable[..., str]
) -> None:
    token = buat_token(SUB_TAMU, exp_detik=-10)

    respons = await klien_matriks.get("/api/model/peta-peran", headers=_header(token))

    assert respons.status_code == 401
    assert respons.json()["galat"]["kode"] == "TIDAK_BERWENANG"


@pytest.mark.integration
async def test_token_aud_salah_kembalikan_401(
    klien_matriks: httpx.AsyncClient, buat_token: Callable[..., str]
) -> None:
    token = buat_token(SUB_TAMU, aud="lain")

    respons = await klien_matriks.get("/api/model/peta-peran", headers=_header(token))

    assert respons.status_code == 401


@pytest.mark.integration
async def test_header_bukan_skema_bearer_kembalikan_401(
    klien_matriks: httpx.AsyncClient,
) -> None:
    respons = await klien_matriks.get(
        "/api/model/peta-peran", headers={"Authorization": "Basic abc123"}
    )

    assert respons.status_code == 401


@pytest.mark.integration
async def test_token_sah_tanpa_baris_profil_kembalikan_403(
    klien_matriks: httpx.AsyncClient, buat_token: Callable[..., str]
) -> None:
    token = buat_token(SUB_TANPA_PROFIL)

    respons = await klien_matriks.get("/api/model/peta-peran", headers=_header(token))

    assert respons.status_code == 403
    assert respons.json()["galat"]["kode"] == "PERAN_KURANG"


@pytest.mark.integration
async def test_klaim_role_token_tidak_dipercaya(
    klien_matriks: httpx.AsyncClient, buat_token: Callable[..., str]
) -> None:
    """Token mengklaim role admin tapi tak punya baris profil → tetap 403.

    Bukti sumber peran adalah tabel `profil` (PRD §5), bukan klaim token.
    """
    token = buat_token(SUB_TANPA_PROFIL, klaim_ekstra={"role": "admin"})

    respons = await klien_matriks.get("/api/model/peta-peran", headers=_header(token))

    assert respons.status_code == 403


# --- Supabase belum dikonfigurasi ---------------------------------------


@pytest.mark.integration
async def test_supabase_env_kosong_kembalikan_503(
    dir_data_lengkap: Path,
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    buat_klien: PembuatKlien,
) -> None:
    """Tanpa `SUPABASE_URL`/kunci, rute tamu menjawab 503 `AUTH_BELUM_SIAP`.

    Env di-set string kosong (bukan sekadar delenv) supaya nilai dari berkas
    `.env` lokal — bila ada — ikut tertimpa dan uji tidak flaky antar mesin.
    """
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    ambil_pengaturan.cache_clear()

    try:
        k = await buat_klien(create_app(), lifespan=True)
        respons = await k.get(
            "/api/model/peta-peran", headers=_header(buat_token(SUB_TAMU))
        )
    finally:
        ambil_pengaturan.cache_clear()

    assert respons.status_code == 503
    assert respons.json()["galat"]["kode"] == "AUTH_BELUM_SIAP"


# --- CORS, cache 304, dan rate limit pada aplikasi nyata -----------------


@pytest.mark.integration
async def test_cors_get_publik_aplikasi_nyata_acao_bintang(
    klien_matriks: httpx.AsyncClient,
) -> None:
    respons = await klien_matriks.get(
        "/health", headers={"Origin": "https://contoh.acak"}
    )

    assert respons.status_code == 200
    assert respons.headers["access-control-allow-origin"] == "*"


@pytest.mark.integration
async def test_cors_401_rute_tamu_tetap_berheader_cors(
    klien_matriks: httpx.AsyncClient,
) -> None:
    """Galat auth pun berheader CORS — bukti MiddlewareCORS paling luar."""
    respons = await klien_matriks.get(
        "/api/model/peta-peran", headers={"Origin": "http://localhost:3000"}
    )

    assert respons.status_code == 401
    assert respons.headers["access-control-allow-origin"] == "http://localhost:3000"


@pytest.mark.integration
async def test_cors_304_cache_tetap_berheader_cors(
    klien_matriks: httpx.AsyncClient,
) -> None:
    pertama = await klien_matriks.get(
        "/api/wilayah/provinsi", headers={"Origin": "https://contoh.acak"}
    )
    etag = pertama.headers["ETag"]

    kedua = await klien_matriks.get(
        "/api/wilayah/provinsi",
        headers={"Origin": "https://contoh.acak", "If-None-Match": etag},
    )

    assert kedua.status_code == 304
    assert kedua.headers["access-control-allow-origin"] == "*"


@pytest.mark.integration
async def test_rate_limit_aplikasi_nyata_429_beramplop(
    dir_data_lengkap: Path, monkeypatch: pytest.MonkeyPatch, buat_klien: PembuatKlien
) -> None:
    """`LAJU_BAWAAN` dari env dihormati aplikasi nyata: permintaan ke-3 → 429."""
    monkeypatch.setenv("LAJU_BAWAAN", "2/minute")
    ambil_pengaturan.cache_clear()

    try:
        k = await buat_klien(create_app(), lifespan=True)
        assert (await k.get("/health")).status_code == 200
        assert (await k.get("/health")).status_code == 200
        respons = await k.get("/health")
    finally:
        ambil_pengaturan.cache_clear()

    assert respons.status_code == 429
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "TERLALU_BANYAK_PERMINTAAN"
    assert "retry-after" in respons.headers


# --- Rute admin (fase 7) --------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("metode, rute", RUTE_ADMIN)
async def test_anonim_ke_rute_admin_kembalikan_401(
    metode: str, rute: str, klien_matriks: httpx.AsyncClient
) -> None:
    respons = await klien_matriks.request(metode, rute)

    assert respons.status_code == 401
    assert respons.json()["galat"]["kode"] == "TIDAK_BERWENANG"


@pytest.mark.integration
@pytest.mark.parametrize("metode, rute", RUTE_ADMIN)
@pytest.mark.parametrize("sub", [SUB_TAMU, SUB_PEMERINTAH, SUB_SWASTA])
async def test_peran_bukan_admin_ke_rute_admin_kembalikan_403(
    sub: str,
    metode: str,
    rute: str,
    klien_matriks: httpx.AsyncClient,
    buat_token: Callable[..., str],
) -> None:
    respons = await klien_matriks.request(
        metode, rute, headers=_header(buat_token(sub))
    )

    assert respons.status_code == 403
    assert respons.json()["galat"]["kode"] == "PERAN_KURANG"


@pytest.mark.integration
@pytest.mark.parametrize("metode, rute", RUTE_ADMIN)
async def test_token_admin_melewati_gerbang_rute_admin(
    metode: str,
    rute: str,
    klien_matriks: httpx.AsyncClient,
    buat_token: Callable[..., str],
) -> None:
    """Status bukan 200 yang wajib — 202/404/422 pun membuktikan gerbang lolos."""
    respons = await klien_matriks.request(
        metode, rute, headers=_header(buat_token(SUB_ADMIN))
    )

    assert respons.status_code not in (401, 403)


# --- Rute laporan (fase 8) -------------------------------------------------


@pytest.mark.integration
async def test_anonim_ke_laporan_401(klien_matriks: httpx.AsyncClient) -> None:
    respons = await klien_matriks.get(RUTE_LAPORAN)

    assert respons.status_code == 401
    assert respons.json()["galat"]["kode"] == "TIDAK_BERWENANG"


@pytest.mark.integration
async def test_tamu_ke_laporan_403(
    klien_matriks: httpx.AsyncClient, buat_token: Callable[..., str]
) -> None:
    respons = await klien_matriks.get(
        RUTE_LAPORAN, headers=_header(buat_token(SUB_TAMU))
    )

    assert respons.status_code == 403
    assert respons.json()["galat"]["kode"] == "PERAN_KURANG"


@pytest.mark.integration
async def test_swasta_ke_laporan_403(
    klien_matriks: httpx.AsyncClient, buat_token: Callable[..., str]
) -> None:
    """Kasus pembeda seluruh fase: swasta mewarisi semua akses tamu tetapi
    TIDAK punya laporan — satu-satunya pengecualian pewarisan peran (PRD
    akar bagian 3, dipetakan di PRD api/ bagian 4).
    """
    respons = await klien_matriks.get(
        RUTE_LAPORAN, headers=_header(buat_token(SUB_SWASTA))
    )

    assert respons.status_code == 403
    assert respons.json()["galat"]["kode"] == "PERAN_KURANG"


@pytest.mark.integration
async def test_pemerintah_ke_laporan_200(
    klien_matriks: httpx.AsyncClient, buat_token: Callable[..., str]
) -> None:
    respons = await klien_matriks.get(
        RUTE_LAPORAN, headers=_header(buat_token(SUB_PEMERINTAH))
    )

    assert respons.status_code == 200
    assert "application/pdf" in respons.headers["content-type"]
    assert respons.content.startswith(b"%PDF-")


@pytest.mark.integration
async def test_admin_ke_laporan_200(
    klien_matriks: httpx.AsyncClient, buat_token: Callable[..., str]
) -> None:
    respons = await klien_matriks.get(
        RUTE_LAPORAN, headers=_header(buat_token(SUB_ADMIN))
    )

    assert respons.status_code == 200
    assert "application/pdf" in respons.headers["content-type"]


# --- Rute chat (fase 5) ------------------------------------------------------
#
# Badan permintaan SENGAJA KOSONG (tanpa `json=`) di seluruh uji di bawah --
# pola yang sama dipakai RUTE_ADMIN di atas. `klien_matriks` TIDAK menambal
# `app.state.layanan_ai`, jadi badan yang SAH akan menembus ke `LayananGemini`
# sungguhan dan memakan kuota Gemini nyata (pelajaran yang sama sudah dicatat
# untuk `POST /api/admin/berita/segarkan` di `api/CLAUDE.md` bagian 12). Badan
# kosong tidak pernah mencapai titik itu: 422 (validasi `PermintaanChat`
# gagal) sudah cukup membuktikan gerbang peran TERLEWATI, sementara 401/403
# membuktikan gerbangnya MENAHAN -- keduanya tidak butuh badan sah untuk
# dibuktikan.


@pytest.mark.integration
@pytest.mark.parametrize("metode, rute", RUTE_CHAT)
async def test_anonim_ke_rute_chat_kembalikan_401(
    metode: str, rute: str, klien_matriks: httpx.AsyncClient
) -> None:
    respons = await klien_matriks.request(metode, rute)

    assert respons.status_code == 401
    assert respons.json()["galat"]["kode"] == "TIDAK_BERWENANG"


@pytest.mark.integration
@pytest.mark.parametrize("metode, rute", RUTE_CHAT)
async def test_tamu_ke_rute_chat_kembalikan_403(
    metode: str,
    rute: str,
    klien_matriks: httpx.AsyncClient,
    buat_token: Callable[..., str],
) -> None:
    """Tamu DITOLAK di sini -- satu-satunya rute selain laporan yang tidak
    mewarisi akses tamu ke atasnya, kebalikan arahnya: chat MENGECUALIKAN
    tamu, bukan mengecualikan swasta seperti laporan (PRD akar bagian 3).
    """
    respons = await klien_matriks.request(
        metode, rute, headers=_header(buat_token(SUB_TAMU))
    )

    assert respons.status_code == 403
    assert respons.json()["galat"]["kode"] == "PERAN_KURANG"


@pytest.mark.integration
@pytest.mark.parametrize("metode, rute", RUTE_CHAT)
@pytest.mark.parametrize("sub", [SUB_PEMERINTAH, SUB_SWASTA, SUB_ADMIN])
async def test_peran_di_atas_tamu_melewati_gerbang_rute_chat(
    sub: str,
    metode: str,
    rute: str,
    klien_matriks: httpx.AsyncClient,
    buat_token: Callable[..., str],
) -> None:
    """Status bukan 200 yang wajib — 422 (badan kosong) pun membuktikan gerbang lolos."""
    respons = await klien_matriks.request(
        metode, rute, headers=_header(buat_token(sub))
    )

    assert respons.status_code not in (401, 403)
