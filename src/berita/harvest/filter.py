"""Tahap 4 panen Berita Desa: saring topik ekonomi + rangkum lewat Gemini.

Kriteria MASUK diturunkan dari GLOSSARY akar — Potensi produksi (8 tema Skor
Potensi), Kelembagaan ekonomi, Amenitas dan keuangan, Konektivitas dan
pembangunan, Wisata, Program dan investasi, Gangguan berdampak ekonomi.
KELUAR: politik/seremonial tanpa muatan ekonomi, kriminal, keagamaan/sosial
seremonial, olahraga/hiburan/profil tokoh, desa sekadar lokasi kejadian,
bencana tanpa dampak ekonomi yang disebut. Prompt teruji 3/3 pada putaran
uji 7 September 2026 — jangan diubah tanpa uji ulang.

Model memakai alias `-latest`: nama pinned `gemini-2.5-flash-lite` terbukti
404 di endpoint generateContent walau tampil di ListModels.
`gemini-flash-latest` sering 503 (model sibuk, bukan kuota) sehingga dicoba
dua kali sebelum turun ke `gemini-flash-lite-latest`. Kunci API dikirim via
header `x-goog-api-key` supaya tidak pernah muncul di URL galat/log.
"""

import logging
import time

import requests

from src.berita.schemas import HasilSaring

logger = logging.getLogger(__name__)

MODEL_COBA = [
    "gemini-flash-latest",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]
KATEGORI = (
    "Potensi produksi; Kelembagaan ekonomi; Amenitas dan keuangan; "
    "Konektivitas dan pembangunan; Wisata; Program dan investasi; "
    "Gangguan berdampak ekonomi"
)
MAKS_TEKS = 12000
_TIMEOUT_GEMINI = 45.0
_JEDA_ULANG = 5.0


def _prompt(teks: str, desa: str, kab: str) -> str:
    return (
        f"Nilai berita berikut untuk fitur Berita Desa (Desa {desa}, "
        f"Kabupaten {kab}). Abaikan menu/iklan/boilerplate halaman.\n"
        f"Berita RELEVAN hanya bila isinya tentang kegiatan atau kondisi "
        f"ekonomi desa itu, pada kategori: {KATEGORI}. "
        f"TIDAK relevan: politik/seremonial tanpa muatan ekonomi, kriminal, "
        f"keagamaan/sosial seremonial, olahraga/hiburan/profil tokoh, desa "
        f"cuma disebut sebagai lokasi kejadian, bencana tanpa dampak ekonomi "
        f"yang disebut.\n"
        f'Jawab JSON persis: {{"relevan": bool, "kategori": '
        f'[dari daftar di atas, boleh kosong], "rangkuman": "1 paragraf '
        f'bahasa Indonesia fokus ekonomi/potensi/wisata desa itu", '
        f'"desa_benar": bool (benarkah tentang Desa {desa} di Kabupaten '
        f'{kab}, bukan desa senama di tempat lain), "alasan": "1 kalimat '
        f'kenapa masuk/keluar"}}\n\n{teks[:MAKS_TEKS]}'
    )


def saring_gemini(teks: str, desa: str, kab: str, kunci: str) -> HasilSaring:
    """Nilai + rangkum satu artikel; melempar galat terakhir bila semua model gagal."""
    galat: Exception | None = None
    for i, model in enumerate(MODEL_COBA):
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        try:
            r = requests.post(
                url,
                headers={"x-goog-api-key": kunci},
                json={
                    "contents": [{"parts": [{"text": _prompt(teks, desa, kab)}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
                timeout=_TIMEOUT_GEMINI,
            )
            r.raise_for_status()
            isi = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return HasilSaring.model_validate_json(isi)
        except Exception as exc:
            galat = exc
            logger.warning("penyaring Gemini gagal pada %s", model, exc_info=True)
            if i < len(MODEL_COBA) - 1:
                time.sleep(_JEDA_ULANG * (i + 1))
    assert galat is not None  # loop selalu berjalan; sampai sini pasti ada galat
    raise galat
