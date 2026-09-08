"""Uji unit lapis layanan AI (`src/chat/llm.py`). Nol panggilan jaringan."""

import logging
from typing import Any

import httpx
import pytest
from google.genai import errors

from src.chat import llm
from src.chat.constants import (
    JAWABAN_KOSONG,
    MAKS_PANGGILAN_PER_PUTARAN,
    PUTARAN_ALAT_HABIS,
    TEKS_JAWABAN_KOSONG,
    TERLALU_BANYAK_PANGGILAN,
)
from src.chat.llm import LangkahPalsu, LayananGemini, LayananPalsu
from src.chat.schemas import Pesan
from src.chat.tools import KonteksAlat
from src.config import Pengaturan
from src.exceptions import AI_BELUM_SIAP, GALAT_LLM, GalatAPI

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


def _pengaturan(**kwargs: Any) -> Pengaturan:
    """Pengaturan uji, tanpa membaca `.env` nyata — bidang lain memakai bawaan."""
    return Pengaturan(_env_file=None, **kwargs)


def _konteks_uji() -> KonteksAlat:
    """Konteks alat kosong.

    Tiap uji yang benar-benar memicu pemanggilan alat menambal
    `src.chat.llm.jalankan_alat`, jadi isi konteks ini tak pernah dibaca.
    """
    return KonteksAlat(simpanan=None, klien_supabase=None)  # type: ignore[arg-type]


async def _tidur_instan(*_args: Any, **_kwargs: Any) -> None:
    """Pengganti `asyncio.sleep` supaya uji tidak menunggu backoff sungguhan."""


class _PanggilPalsu:
    """Tiruan `types.FunctionCall` — hanya `name` dan `args` yang dipakai kode."""

    def __init__(self, name: str, args: dict[str, Any]) -> None:
        self.name = name
        self.args = args


class _KandidatPalsu:
    """Tiruan `types.Candidate` — hanya `content`/`finish_reason` yang dipakai kode."""

    def __init__(self, content: Any, finish_reason: Any = None) -> None:
        self.content = content
        self.finish_reason = finish_reason


class _RespPalsu:
    """Tiruan `types.GenerateContentResponse` — hanya atribut yang dipakai kode."""

    def __init__(
        self,
        function_calls: list[_PanggilPalsu] | None,
        text: str | None,
        candidates: list[_KandidatPalsu] | None,
        prompt_feedback: Any = None,
    ) -> None:
        self.function_calls = function_calls
        self.text = text
        self.candidates = candidates
        self.prompt_feedback = prompt_feedback


class _ModelsPalsu:
    def __init__(self, panggil: Any) -> None:
        self._panggil = panggil

    async def generate_content(
        self, *, model: str, contents: Any, config: Any
    ) -> _RespPalsu:
        return await self._panggil(model=model, contents=contents, config=config)


class _AioPalsu:
    def __init__(self, models: _ModelsPalsu) -> None:
        self.models = models


class _KlienPalsu:
    """Tiruan `genai.Client` — hanya jalur `.aio.models.generate_content` dipakai kode."""

    def __init__(self, panggil: Any) -> None:
        self.aio = _AioPalsu(_ModelsPalsu(panggil))


def _tambal_client(monkeypatch: pytest.MonkeyPatch, klien_palsu: _KlienPalsu) -> None:
    """Tambal properti `_client` di kelas `LayananGemini`, bukan instance.

    Properti adalah data descriptor: menimpa atribut instance tidak menembus
    `property` tanpa setter. Menambal di kelas juga membuat uji ini tidak
    perlu `gemini_api_key_chat` sungguhan.
    """
    monkeypatch.setattr(LayananGemini, "_client", property(lambda self: klien_palsu))


async def test_layanan_palsu_satu_tool_call_dan_teks() -> None:
    langkah = [
        LangkahPalsu(
            fungsi="cari_desa", argumen={"q": "Kubu"}, hasil={"iddesa": "180104"}
        ),
        LangkahPalsu(teks="Jawaban akhir"),
    ]
    layanan = LayananPalsu(langkah)

    hasil = await layanan.jawab(
        [Pesan(role="user", isi="halo")], "system", 0.4, _konteks_uji()
    )

    assert hasil.teks == "Jawaban akhir"
    assert len(hasil.jejak) == 1
    assert hasil.jejak[0].fungsi == "cari_desa"
    assert hasil.jejak[0].argumen == {"q": "Kubu"}
    assert hasil.jejak[0].status == "sukses"
    assert hasil.hasil_mentah == [{"iddesa": "180104"}]
    assert hasil.putaran == 2


async def test_layanan_palsu_hasil_galat_ditandai_jejak_gagal() -> None:
    langkah = [
        LangkahPalsu(fungsi="wilayah_ringkasan", hasil={"galat": "WILAYAH_TIDAK_ADA"}),
        LangkahPalsu(teks="maaf, data tidak ditemukan"),
    ]
    layanan = LayananPalsu(langkah)

    hasil = await layanan.jawab(
        [Pesan(role="user", isi="halo")], "system", 0.4, _konteks_uji()
    )

    assert hasil.jejak[0].status == "gagal"
    assert hasil.hasil_mentah == [{"galat": "WILAYAH_TIDAK_ADA"}]


def test_kunci_kosong_menolak_sebelum_membangun_klien() -> None:
    layanan = LayananGemini(_pengaturan(gemini_api_key_chat=""))

    with pytest.raises(GalatAPI) as info:
        _ = layanan._client

    assert info.value.kode == AI_BELUM_SIAP
    assert info.value.status == 503


async def test_kunci_kosong_tidak_berubah_jadi_galat_llm_lewat_jawab() -> None:
    layanan = LayananGemini(_pengaturan(gemini_api_key_chat=""))

    with pytest.raises(GalatAPI) as info:
        await layanan.jawab(
            [Pesan(role="user", isi="halo")], "system", 0.4, _konteks_uji()
        )

    # Galat konfigurasi TIDAK boleh tertelan jadi 502 GALAT_LLM yang
    # menyesatkan — kodenya harus tetap AI_BELUM_SIAP.
    assert info.value.kode == AI_BELUM_SIAP
    assert info.value.status == 503


async def test_semua_model_gagal_melempar_galat_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hitung = {"n": 0}

    async def _selalu_gagal(*, model: str, contents: Any, config: Any) -> _RespPalsu:
        hitung["n"] += 1
        raise errors.APIError(
            503, {"error": {"message": "model sibuk", "status": "UNAVAILABLE"}}
        )

    _tambal_client(monkeypatch, _KlienPalsu(_selalu_gagal))
    monkeypatch.setattr(llm.asyncio, "sleep", _tidur_instan)

    layanan = LayananGemini(_pengaturan())

    with pytest.raises(GalatAPI) as info:
        await layanan.jawab(
            [Pesan(role="user", isi="halo")], "system", 0.4, _konteks_uji()
        )

    assert info.value.kode == GALAT_LLM
    assert info.value.status == 502
    # 3 model dicoba (utama x2 + cadangan), masing-masing gagal sekali.
    assert hitung["n"] == 3


async def test_semua_model_gagal_tidak_membocorkan_detail_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T1: pesan `GalatAPI` publik TIDAK boleh memuat detail exception vendor
    (URL endpoint, nama model, kuota) -- sebelumnya `f"...: {galat}"` menyalin
    verbatim exception asli ke amplop 502."""
    hitung = {"n": 0}

    async def _selalu_gagal(*, model: str, contents: Any, config: Any) -> _RespPalsu:
        hitung["n"] += 1
        raise errors.APIError(
            503,
            {
                "error": {
                    "message": (
                        "DETAIL-INTERNAL-RAHASIA-XYZ "
                        "https://generativelanguage.googleapis.com/quota-habis"
                    ),
                    "status": "UNAVAILABLE",
                }
            },
        )

    _tambal_client(monkeypatch, _KlienPalsu(_selalu_gagal))
    monkeypatch.setattr(llm.asyncio, "sleep", _tidur_instan)

    layanan = LayananGemini(_pengaturan())

    with pytest.raises(GalatAPI) as info:
        await layanan.jawab(
            [Pesan(role="user", isi="halo")], "system", 0.4, _konteks_uji()
        )

    assert info.value.kode == GALAT_LLM
    assert info.value.status == 502
    assert "DETAIL-INTERNAL-RAHASIA-XYZ" not in info.value.pesan
    assert "googleapis.com" not in info.value.pesan
    assert hitung["n"] == 3


async def test_galat_jaringan_httpx_dicoba_ulang_lalu_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Galat jaringan (transport async SDK memakai httpx, `aiohttp` TIDAK
    terpasang) diperlakukan sama seperti `errors.APIError` -- layak diulang
    ke model berikutnya, lalu 502 GALAT_LLM setelah ketiganya gagal."""
    hitung = {"n": 0}

    async def _selalu_gagal(*, model: str, contents: Any, config: Any) -> _RespPalsu:
        hitung["n"] += 1
        raise httpx.ConnectError("jaringan putus")

    _tambal_client(monkeypatch, _KlienPalsu(_selalu_gagal))
    monkeypatch.setattr(llm.asyncio, "sleep", _tidur_instan)

    layanan = LayananGemini(_pengaturan())

    with pytest.raises(GalatAPI) as info:
        await layanan.jawab(
            [Pesan(role="user", isi="halo")], "system", 0.4, _konteks_uji()
        )

    assert info.value.kode == GALAT_LLM
    assert info.value.status == 502
    assert hitung["n"] == 3


async def test_galat_non_vendor_naik_apa_adanya_tanpa_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bug data kita sendiri (mis. `KeyError` dari `tools.py`) BUKAN galat
    vendor -- ia TIDAK boleh diulang ke model lain (satu bug deterministik
    gagal 3x + backoff percuma), dan TIDAK boleh disamarkan jadi 502
    GALAT_LLM. Exception naik apa adanya ke pemanggil `jawab()`."""
    hitung = {"n": 0}
    tidur_dipanggil = {"n": 0}

    async def _pencatat_tidur(*_args: Any, **_kwargs: Any) -> None:
        tidur_dipanggil["n"] += 1

    async def _meledak_non_vendor(
        *, model: str, contents: Any, config: Any
    ) -> _RespPalsu:
        hitung["n"] += 1
        raise KeyError("idkab")

    _tambal_client(monkeypatch, _KlienPalsu(_meledak_non_vendor))
    monkeypatch.setattr(llm.asyncio, "sleep", _pencatat_tidur)

    layanan = LayananGemini(_pengaturan())

    with pytest.raises(KeyError):
        await layanan.jawab(
            [Pesan(role="user", isi="halo")], "system", 0.4, _konteks_uji()
        )

    assert hitung["n"] == 1
    assert tidur_dipanggil["n"] == 0


async def test_putaran_alat_habis_menandai_peringatan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hitung = {"n": 0}

    async def _selalu_panggil_alat(
        *, model: str, contents: Any, config: Any
    ) -> _RespPalsu:
        hitung["n"] += 1
        return _RespPalsu(
            function_calls=[_PanggilPalsu(name="wilayah_ringkasan", args={})],
            text="tidak dipakai",
            candidates=[_KandidatPalsu(content=object())],
        )

    async def _jalankan_alat_palsu(
        nama: str, argumen: dict[str, Any], konteks: KonteksAlat
    ) -> dict[str, Any]:
        return {"ok": True}

    _tambal_client(monkeypatch, _KlienPalsu(_selalu_panggil_alat))
    monkeypatch.setattr(llm, "jalankan_alat", _jalankan_alat_palsu)

    pengaturan = _pengaturan(chat_maks_putaran_alat=2)
    layanan = LayananGemini(pengaturan)

    hasil = await layanan.jawab(
        [Pesan(role="user", isi="halo")], "system", 0.4, _konteks_uji()
    )

    assert hasil.peringatan == [PUTARAN_ALAT_HABIS]
    # M3 (disengaja): `putaran` sekarang = CACAH PANGGILAN `generate_content`
    # NYATA (loop alat + satu panggilan penutup), bukan `maks` semata --
    # harness `--maks-panggilan` menjumlahkan `data["putaran_alat"]` sebagai
    # anggaran kuota, dan nilai lama (`maks`) kurang hitung ~20% karena tidak
    # menghitung panggilan penutup ini.
    assert hasil.putaran == pengaturan.chat_maks_putaran_alat + 1
    assert hasil.putaran == hitung["n"]
    # Loop = chat_maks_putaran_alat panggilan, ditambah SATU panggilan
    # penutup tanpa tools untuk memaksa jawaban teks.
    assert hitung["n"] == pengaturan.chat_maks_putaran_alat + 1


async def test_automatic_function_calling_dimatikan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_tertangkap: list[Any] = []

    async def _tangkap_config(*, model: str, contents: Any, config: Any) -> _RespPalsu:
        config_tertangkap.append(config)
        return _RespPalsu(function_calls=None, text="jawaban", candidates=None)

    _tambal_client(monkeypatch, _KlienPalsu(_tangkap_config))

    layanan = LayananGemini(_pengaturan())

    await layanan.jawab([Pesan(role="user", isi="halo")], "system", 0.4, _konteks_uji())

    assert config_tertangkap[0].automatic_function_calling is not None
    assert config_tertangkap[0].automatic_function_calling.disable is True


async def test_hasil_fungsi_dikirim_sebagai_role_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from google.genai import types

    contents_tertangkap: list[list[Any]] = []
    hitung = {"n": 0}

    async def _panggil(*, model: str, contents: Any, config: Any) -> _RespPalsu:
        hitung["n"] += 1
        contents_tertangkap.append(list(contents))
        if hitung["n"] == 1:
            return _RespPalsu(
                function_calls=[_PanggilPalsu(name="wilayah_ringkasan", args={})],
                text="",
                candidates=[
                    _KandidatPalsu(
                        content=types.Content(
                            role="model",
                            parts=[types.Part.from_text(text="memanggil alat")],
                        )
                    )
                ],
            )
        return _RespPalsu(function_calls=None, text="selesai", candidates=None)

    async def _jalankan_alat_palsu(
        nama: str, argumen: dict[str, Any], konteks: KonteksAlat
    ) -> dict[str, Any]:
        return {"ok": True}

    _tambal_client(monkeypatch, _KlienPalsu(_panggil))
    monkeypatch.setattr(llm, "jalankan_alat", _jalankan_alat_palsu)

    layanan = LayananGemini(_pengaturan())

    await layanan.jawab([Pesan(role="user", isi="halo")], "system", 0.4, _konteks_uji())

    # Kedua = contents yang diterima panggilan generate_content KEDUA, yaitu
    # SETELAH hasil fungsi dari putaran pertama ditambahkan.
    kedua = contents_tertangkap[1]
    isi_terakhir = kedua[-1]
    assert isi_terakhir.role == "user"
    assert isi_terakhir.parts[-1].function_response is not None


async def test_panggilan_melewati_batas_tetap_dijawab_stub_galat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T4: model meminta 12 `function_call` dalam SATU putaran -- hanya
    `MAKS_PANGGILAN_PER_PUTARAN` (8) pertama yang benar-benar dieksekusi
    lewat `jalankan_alat`; 4 sisanya dijawab stub `{"galat":
    TERLALU_BANYAK_PANGGILAN}` TANPA dieksekusi. Keduanya tetap mendapat
    `function_response` (satu per `function_call` -- Gemini menolak giliran
    berikutnya kalau ada yang tidak dijawab) DAN tetap tercatat di
    `jejak_fungsi`, yang terpotong berstatus "gagal" -- bukan dibuang
    senyap. Sebelum perbaikan T4, satu putaran tanpa batas ini bisa
    mencapai puluhan panggilan sekaligus (terukur 18 panggilan / ~1,94 juta
    karakter untuk satu permintaan HTTP sah)."""
    CACAH_DIMINTA = 12
    hitung_eksekusi = {"n": 0}
    hitung_putaran = {"n": 0}
    contents_tertangkap: list[list[Any]] = []

    async def _panggil(*, model: str, contents: Any, config: Any) -> _RespPalsu:
        hitung_putaran["n"] += 1
        contents_tertangkap.append(list(contents))
        if hitung_putaran["n"] == 1:
            return _RespPalsu(
                function_calls=[
                    _PanggilPalsu(name=f"alat_{i}", args={"i": i})
                    for i in range(CACAH_DIMINTA)
                ],
                text="",
                candidates=[_KandidatPalsu(content=object())],
            )
        return _RespPalsu(function_calls=None, text="selesai", candidates=None)

    async def _jalankan_alat_palsu(
        nama: str, argumen: dict[str, Any], konteks: KonteksAlat
    ) -> dict[str, Any]:
        hitung_eksekusi["n"] += 1
        return {"ok": True}

    _tambal_client(monkeypatch, _KlienPalsu(_panggil))
    monkeypatch.setattr(llm, "jalankan_alat", _jalankan_alat_palsu)

    layanan = LayananGemini(_pengaturan())

    hasil = await layanan.jawab(
        [Pesan(role="user", isi="halo")], "system", 0.4, _konteks_uji()
    )

    # Hanya MAKS_PANGGILAN_PER_PUTARAN yang benar-benar dieksekusi.
    assert hitung_eksekusi["n"] == MAKS_PANGGILAN_PER_PUTARAN

    # Tapi SELURUH 12 panggilan tercatat di jejak -- 4 terakhir "gagal".
    assert len(hasil.jejak) == CACAH_DIMINTA
    status = [j.status for j in hasil.jejak]
    assert (
        status[:MAKS_PANGGILAN_PER_PUTARAN] == ["sukses"] * MAKS_PANGGILAN_PER_PUTARAN
    )
    assert status[MAKS_PANGGILAN_PER_PUTARAN:] == ["gagal"] * (
        CACAH_DIMINTA - MAKS_PANGGILAN_PER_PUTARAN
    )
    assert hasil.hasil_mentah[MAKS_PANGGILAN_PER_PUTARAN:] == [
        {"galat": TERLALU_BANYAK_PANGGILAN}
    ] * (CACAH_DIMINTA - MAKS_PANGGILAN_PER_PUTARAN)

    # contents yang dikirim ke panggilan generate_content KEDUA (putaran
    # berikutnya) harus memuat 12 `function_response` -- satu per
    # `function_call`, termasuk yang dipotong -- kalau tidak, API Gemini
    # sungguhan menolak giliran ini.
    kedua = contents_tertangkap[1]
    respons_fungsi = [
        isi
        for isi in kedua
        if getattr(isi, "parts", None) and isi.parts[-1].function_response is not None
    ]
    assert len(respons_fungsi) == CACAH_DIMINTA


# --- jawaban kosong (respons.text None ATAU "") diganti teks baku ----------


class _FeedbackPalsu:
    """Tiruan `types.GenerateContentResponsePromptFeedback` — hanya `block_reason`."""

    def __init__(self, block_reason: Any = "SAFETY") -> None:
        self.block_reason = block_reason


async def test_jawaban_kosong_diganti_teks_pengganti_dan_peringatan(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def _jawaban_kosong(*, model: str, contents: Any, config: Any) -> _RespPalsu:
        return _RespPalsu(
            function_calls=None,
            text=None,
            candidates=[],
            prompt_feedback=_FeedbackPalsu(),
        )

    _tambal_client(monkeypatch, _KlienPalsu(_jawaban_kosong))

    layanan = LayananGemini(_pengaturan())

    with caplog.at_level(logging.WARNING):
        hasil = await layanan.jawab(
            [Pesan(role="user", isi="halo")], "system", 0.4, _konteks_uji()
        )

    assert hasil.teks == TEKS_JAWABAN_KOSONG
    assert JAWABAN_KOSONG in hasil.peringatan
    assert any(
        "finish_reason" in rec.message and "block_reason" in rec.message
        for rec in caplog.records
    )


async def test_jawaban_kosong_pada_jalur_putaran_habis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pola sama seperti `test_putaran_alat_habis_menandai_peringatan`, tapi
    panggilan PENUTUP (putaran habis) membalas jawaban kosong -- peringatan
    harus memuat KEDUANYA `PUTARAN_ALAT_HABIS` dan `JAWABAN_KOSONG`."""
    hitung = {"n": 0}

    async def _selalu_panggil_lalu_kosong(
        *, model: str, contents: Any, config: Any
    ) -> _RespPalsu:
        hitung["n"] += 1
        if hitung["n"] <= 2:
            return _RespPalsu(
                function_calls=[_PanggilPalsu(name="wilayah_ringkasan", args={})],
                text="tidak dipakai",
                candidates=[_KandidatPalsu(content=object())],
            )
        # Panggilan penutup: jawaban kosong.
        return _RespPalsu(function_calls=None, text=None, candidates=[])

    async def _jalankan_alat_palsu(
        nama: str, argumen: dict[str, Any], konteks: KonteksAlat
    ) -> dict[str, Any]:
        return {"ok": True}

    _tambal_client(monkeypatch, _KlienPalsu(_selalu_panggil_lalu_kosong))
    monkeypatch.setattr(llm, "jalankan_alat", _jalankan_alat_palsu)

    pengaturan = _pengaturan(chat_maks_putaran_alat=2)
    layanan = LayananGemini(pengaturan)

    hasil = await layanan.jawab(
        [Pesan(role="user", isi="halo")], "system", 0.4, _konteks_uji()
    )

    assert hasil.teks == TEKS_JAWABAN_KOSONG
    assert set(hasil.peringatan) == {PUTARAN_ALAT_HABIS, JAWABAN_KOSONG}


async def test_teks_kosong_string_diperlakukan_sama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _teks_kosong_string(
        *, model: str, contents: Any, config: Any
    ) -> _RespPalsu:
        return _RespPalsu(function_calls=None, text="", candidates=[])

    _tambal_client(monkeypatch, _KlienPalsu(_teks_kosong_string))

    layanan = LayananGemini(_pengaturan())

    hasil = await layanan.jawab(
        [Pesan(role="user", isi="halo")], "system", 0.4, _konteks_uji()
    )

    assert hasil.teks == TEKS_JAWABAN_KOSONG
    assert JAWABAN_KOSONG in hasil.peringatan
