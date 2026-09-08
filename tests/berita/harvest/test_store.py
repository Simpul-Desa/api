"""Uji unit penyimpanan PostgREST (`src/berita/simpan.py`)."""

import logging
from datetime import UTC, datetime

import httpx
import pytest

from src.berita.harvest.store import (
    MAKS_BARIS_TERSIMPAN,
    simpan_berita,
    url_tersimpan,
)
from src.berita.schemas import BarisBerita
from src.config import Pengaturan

_PENGATURAN = Pengaturan(
    supabase_url="https://uji.supabase.co",
    supabase_service_role_key="kunci-uji",
)


def _baris(url: str) -> BarisBerita:
    return BarisBerita(
        iddesa="1801040001",
        judul="Desa untung",
        url=url,
        sumber="Contoh News",
        terbit_pada=datetime(2026, 9, 1, tzinfo=UTC),
        dipanen_pada=datetime(2026, 9, 7, tzinfo=UTC),
        rangkuman="Rangkuman.",
        kategori=["Wisata"],
        perangkum="gemini",
    )


@pytest.mark.unit
def test_url_tersimpan_kembalikan_info_per_url() -> None:
    """Bukan cuma set URL — FIX 1 butuh rangkuman/kategori/perangkum lama
    per URL supaya orchestrator bisa menolak downgrade re-panen."""

    # Arrange
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/v1/berita_desa"
        assert request.url.params["iddesa"] == "eq.1801040001"
        assert request.url.params["select"] == "url,rangkuman,kategori,perangkum"
        assert request.headers["apikey"] == "kunci-uji"
        return httpx.Response(
            200,
            json=[
                {
                    "url": "https://p.id/1",
                    "rangkuman": "Rangkuman lama.",
                    "kategori": ["Wisata"],
                    "perangkum": "gemini",
                },
                {
                    "url": "https://p.id/2",
                    "rangkuman": None,
                    "kategori": [],
                    "perangkum": "judul-rss",
                },
            ],
        )

    klien = httpx.Client(transport=httpx.MockTransport(_handler))

    # Act
    hasil = url_tersimpan(klien, _PENGATURAN, "1801040001")

    # Assert
    assert set(hasil) == {"https://p.id/1", "https://p.id/2"}
    assert hasil["https://p.id/1"]["rangkuman"] == "Rangkuman lama."
    assert hasil["https://p.id/1"]["kategori"] == ["Wisata"]
    assert hasil["https://p.id/1"]["perangkum"] == "gemini"
    assert hasil["https://p.id/2"]["rangkuman"] is None
    assert hasil["https://p.id/2"]["perangkum"] == "judul-rss"


@pytest.mark.unit
def test_simpan_berita_upsert_merge_duplicates() -> None:
    tangkapan: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        tangkapan.append(request)
        return httpx.Response(201)

    klien = httpx.Client(transport=httpx.MockTransport(_handler))

    simpan_berita(klien, _PENGATURAN, [_baris("https://p.id/1")])

    permintaan = tangkapan[0]
    assert permintaan.method == "POST"
    assert permintaan.url.params["on_conflict"] == "iddesa,url"
    assert permintaan.headers["Prefer"] == "resolution=merge-duplicates"
    assert b'"dipanen_pada":"2026-09-07T00:00:00Z"' in permintaan.content
    assert b'"kategori":["Wisata"]' in permintaan.content


@pytest.mark.unit
def test_simpan_berita_daftar_kosong_tanpa_jaringan() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("tidak boleh ada panggilan jaringan")

    klien = httpx.Client(transport=httpx.MockTransport(_handler))

    simpan_berita(klien, _PENGATURAN, [])


@pytest.mark.unit
def test_simpan_berita_galat_postgrest_melempar() -> None:
    klien = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(500, json={}))
    )

    with pytest.raises(httpx.HTTPStatusError):
        simpan_berita(klien, _PENGATURAN, [_baris("https://p.id/1")])


@pytest.mark.unit
def test_url_tersimpan_kirim_limit_eksplisit() -> None:
    """Tanpa `limit` eksplisit, batas baris ditentukan konfigurasi PostgREST
    di luar kendali kode ini."""

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["limit"] == str(MAKS_BARIS_TERSIMPAN)
        return httpx.Response(200, json=[])

    with httpx.Client(transport=httpx.MockTransport(_handler)) as klien:
        url_tersimpan(klien, _PENGATURAN, "1801040001")


@pytest.mark.unit
def test_url_tersimpan_terpotong_di_batas_memperingatkan(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Baris sebanyak `limit` berarti hasilnya PASTI tidak lengkap: penjaga
    anti-downgrade jadi buta pada baris yang tidak terbaca."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "url": f"https://p.id/{i}",
                    "rangkuman": None,
                    "kategori": [],
                    "perangkum": "judul-rss",
                }
                for i in range(MAKS_BARIS_TERSIMPAN)
            ],
        )

    with (
        caplog.at_level(logging.WARNING),
        httpx.Client(transport=httpx.MockTransport(_handler)) as klien,
    ):
        url_tersimpan(klien, _PENGATURAN, "1801040001")

    assert "1801040001" in caplog.text


@pytest.mark.unit
def test_url_tersimpan_di_bawah_batas_tidak_memperingatkan(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "url": "https://p.id/1",
                    "rangkuman": None,
                    "kategori": [],
                    "perangkum": "judul-rss",
                }
            ],
        )

    with (
        caplog.at_level(logging.WARNING),
        httpx.Client(transport=httpx.MockTransport(_handler)) as klien,
    ):
        url_tersimpan(klien, _PENGATURAN, "1801040001")

    assert caplog.text == ""
