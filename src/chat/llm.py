"""Strategi layanan AI Asisten Desa.

Dua implementasi `LayananAI`: `LayananGemini` (nyata, loop function calling
manual atas API Gemini) dan `LayananPalsu` (skrip deterministik untuk pytest
— tanpa jaringan, tanpa kuota).

Kebijakan model (alias `-latest`, model utama dicoba dua kali, backoff
linear sebelum turun ke cadangan) mengikuti `src/berita/harvest/filter.py`,
yang sudah terbukti di folder ini.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from google import genai
from google.genai import errors, types

from src.chat.constants import (
    JAWABAN_KOSONG,
    MAKS_PANGGILAN_PER_PUTARAN,
    PUTARAN_ALAT_HABIS,
    TEKS_JAWABAN_KOSONG,
    TERLALU_BANYAK_PANGGILAN,
)
from src.chat.schemas import JejakFungsi, Pesan
from src.chat.tools import KonteksAlat, alat_gemini, jalankan_alat
from src.config import Pengaturan
from src.exceptions import AI_BELUM_SIAP, GALAT_LLM, GalatAPI

logger = logging.getLogger(__name__)

_JEDA_ULANG = 5.0

# Galat VENDOR (layak diulang ke model lain): `errors.APIError` (basis SDK
# 2.22.0 -- mencakup subkelas `ClientError`/`ServerError`, jadi 404/429/503
# tertangkap seragam) dan `httpx.HTTPError` (transport async SDK memakai
# httpx, `aiohttp` TIDAK terpasang, jadi galat jaringan/timeout muncul lewat
# sini). Exception LAIN (mis. `KeyError` dari bug data kita sendiri di
# `tools.py`) BUKAN galat vendor -- ia harus naik apa adanya ke 500
# GALAT_SERVER, bukan ditelan jadi 3 percobaan + 15 detik percuma lalu
# dilaporkan 502 GALAT_LLM yang salah atribusi. Kalau kelak `aiohttp`
# dipasang, `aiohttp.ClientError` akan jatuh ke jalur non-vendor 500 ini dan
# perlu ditambahkan ke tuple ini saat itu.
_GALAT_VENDOR: tuple[type[Exception], ...] = (errors.APIError, httpx.HTTPError)

SAFETY_BAKU = [
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
]


@dataclass
class HasilLayanan:
    teks: str
    jejak: list[JejakFungsi] = field(default_factory=list)
    hasil_mentah: list[Any] = field(default_factory=list)
    putaran: int = 1
    model: str = ""
    peringatan: list[str] = field(default_factory=list)


def _teks_atau_pengganti(respons: types.GenerateContentResponse) -> tuple[str, bool]:
    """Teks jawaban, atau `TEKS_JAWABAN_KOSONG` bila `respons.text` kosong.

    `respons.text` bisa `None` ATAU `""` saat `candidates`/`parts` kosong
    (blokir `SAFETY_BAKU` atau `prompt_feedback.block_reason`) -- `respons.text
    or ""` yang lama menelan keduanya jadi string kosong TANPA jejak apa pun
    ke pemanggil maupun ke log. Detail (`finish_reason`, `block_reason`)
    HANYA masuk log; teks pengganti yang dikembalikan tidak membawa alasan
    apa pun ke pemanggil.
    """
    if respons.text:
        return respons.text, False
    finish_reason = respons.candidates[0].finish_reason if respons.candidates else None
    block_reason = getattr(respons.prompt_feedback, "block_reason", None)
    logger.warning(
        "jawaban Gemini kosong: finish_reason=%s block_reason=%s",
        finish_reason,
        block_reason,
    )
    return TEKS_JAWABAN_KOSONG, True


class LayananAI(ABC):
    @abstractmethod
    async def jawab(
        self,
        messages: list[Pesan],
        system_prompt: str,
        temperature: float,
        konteks: KonteksAlat,
    ) -> HasilLayanan:
        raise NotImplementedError


class LayananGemini(LayananAI):
    def __init__(self, pengaturan: Pengaturan) -> None:
        self._pengaturan = pengaturan
        # Model utama dicoba DUA kali: 503 "model sibuk" sering terjadi dan
        # itu bukan masalah kuota, baru turun ke cadangan pada percobaan
        # ketiga.
        self._model_coba = [
            pengaturan.model_chat,
            pengaturan.model_chat,
            pengaturan.model_chat_cadangan,
        ]
        self._klien_gemini: genai.Client | None = None

    @property
    def _client(self) -> genai.Client:
        """Klien Gemini, dibangun lazy.

        Kunci kosong baru gagal saat dipakai, bukan saat impor modul —
        `create_app()` harus tetap bisa dibangun pytest tanpa kunci.
        """
        if self._klien_gemini is None:
            # Kunci yang dipakai `gemini_api_key_chat`, BUKAN `gemini_api_key`
            # (itu milik panen Berita Desa) — TIDAK ADA fallback, karena
            # fallback diam-diam menghancurkan alasan pemisahan kuota.
            kunci = self._pengaturan.gemini_api_key_chat.get_secret_value()
            if not kunci:
                raise GalatAPI(
                    AI_BELUM_SIAP, "layanan Asisten Desa belum dikonfigurasi", 503
                )
            # Client(api_key=...) mengirim kunci lewat header, tidak pernah
            # di URL galat/log.
            self._klien_gemini = genai.Client(api_key=kunci)
        return self._klien_gemini

    async def jawab(
        self,
        messages: list[Pesan],
        system_prompt: str,
        temperature: float,
        konteks: KonteksAlat,
    ) -> HasilLayanan:
        galat: Exception | None = None
        for i, model in enumerate(self._model_coba):
            try:
                return await self._jawab_satu_model(
                    model, messages, system_prompt, temperature, konteks
                )
            except GalatAPI:
                # Kunci kosong adalah kesalahan konfigurasi, bukan model
                # sibuk — kalau ditelan di sini, pemanggil hanya melihat 502
                # GALAT_LLM yang menyesatkan.
                raise
            except _GALAT_VENDOR as exc:  # 404/429/503/timeout diperlakukan seragam
                galat = exc
                logger.warning("Gemini gagal pada %s", model, exc_info=True)
                if i < len(self._model_coba) - 1:
                    await asyncio.sleep(_JEDA_ULANG * (i + 1))
                # Galat NON-vendor (bug data kita sendiri, mis. `KeyError`
                # dari `tools.py`) TIDAK ditangkap di sini -- ia merambat
                # keluar dari `jawab()` apa adanya menuju jaring
                # `_tangani_tak_terduga` FastAPI (500 GALAT_SERVER), bukan
                # diulang 3x ke model lain lalu disamarkan jadi 502
                # GALAT_LLM.
        # Detail vendor (URL endpoint, nama model, kuota proyek) masuk LOG,
        # tidak pernah ke pemanggil -- pesan `galat` verbatim di sini pernah
        # membocorkan detail internal itu ke amplop publik 502 (PRD bagian 6:
        # "5xx galat server tanpa bocoran detail internal").
        logger.error("semua model Gemini gagal", exc_info=galat)
        raise GalatAPI(
            GALAT_LLM, "layanan Asisten Desa sedang gagal, coba lagi nanti", 502
        ) from galat

    async def _jawab_satu_model(
        self,
        model: str,
        messages: list[Pesan],
        system_prompt: str,
        temperature: float,
        konteks: KonteksAlat,
    ) -> HasilLayanan:
        # Anotasi `ContentUnion`, bukan `Content`: `list` invarian di mypy,
        # jadi `list[Content]` bukan subtipe dari union tipe yang diminta SDK
        # walau tiap elemennya sah.
        contents: list[types.ContentUnion] = [
            types.Content(role=m.role, parts=[types.Part.from_text(text=m.isi)])
            for m in messages
        ]
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            tools=[alat_gemini()],
            safety_settings=SAFETY_BAKU,
            # Tanpa disable=True, SDK mengeksekusi alat sendiri dan
            # `jejak_fungsi` — yang merupakan kontrak PRD bagian 5, jejak
            # asal angka — kosong tanpa galat apa pun.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        )
        jejak: list[JejakFungsi] = []
        hasil_mentah: list[Any] = []
        maks = self._pengaturan.chat_maks_putaran_alat
        for putaran in range(1, maks + 1):
            respons = await self._client.aio.models.generate_content(
                model=model, contents=contents, config=config
            )
            panggilan = respons.function_calls or []
            if not panggilan:
                teks, kosong = _teks_atau_pengganti(respons)
                return HasilLayanan(
                    teks=teks,
                    jejak=jejak,
                    hasil_mentah=hasil_mentah,
                    putaran=putaran,
                    model=model,
                    peringatan=[JAWABAN_KOSONG] if kosong else [],
                )
            if respons.candidates:
                isi_model = respons.candidates[0].content
                if isi_model is not None:
                    contents.append(isi_model)
            for nomor, panggil in enumerate(panggilan):
                argumen = dict(panggil.args or {})
                # Panggilan yang melewati MAKS_PANGGILAN_PER_PUTARAN tetap
                # dijawab stub `{"galat": ...}`, TIDAK dibuang -- Gemini
                # menuntut satu `function_response` untuk TIAP `function_call`
                # pada giliran model; membuang salah satunya membuat panggilan
                # berikutnya ditolak API. Jejaknya tetap dicatat berstatus
                # "gagal" supaya pemotongan terlihat di `jejak_fungsi`, bukan
                # senyap.
                if nomor < MAKS_PANGGILAN_PER_PUTARAN:
                    hasil = await jalankan_alat(panggil.name or "", argumen, konteks)
                else:
                    hasil = {"galat": TERLALU_BANYAK_PANGGILAN}
                status: Literal["sukses", "gagal"] = (
                    "gagal" if "galat" in hasil else "sukses"
                )
                jejak.append(
                    JejakFungsi(
                        fungsi=panggil.name or "", argumen=argumen, status=status
                    )
                )
                hasil_mentah.append(hasil)
                # Role "tool" DITOLAK API live ("Role 'tool' is not
                # supported") walau dokumen SDK memakainya; role "user"
                # berisi Part.from_function_response terbukti jalan 7
                # September 2026.
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(
                                name=panggil.name or "", response=hasil
                            )
                        ],
                    )
                )
        # Putaran habis: satu panggilan terakhir TANPA tools untuk memaksa
        # jawaban teks.
        config_akhir = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            safety_settings=SAFETY_BAKU,
        )
        respons = await self._client.aio.models.generate_content(
            model=model, contents=contents, config=config_akhir
        )
        teks, kosong = _teks_atau_pengganti(respons)
        return HasilLayanan(
            teks=teks,
            jejak=jejak,
            hasil_mentah=hasil_mentah,
            # M3: `maks + 1`, BUKAN `maks` -- ini cacah panggilan
            # `generate_content` NYATA (`maks` putaran alat + SATU panggilan
            # penutup di atas), dan harness (`--maks-panggilan`) menjumlahkan
            # nilai ini sebagai anggaran kuota. `maks` saja kurang hitung
            # ~20% karena tidak menghitung panggilan penutup ini.
            putaran=maks + 1,
            model=model,
            peringatan=[PUTARAN_ALAT_HABIS] + ([JAWABAN_KOSONG] if kosong else []),
        )


@dataclass
class LangkahPalsu:
    """Satu langkah skrip `LayananPalsu`: tool call (fungsi+argumen+hasil) atau teks akhir."""

    teks: str | None = None
    fungsi: str | None = None
    argumen: dict[str, Any] = field(default_factory=dict)
    hasil: dict[str, Any] = field(default_factory=dict)


class LayananPalsu(LayananAI):
    """Implementasi deterministik untuk pytest — tanpa jaringan, tanpa kuota."""

    def __init__(
        self,
        langkah: list[LangkahPalsu],
        model: str = "palsu",
        peringatan: list[str] | None = None,
    ) -> None:
        self._langkah = langkah
        self._model = model
        self._peringatan = peringatan or []

    async def jawab(
        self,
        messages: list[Pesan],
        system_prompt: str,
        temperature: float,
        konteks: KonteksAlat,
    ) -> HasilLayanan:
        jejak: list[JejakFungsi] = []
        hasil_mentah: list[Any] = []
        teks = ""
        for langkah in self._langkah:
            if langkah.fungsi is not None:
                status: Literal["sukses", "gagal"] = (
                    "gagal" if "galat" in langkah.hasil else "sukses"
                )
                jejak.append(
                    JejakFungsi(
                        fungsi=langkah.fungsi, argumen=langkah.argumen, status=status
                    )
                )
                hasil_mentah.append(langkah.hasil)
            if langkah.teks is not None:
                teks = langkah.teks
        return HasilLayanan(
            teks=teks,
            jejak=jejak,
            hasil_mentah=hasil_mentah,
            putaran=1 + sum(1 for x in self._langkah if x.fungsi is not None),
            model=self._model,
            peringatan=list(self._peringatan),
        )
