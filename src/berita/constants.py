"""Konstanta modul Berita Desa yang dipakai lintas berkas.

Konstanta yang hanya dipakai satu berkas pipeline (BLACKLIST, TANDA_BLOKIR,
MODEL_COBA, UA, timeout) sengaja TETAP di berkasnya: menaikkan semuanya ke
sini membuat satu keranjang panjang yang justru menyulitkan pembacaan
logika yang memakainya.
"""

# Kolom yang diminta dari PostgREST untuk rute baca berita.
KOLOM = "id,judul,url,sumber,terbit_pada,dipanen_pada,rangkuman,kategori,perangkum"

# Di bawah panjang ini isi artikel dianggap tak terbaca (halaman blokir atau
# galeri). Dipakai content.py saat mengekstrak dan orchestrator.py saat
# memutuskan artikel dibuang.
MIN_PANJANG_TEKS = 300
