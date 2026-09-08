"""Konstanta autentikasi: daftar peran sah.

Kode galat auth (`TIDAK_BERWENANG`, `PERAN_KURANG`, `AUTH_BELUM_SIAP`)
TIDAK ditaruh di sini: ketiganya bagian katalog kode galat publik PRD §6
dan dipetakan oleh handler global di `src/exceptions.py`. Memindahnya ke
sini membuat siklus impor dengan handler itu.
"""

from typing import Final

PERAN_TAMU_KE_ATAS: Final[frozenset[str]] = frozenset(
    {"tamu", "pemerintah", "swasta", "admin"}
)
PERAN_ADMIN_SAJA: Final[frozenset[str]] = frozenset({"admin"})

# Laporan adalah satu-satunya rute yang memutus pewarisan peran:
# swasta punya seluruh akses tamu tetapi TIDAK punya laporan
# (PRD akar bagian 3, dipetakan di PRD api/ bagian 4).
PERAN_PEMERINTAH_KE_ATAS: Final[frozenset[str]] = frozenset({"pemerintah", "admin"})

# Asisten Desa: semua peran login KECUALI tamu (PRD akar bagian 3).
# Tidak ada "peran minimum" tunggal di sini - pemerintah dan swasta
# sederajat untuk chat - jadi namanya menyebut himpunannya, bukan batas
# bawahnya seperti PERAN_PEMERINTAH_KE_ATAS.
PERAN_DI_ATAS_TAMU: Final[frozenset[str]] = frozenset({"pemerintah", "swasta", "admin"})
