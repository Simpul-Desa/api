"""Konstanta Asisten Desa: frasa penolakan baku, kode peringatan, dan ambang.

Kode PERINGATAN di sini BUKAN kode galat HTTP: ia masuk ke
`DataJawaban.peringatan` pada respons 200, bukan ke amplop `galat`. Karena
itu ia tinggal di sini, bukan di katalog kode galat publik
`src/exceptions.py` (PRD bagian 6).
"""

from typing import Final

# Frasa penolakan baku. Disuntik ke prompt lewat {{REFUSAL}} DAN dipakai
# harness/penilai.py untuk deteksi refusal deterministik. Mengubah salah
# satunya saja mematahkan penilaian harness.
REFUSAL_BAKU: Final[str] = (
    "Maaf, saya hanya dapat membantu pertanyaan seputar data dan metodologi SIMPUL DESA."
)

# Peringatan (masuk DataJawaban.peringatan, bukan amplop galat)
PUTARAN_ALAT_HABIS: Final[str] = "PUTARAN_ALAT_HABIS"
ANGKA_TANPA_ASAL: Final[str] = "ANGKA_TANPA_ASAL"
SUSPEK_INJEKSI: Final[str] = "SUSPEK_INJEKSI"
SUSPEK_INJEKSI_ALAT: Final[str] = "SUSPEK_INJEKSI_ALAT"
BOCOR_PROMPT: Final[str] = "BOCOR_PROMPT"
MARKUP_DIBUANG: Final[str] = "MARKUP_DIBUANG"
JAWABAN_KOSONG: Final[str] = "JAWABAN_KOSONG"

# Teks pengganti saat `respons.text` Gemini `None` ATAU `""` (kandidat/parts
# kosong -- blokir `SAFETY_BAKU` atau `prompt_feedback.block_reason`).
# Verbatim keputusan user. "Silakan" adalah ejaan baku KBBI. Frasa "contact
# support" TETAP dipertahankan apa adanya atas keputusan user, meski bukan
# frasa Indonesia baku -- JANGAN diterjemahkan atau diubah.
TEKS_JAWABAN_KOSONG: Final[str] = (
    "Maaf, saya belum bisa menjawab pertanyaan Anda. "
    "Silakan hubungi contact support kami untuk melaporkan insiden ini."
)

# Galat tingkat alat (dikembalikan sebagai DATA hasil fungsi, bukan exception)
ALAT_TIDAK_DIKENAL: Final[str] = "ALAT_TIDAK_DIKENAL"
ARGUMEN_TIDAK_SAH: Final[str] = "ARGUMEN_TIDAK_SAH"

# Skor deteksi_injeksi >= ini pada gabungan pesan user -> jawab refusal baku
# TANPA memanggil LLM sama sekali. Skor 1 hanya ditandai: kata sehari-hari
# yang sah ("abaikan", "instruksi") berhenti di 1 poin, dan memblokir di 1
# berarti false refusal untuk percakapan yang sah.
AMBANG_BLOKIR: Final[int] = 2

# Batas cacah baris hasil alat yang boleh masuk konteks model. Service
# internal TIDAK membawa paginasi seperti rutenya: `ratakan()` mengembalikan
# seluruh jalur 97 kabupaten dan `baca_sel_citra` seluruh skor satu provinsi.
# Tanpa batas ini satu putaran alat bisa puluhan ribu token.
MAKS_BARIS_ALAT: Final[int] = 20

# Berita dipotong lebih pendek: tiap baris membawa rangkuman satu paragraf.
MAKS_BARIS_BERITA: Final[int] = 10

# Batas cacah pemanggilan fungsi dalam SATU putaran. Tanpa ini, satu
# permintaan sah bisa meminta puluhan kartu sekaligus; tiap hasil ikut
# terkirim ulang di seluruh putaran berikutnya, dan biaya token satu
# permintaan HTTP terukur mencapai ~1,94 juta karakter. Ambang rate limit
# membatasi PERMINTAAN, bukan token - inilah plafon tokennya.
MAKS_PANGGILAN_PER_PUTARAN: Final[int] = 8
TERLALU_BANYAK_PANGGILAN: Final[str] = "TERLALU_BANYAK_PANGGILAN"
