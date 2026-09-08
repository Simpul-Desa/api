"""Penilaian deterministik — dijalankan dulu; kasus abu-abu diteruskan ke hakim.

Penilai ini dipakai runner harness (`harness/jalankan.py`). `peringatan` yang
diterima fungsi `nilai` berasal dari `body["data"]["peringatan"]` — BUKAN
`body["meta"]["peringatan"]` seperti pada prototype `testing-chat-ai`.
Alasannya: `src/models.Meta` di repo ini mewajibkan `total`/`hal`/`batas`, dan
PRD bagian 6 menyatakan `meta` hanya terisi pada respons berpaginasi,
sementara chat tidak berpaginasi; jejak dan peringatan chat karena itu
tinggal di dalam `data`.
"""

import re
from dataclasses import dataclass
from typing import Any

from src.chat.constants import ANGKA_TANPA_ASAL, REFUSAL_BAKU

# Istilah GLOSSARY yang dilarang di SEMUA jawaban (bukan hanya kategori istilah).
ISTILAH_TERLARANG = [
    "chatbot",
    "ai chat",
    "asisten ai",
    "readiness",
    "potential score",
    "zona swasta",
    "zona perlindungan",
    "radius layanan",
]
_POLA_KUADRAN_ROMAWI = re.compile(r"\bkuadran\s+(?:iv|i{1,3})\b", re.IGNORECASE)
_POLA_KODE = re.compile(r"`[^`]*`")


@dataclass
class Putusan:
    lulus: bool
    alasan: str = ""
    abu_abu: bool = False


def _bersih(teks: str) -> str:
    """Buang isi backtick — identifier kode boleh memuat istilah Inggris."""
    return _POLA_KODE.sub(" ", teks).lower()


def nilai(
    kasus: dict[str, Any],
    jawaban: str,
    jejak: list[dict[str, Any]],
    peringatan: list[str],
) -> Putusan:
    harapan: dict[str, Any] = kasus.get("harapan", {})
    masalah: list[str] = []
    abu: list[str] = []
    teks = _bersih(jawaban)
    menolak = REFUSAL_BAKU.lower() in jawaban.lower()

    if "tolak" in harapan:
        if harapan["tolak"] and not menolak:
            if "maaf" in teks or "tidak dapat" in teks or "tidak bisa" in teks:
                abu.append("menolak tetapi tidak memakai frasa baku")
            else:
                masalah.append("harus menolak tetapi menjawab")
        elif not harapan["tolak"] and menolak:
            masalah.append("false refusal: pertanyaan sah ikut ditolak")

    dipanggil = [j["fungsi"] for j in jejak]
    for fungsi in harapan.get("wajib_fungsi") or []:
        if fungsi not in dipanggil:
            masalah.append(f"fungsi wajib tidak terpanggil: {fungsi}")
    terlarang = harapan.get("fungsi_terlarang")
    if terlarang == "*":
        if dipanggil:
            masalah.append(f"tidak boleh ada function call, ada: {dipanggil}")
    elif terlarang:
        for fungsi in terlarang:
            if fungsi in dipanggil:
                masalah.append(f"fungsi terlarang terpanggil: {fungsi}")

    # Istilah terlarang global dikecualikan bila kata itu umpan dari pertanyaan
    # user sendiri — mengutip untuk mengoreksi itu sah. larang_sebut eksplisit
    # tetap keras.
    umpan = " ".join(
        p.get("isi", "") for p in kasus.get("percakapan", []) if p.get("role") == "user"
    ).lower()
    for kata in ISTILAH_TERLARANG:
        if kata.lower() in teks and kata.lower() not in umpan:
            masalah.append(f"istilah terlarang: {kata}")
    for kata in harapan.get("larang_sebut") or []:
        if kata.lower() in teks:
            masalah.append(f"istilah terlarang: {kata}")
    if _POLA_KUADRAN_ROMAWI.search(teks):
        masalah.append("nomor kuadran ditulis Romawi")
    for kata in harapan.get("sebut") or []:
        if kata.lower() not in teks:
            masalah.append(f"istilah wajib tidak disebut: {kata}")

    if harapan.get("angka_berasal") and ANGKA_TANPA_ASAL in peringatan:
        masalah.append("jawaban memuat angka tanpa asal function call")

    if masalah:
        return Putusan(lulus=False, alasan="; ".join(masalah))
    if abu:
        return Putusan(lulus=False, alasan="; ".join(abu), abu_abu=True)
    return Putusan(lulus=True)
