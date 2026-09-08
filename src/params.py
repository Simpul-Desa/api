"""Pola dan tipe parameter path/query yang dipakai lebih dari satu modul.

Pola regex kode wilayah dan kode desa disimpan sebagai konstanta bernama
karena literalnya sebelumnya ditulis ulang di 14 tempat: `^\\d{2}$` di 4
tempat, `^\\d{4}$` di 5 tempat, `^\\d{10}$` di 5 tempat. Satu salah ketik di
salah satunya membuat satu endpoint menerima kode yang tidak sah tanpa
terlihat di endpoint lain.

Yang dibagikan di sini HANYA pola, plus satu alias yang tripletnya (tipe,
pola, deskripsi) benar-benar identik antar modul. Alias sengaja TIDAK
diseragamkan lebih jauh: deskripsi parameter berbeda antar endpoint
("Filter provinsi (2 digit)" di citra potensi, "Kode provinsi 2 digit" di
peta peran, tanpa deskripsi di wilayah), dan deskripsi itu terbit ke
`/openapi.json` yang merupakan bagian kontrak publik menurut PRD §3.
Menyatukannya berarti mengubah kontrak, bukan merapikan struktur.

Nilai bawaan TIDAK ditaruh di dalam `Query()`/`Path()` — FastAPI melarang
`default=` di dalam `Annotated` (AssertionError saat registrasi rute). Pakai
di signature handler, sama seperti `ParamHal`/`ParamBatas` di `pagination.py`.
"""

from typing import Annotated

from fastapi import Path

POLA_IDPROV = r"^\d{2}$"
POLA_IDKAB = r"^\d{4}$"
POLA_IDDESA = r"^\d{10}$"

ParamIddesa = Annotated[
    str, Path(pattern=POLA_IDDESA, description="Kode desa 10 digit")
]
