"""Konstanta modul admin yang dipakai lintas berkas."""

from typing import Final

# Batas keras jumlah desa per permintaan penyegaran. 50 desa x ~10
# artikel x (jeda 1 detik + ambil isi + saring) = pekerjaan latar
# berjam-jam pada kasus terburuk; angka ini yang menahan admin dari
# tidak sengaja memicu panen seluruh provinsi.
MAKS_DESA_SEGARKAN: Final[int] = 50

# Kolom yang diminta dari PostgREST untuk daftar pengguna.
KOLOM_PENGGUNA: Final[str] = "id,email,peran,dibuat_pada,diubah_pada"

# Baris berita yang diambil untuk menurunkan "penyegaran terakhir per
# desa". CAP SADAR: bukan seluruh tabel - desa yang beritanya sangat
# lama bisa tidak muncul di daftar sepuluh besar.
BARIS_SAMPEL_PENYEGARAN: Final[int] = 500
MAKS_DESA_PENYEGARAN_TERAKHIR: Final[int] = 10

# Pola nilai pencarian pengguna. Nilai di luar pola ditolak 422 di batas
# supaya tidak ada karakter yang mengubah arti filter PostgREST.
POLA_CARI_PENGGUNA: Final[str] = r"^[A-Za-z0-9@._+\- ]+$"
