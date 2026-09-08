# Harness eval Asisten Desa

Suite eval untuk `POST /api/chat` (Asisten Desa): 51 kasus di 4 kategori
(`angka` 10, `guardrail_topik` 13, `injection` 18, `istilah` 10), dijalankan
in-process lewat `httpx.ASGITransport` tanpa server dan tanpa Supabase
sungguhan. Penilaian hibrida: `penilai.py` menilai deterministik dulu (regex,
daftar istilah terlarang, pola refusal), lalu kasus abu-abu diteruskan ke
hakim LLM (`hakim.py`) hanya bila `--hakim` diminta.

## Kenapa ada rel kuota

Satu giliran chat bisa memakai sampai 6 panggilan Gemini (5 putaran alat + 1
panggilan penutup tanpa tools saat putaran habis). 51 kasus tanpa batas
berarti kira-kira 51 * 6 = 306 panggilan — sekitar 30% kuota harian free
tier — habis dalam satu perintah salah ketik. Harness ini memakai
`GEMINI_API_KEY_CHAT`, kunci yang sama dipakai `POST /api/chat`, TERPISAH
dari `GEMINI_API_KEY` milik panen Berita Desa (`src/admin`).

## Pemakaian

```bash
../.venv/bin/python -m harness.jalankan                       # kering, 0 kuota
../.venv/bin/python -m harness.jalankan --sungguhan           # 8 kasus, <=60 panggilan
../.venv/bin/python -m harness.jalankan --sungguhan --semua --maks-panggilan 320
../.venv/bin/python -m harness.jalankan --sungguhan --kategori injection --hakim
```

- Baris 1: bawaan tanpa `--sungguhan` — muat kasus, validasi skema, cetak
  ringkasan, keluar. Nol jaringan.
- Baris 2: 8 kasus contoh (rata per kategori), anggaran bawaan 60 panggilan.
- Baris 3: seluruh 51 kasus, anggaran dinaikkan supaya tidak terpotong.
- Baris 4: satu kategori saja, hakim LLM dinyalakan untuk kasus abu-abu.

## Rel pengaman

| Rel | Nilai |
|---|---|
| Bawaan | kering — nol jaringan, aplikasi FastAPI tidak dibangun |
| Anggaran keras | `--maks-panggilan` (bawaan 60), dihitung dari `data.putaran_alat` (kini = cacah panggilan Gemini nyata, termasuk panggilan penutup saat putaran alat habis) |
| Cakupan | contoh 8 kasus (bawaan); `--semua` untuk seluruh 51 |
| Hakim LLM | opt-in lewat `--hakim`, mati bawaan |
| Model | termurah, `gemini-flash-lite-latest` (bawaan `pengaturan.model_chat_cadangan`) |
| Eksekusi | serial, jeda 4 detik antar kasus, retry pada 429/502/503 (3x, backoff `10 * percobaan`) |
| Isolasi | in-process (`ASGITransport`), tanpa server, tanpa Supabase sungguhan (klien ditimpa tiruan) |
| Kunci | wajib eksplisit — `--sungguhan` tanpa `GEMINI_API_KEY_CHAT` terisi keluar kode 2 SEBELUM kasus pertama |

## Jangan diulang

`harness/` sengaja di LUAR `testpaths = ["tests"]` (`pyproject.toml`).
Melebarkan `testpaths` ke folder ini membuat `pytest` polos membakar kuota
Gemini. Penjaganya `tests/chat/test_harness_terpisah.py`.

Laporan ditulis ke `harness/laporan/` dan gitignored.

Batas pertahanan injeksi TIDAK diklaim kebal — filter deterministik
memperlambat, bukan menghentikan, penyerang Best-of-N yang gigih (OWASP LLM
Prompt Injection Prevention Cheat Sheet). Lapis prompt Railguard dan safety
settings Gemini tetap berjalan di baliknya.
