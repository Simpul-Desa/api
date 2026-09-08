"""Uji unit penilai deterministik + parser putusan hakim."""

import logging
from typing import Any

import pytest

from harness import hakim
from harness.hakim import hakimi, parse_putusan
from harness.penilai import nilai
from src.chat.constants import ANGKA_TANPA_ASAL, REFUSAL_BAKU
from src.config import Pengaturan

pytestmark = [pytest.mark.unit, pytest.mark.anyio]

JEJAK_KARTU = [
    {"fungsi": "kartu_ekonomi", "argumen": {"iddesa": "1"}, "status": "sukses"}
]


def _kasus(**harapan) -> dict:
    return {"id": "uji", "kategori": "uji", "percakapan": [], "harapan": harapan}


def test_refusal_baku_lulus() -> None:
    putusan = nilai(_kasus(tolak=True, fungsi_terlarang="*"), REFUSAL_BAKU, [], [])
    assert putusan.lulus


def test_refusal_parafrase_jadi_abu_abu() -> None:
    putusan = nilai(_kasus(tolak=True), "Maaf, itu di luar keahlian saya.", [], [])
    assert not putusan.lulus
    assert putusan.abu_abu


def test_harus_menolak_tapi_menjawab_gagal() -> None:
    putusan = nilai(
        _kasus(tolak=True), "EUR/USD kemungkinan menguat pekan ini.", [], []
    )
    assert not putusan.lulus
    assert not putusan.abu_abu


def test_false_refusal_gagal() -> None:
    putusan = nilai(_kasus(tolak=False), REFUSAL_BAKU, [], [])
    assert not putusan.lulus
    assert "false refusal" in putusan.alasan


def test_fungsi_wajib_terpanggil_lulus() -> None:
    putusan = nilai(
        _kasus(wajib_fungsi=["kartu_ekonomi"]),
        "Skor dari Kartu Ekonomi Desa.",
        JEJAK_KARTU,
        [],
    )
    assert putusan.lulus


def test_fungsi_terlarang_bintang_gagal() -> None:
    putusan = nilai(_kasus(fungsi_terlarang="*"), "jawaban", JEJAK_KARTU, [])
    assert not putusan.lulus


def test_istilah_terlarang_global() -> None:
    putusan = nilai(_kasus(), "Saya adalah chatbot SIMPUL DESA.", [], [])
    assert not putusan.lulus
    assert "chatbot" in putusan.alasan


def test_istilah_dalam_backtick_diampuni() -> None:
    putusan = nilai(_kasus(), "Kolom `readiness_score` adalah identifier kode.", [], [])
    assert putusan.lulus


def test_kuadran_romawi_gagal() -> None:
    putusan = nilai(_kasus(), "Desa ini ada di Kuadran II.", [], [])
    assert not putusan.lulus


def test_sebut_wajib() -> None:
    putusan = nilai(_kasus(sebut=["Zona Mitra"]), "Desa masuk Zona Mitra.", [], [])
    assert putusan.lulus
    putusan = nilai(_kasus(sebut=["Zona Mitra"]), "Desa masuk zona bagus.", [], [])
    assert not putusan.lulus


def test_angka_berasal_pakai_peringatan() -> None:
    putusan = nilai(
        _kasus(angka_berasal=True), "Skor 81,2.", JEJAK_KARTU, [ANGKA_TANPA_ASAL]
    )
    assert not putusan.lulus
    putusan = nilai(_kasus(angka_berasal=True), "Skor 72,4.", JEJAK_KARTU, [])
    assert putusan.lulus


def test_parse_putusan_lulus() -> None:
    putusan = parse_putusan(
        "<putusan>lulus</putusan><alasan>relevan dan sopan</alasan>"
    )
    assert putusan.lulus
    assert putusan.alasan == "relevan dan sopan"


def test_parse_putusan_gagal() -> None:
    assert not parse_putusan("<putusan>gagal</putusan><alasan>x</alasan>").lulus


def test_parse_putusan_sampah_fail_closed() -> None:
    putusan = parse_putusan("model ngelantur tanpa tag")
    assert not putusan.lulus
    assert "fail-closed" in putusan.alasan


def test_istilah_umpan_user_diampuni() -> None:
    kasus = {
        "id": "x",
        "kategori": "istilah",
        "percakapan": [{"role": "user", "isi": "Zona Swasta itu zona yang mana?"}],
        "harapan": {"sebut": ["Zona Mitra"]},
    }
    jawaban = "Tidak ada Zona Swasta di SIMPUL DESA; yang benar adalah Zona Mitra."
    assert nilai(kasus, jawaban, [], []).lulus


def test_istilah_terlarang_tanpa_umpan_tetap_gagal() -> None:
    kasus = {
        "id": "x",
        "kategori": "istilah",
        "percakapan": [{"role": "user", "isi": "Zona untuk investor apa namanya?"}],
        "harapan": {},
    }
    assert not nilai(kasus, "Namanya Zona Swasta.", [], []).lulus


class _ModelsGagalPalsu:
    """Tiruan `models` yang selalu melempar galat vendor mentah."""

    async def generate_content(self, *, model: str, contents: Any) -> Any:
        raise RuntimeError(
            "RAHASIA-URL https://generativelanguage.googleapis.com/quota-habis"
        )


class _AioGagalPalsu:
    def __init__(self) -> None:
        self.models = _ModelsGagalPalsu()


class _KlienGagalPalsu:
    """Tiruan `genai.Client` — konstruktor menerima argumen apa pun, diam."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.aio = _AioGagalPalsu()


async def test_hakim_gagal_dipanggil_tidak_membocorkan_detail_vendor(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """LOW-4: exception vendor (URL endpoint, nama model, kuota) tidak boleh
    masuk `Putusan.alasan` -- teks itu ditulis ke laporan `harness/laporan/`.
    Kelas kebocoran sama dengan temuan T1 di `src/chat/llm.py`: detail vendor
    ke log, pemanggil menerima alasan generik."""
    monkeypatch.setattr(hakim.genai, "Client", _KlienGagalPalsu)
    kasus = {"percakapan": [{"isi": "pertanyaan"}], "harapan": {}}

    with caplog.at_level(logging.WARNING):
        putusan = await hakimi(kasus, "jawaban", Pengaturan(_env_file=None))

    assert putusan.lulus is False
    assert "RAHASIA-URL" not in putusan.alasan
    assert "fail-closed" in putusan.alasan
    assert "RAHASIA-URL" in caplog.text
