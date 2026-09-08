"""Konstanta modul Jalur Ekonomi: peta varian ke kunci anggota dan ke berkas."""

# Kunci daftar anggota per varian, dipakai anggota_iddesa().
KUNCI_ANGGOTA_PER_VARIAN: dict[str, str] = {
    "komoditas": "anggota",
    "gudang-kopdes": "desa_layanan",
    "cold-storage": "desa_layanan",
    "wisata": "desa",
}

# Nama berkas hasil per varian, dipakai baca_jalur().
BERKAS_JALUR_PER_VARIAN: dict[str, str] = {
    "komoditas": "hasil_komoditas.json",
    "gudang-kopdes": "hasil_gudang.json",
    "cold-storage": "hasil_cold_storage.json",
    "wisata": "hasil_wisata.json",
}
