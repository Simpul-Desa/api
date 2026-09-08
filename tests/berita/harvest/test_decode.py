"""Uji unit tahap dekode (`src/berita/dekode.py`)."""

from typing import Any

import pytest

from src.berita.harvest import decode as dekode


@pytest.mark.unit
def test_dekode_sukses(monkeypatch: pytest.MonkeyPatch) -> None:
    def _dekoder(link: str, interval: int = 1) -> dict[str, Any]:
        return {"status": True, "decoded_url": "https://penerbit.id/artikel"}

    monkeypatch.setattr(dekode, "gnewsdecoder", _dekoder)

    assert dekode.dekode_link("https://news.google.com/x") == (
        "https://penerbit.id/artikel"
    )


@pytest.mark.unit
def test_dekode_status_false_jadi_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def _dekoder(link: str, interval: int = 1) -> dict[str, Any]:
        return {"status": False, "message": "gagal"}

    monkeypatch.setattr(dekode, "gnewsdecoder", _dekoder)

    assert dekode.dekode_link("https://news.google.com/x") is None


@pytest.mark.unit
def test_dekode_exception_jadi_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def _dekoder(link: str, interval: int = 1) -> dict[str, Any]:
        raise RuntimeError("jaringan putus")

    monkeypatch.setattr(dekode, "gnewsdecoder", _dekoder)

    assert dekode.dekode_link("https://news.google.com/x") is None
