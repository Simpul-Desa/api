"""Uji unit untuk modul konfigurasi (src/config.py)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import Pengaturan, ambil_pengaturan

VARIABEL_LINGKUNGAN = (
    "LINGKUNGAN",
    "DIR_DATA",
    "ORIGIN_APP",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "JWT_AUDIENCE",
    "LAJU_BAWAAN",
    "WEB_CONCURRENCY",
    "MAKS_CACHE_KARTU",
    "MAKS_CACHE_JALUR",
    "MAKS_CACHE_CITRA",
    "MAKS_CACHE_KEMBAR",
)


def _hapus_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for nama in VARIABEL_LINGKUNGAN:
        monkeypatch.delenv(nama, raising=False)


@pytest.mark.unit
def test_pengaturan_default_saat_env_kosong(monkeypatch: pytest.MonkeyPatch) -> None:
    _hapus_env(monkeypatch)

    pengaturan = Pengaturan(_env_file=None)

    assert pengaturan.lingkungan == "dev"
    assert pengaturan.dir_data == Path("data-salinan")
    assert pengaturan.origin_app == "http://localhost:3000"
    assert pengaturan.supabase_url == ""
    assert pengaturan.supabase_service_role_key.get_secret_value() == ""
    assert pengaturan.jwt_audience == "authenticated"
    assert pengaturan.laju_bawaan == "120/minute"


@pytest.mark.unit
def test_pengaturan_terisi_dari_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _hapus_env(monkeypatch)
    monkeypatch.setenv("LINGKUNGAN", "prod")
    monkeypatch.setenv("DIR_DATA", str(tmp_path))
    monkeypatch.setenv("ORIGIN_APP", "https://simpuldesa.example")
    monkeypatch.setenv("SUPABASE_URL", "https://proyek.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "kunci-rahasia")
    monkeypatch.setenv("LAJU_BAWAAN", "5/minute")

    pengaturan = Pengaturan(_env_file=None)

    assert pengaturan.lingkungan == "prod"
    assert pengaturan.dir_data == tmp_path
    assert isinstance(pengaturan.dir_data, Path)
    assert pengaturan.origin_app == "https://simpuldesa.example"
    assert pengaturan.supabase_url == "https://proyek.supabase.co"
    assert pengaturan.supabase_service_role_key.get_secret_value() == "kunci-rahasia"
    assert "kunci-rahasia" not in repr(pengaturan)
    assert pengaturan.laju_bawaan == "5/minute"


@pytest.mark.unit
def test_ambil_pengaturan_dicache(monkeypatch: pytest.MonkeyPatch) -> None:
    _hapus_env(monkeypatch)
    ambil_pengaturan.cache_clear()

    pertama = ambil_pengaturan()
    kedua = ambil_pengaturan()

    assert pertama is kedua


@pytest.mark.unit
def test_supabase_url_http_ditolak(monkeypatch: pytest.MonkeyPatch) -> None:
    _hapus_env(monkeypatch)

    with pytest.raises(ValueError, match="https"):
        Pengaturan(_env_file=None, supabase_url="http://proyek.supabase.co")


@pytest.mark.unit
def test_supabase_url_garis_miring_ekor_dibuang(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _hapus_env(monkeypatch)

    pengaturan = Pengaturan(_env_file=None, supabase_url="https://proyek.supabase.co/")

    assert pengaturan.supabase_url == "https://proyek.supabase.co"


@pytest.mark.unit
def test_luar_dev_tanpa_kredensial_supabase_gagal_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _hapus_env(monkeypatch)

    with pytest.raises(ValueError, match="Supabase"):
        Pengaturan(
            _env_file=None,
            lingkungan="prod",
            origin_app="https://simpuldesa.example",
        )


@pytest.mark.unit
def test_luar_dev_origin_http_gagal_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    _hapus_env(monkeypatch)

    with pytest.raises(ValueError, match="ORIGIN_APP"):
        Pengaturan(
            _env_file=None,
            lingkungan="prod",
            origin_app="http://simpuldesa.example",
            supabase_url="https://proyek.supabase.co",
            supabase_service_role_key="kunci",
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("lingkungan", "workers", "boleh"),
    [
        ("prod", "2", False),
        ("prod", "4", False),
        ("prod", "1", True),
        ("prod", None, True),
        ("dev", "4", True),
    ],
)
def test_web_concurrency_lebih_dari_satu_ditolak_di_luar_dev(
    monkeypatch: pytest.MonkeyPatch,
    lingkungan: str,
    workers: str | None,
    boleh: bool,
) -> None:
    """Gerbang satu-pekerjaan penyegaran hidup di MEMORI PROSES.

    `src/admin/jobs.py` menjaga "satu pekerjaan pada satu waktu" lewat
    `app.state`, yang atomik HANYA dalam satu proses. Dengan lebih dari satu
    worker, N admin (atau satu admin yang N permintaannya dibagi rata antar
    worker) masing-masing memulai pekerjaan sendiri — sampai 50 desa panen
    RSS + Gemini per worker — dan invarian ber-409 itu diam-diam berubah
    jadi "satu pekerjaan per worker". Lebih baik gagal boot daripada jalan
    dengan invarian yang bohong.
    """
    _hapus_env(monkeypatch)
    kwargs: dict[str, object] = {
        "lingkungan": lingkungan,
        "origin_app": "https://app.contoh.id",
        "supabase_url": "https://uji.supabase.co",
        "supabase_service_role_key": "kunci-uji",
    }
    if workers is not None:
        kwargs["web_concurrency"] = int(workers)

    if boleh:
        pengaturan = Pengaturan(_env_file=None, **kwargs)  # type: ignore[arg-type]
        assert pengaturan.web_concurrency == int(workers or 1)
    else:
        with pytest.raises(ValueError, match="WEB_CONCURRENCY"):
            Pengaturan(_env_file=None, **kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
def test_maks_cache_default_saat_env_kosong(monkeypatch: pytest.MonkeyPatch) -> None:
    _hapus_env(monkeypatch)

    pengaturan = Pengaturan(_env_file=None)

    assert pengaturan.maks_cache_kartu == 16
    assert pengaturan.maks_cache_jalur == 4
    assert pengaturan.maks_cache_citra == 16
    assert pengaturan.maks_cache_kembar == 16


@pytest.mark.unit
def test_maks_cache_terisi_dari_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _hapus_env(monkeypatch)
    monkeypatch.setenv("MAKS_CACHE_KARTU", "4")
    monkeypatch.setenv("MAKS_CACHE_JALUR", "1")
    monkeypatch.setenv("MAKS_CACHE_CITRA", "3")
    monkeypatch.setenv("MAKS_CACHE_KEMBAR", "8")

    pengaturan = Pengaturan(_env_file=None)

    assert pengaturan.maks_cache_kartu == 4
    assert pengaturan.maks_cache_jalur == 1
    assert pengaturan.maks_cache_citra == 3
    assert pengaturan.maks_cache_kembar == 8


@pytest.mark.unit
@pytest.mark.parametrize("nilai", [0, -1])
def test_maks_cache_nol_atau_negatif_ditolak(
    monkeypatch: pytest.MonkeyPatch, nilai: int
) -> None:
    """`maxsize` 0 mematikan cache, negatif dibaca `lru_cache` sebagai 0 juga.

    Keduanya membuat setiap permintaan mem-parse ulang berkas yang sampai
    15,6 MB — kegagalan performa senyap, bukan galat. Ditolak di batas.
    """
    _hapus_env(monkeypatch)

    with pytest.raises(ValidationError):
        Pengaturan(_env_file=None, maks_cache_kartu=nilai)


@pytest.mark.unit
def test_maks_cache_env_sampai_ke_lru_cache_di_proses_baru() -> None:
    """`MAKS_CACHE_KARTU` dari environment benar-benar mengubah `maxsize`.

    Dijalankan di proses TERPISAH dengan sengaja: `maxsize` dibaca saat modul
    service diimpor, jadi `monkeypatch.setenv` di dalam proses uji ini sudah
    terlambat dan akan lolos tanpa membuktikan apa pun. Ini penjaga tombol
    memori produksi (`render.yaml`) — kalau rantai env -> `Pengaturan` ->
    `lru_cache` putus, instance 512 MB kehabisan memori tanpa satu baris log.
    """
    akar = Path(__file__).resolve().parents[1]
    kode = (
        "from src.kartu.service import baca_kartu_kab; "
        "print(baca_kartu_kab.cache_info().maxsize)"
    )

    hasil = subprocess.run(
        [sys.executable, "-c", kode],
        cwd=akar,
        env={**os.environ, "MAKS_CACHE_KARTU": "3"},
        capture_output=True,
        text=True,
        check=True,
    )

    assert hasil.stdout.strip() == "3"
