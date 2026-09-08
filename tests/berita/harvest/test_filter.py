"""Uji unit penyaring Gemini (`src/berita/saring.py`)."""

import json
from typing import Any

import pytest
import requests
from pydantic import ValidationError

from src.berita.harvest import filter as saring

_JAWABAN_SAH = json.dumps(
    {
        "relevan": True,
        "kategori": ["Wisata"],
        "rangkuman": "Desa untung dari wisata.",
        "desa_benar": True,
        "alasan": "kegiatan ekonomi wisata desa",
    }
)


class _ResponsPalsu:
    def __init__(self, status_code: int, teks_jawaban: str | None = None) -> None:
        self.status_code = status_code
        self._teks = teks_jawaban

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self) -> dict[str, Any]:
        return {"candidates": [{"content": {"parts": [{"text": self._teks}]}}]}


@pytest.fixture(autouse=True)
def _tanpa_jeda(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(saring.time, "sleep", lambda detik: None)


@pytest.mark.unit
def test_saring_sukses_model_pertama(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    dipakai: list[str] = []

    def _post(
        url: str, headers: dict[str, str], json: dict[str, Any], timeout: float
    ) -> _ResponsPalsu:
        dipakai.append(url)
        assert headers["x-goog-api-key"] == "kunci-uji"
        return _ResponsPalsu(200, _JAWABAN_SAH)

    monkeypatch.setattr(saring.requests, "post", _post)

    # Act
    hasil = saring.saring_gemini("teks artikel", "Contoh", "Uji", "kunci-uji")

    # Assert
    assert hasil.relevan is True
    assert hasil.kategori == ["Wisata"]
    assert len(dipakai) == 1
    assert "gemini-flash-latest" in dipakai[0]


@pytest.mark.unit
def test_saring_503_dua_kali_fallback_flash_lite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dipakai: list[str] = []

    def _post(
        url: str, headers: dict[str, str], json: dict[str, Any], timeout: float
    ) -> _ResponsPalsu:
        dipakai.append(url)
        if len(dipakai) < 3:
            return _ResponsPalsu(503)
        return _ResponsPalsu(200, _JAWABAN_SAH)

    monkeypatch.setattr(saring.requests, "post", _post)

    hasil = saring.saring_gemini("teks", "Contoh", "Uji", "kunci-uji")

    assert hasil.desa_benar is True
    assert len(dipakai) == 3
    assert "gemini-flash-lite-latest" in dipakai[2]


@pytest.mark.unit
def test_saring_semua_model_gagal_melempar_galat_terakhir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        saring.requests,
        "post",
        lambda url, headers, json, timeout: _ResponsPalsu(503),
    )

    with pytest.raises(requests.HTTPError):
        saring.saring_gemini("teks", "Contoh", "Uji", "kunci-uji")


@pytest.mark.unit
def test_saring_jawaban_bukan_json_melempar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        saring.requests,
        "post",
        lambda url, headers, json, timeout: _ResponsPalsu(200, "bukan json"),
    )

    with pytest.raises(ValidationError):
        saring.saring_gemini("teks", "Contoh", "Uji", "kunci-uji")


@pytest.mark.unit
def test_prompt_memuat_kategori_dan_memotong_teks() -> None:
    teks = "x" * (saring.MAKS_TEKS + 500)

    prompt = saring._prompt(teks, "Contoh", "Uji")

    assert saring.KATEGORI in prompt
    assert "Desa Contoh" in prompt and "Kabupaten Uji" in prompt
    assert len(prompt) < saring.MAKS_TEKS + 2000
