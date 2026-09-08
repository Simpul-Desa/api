"""Logika pencarian desa: peringkat kecocokan nama dan kunci pengurutan.

Fungsi murni — tanpa FastAPI, tanpa I/O.
"""

from typing import Any


def peringkat_kecocokan(nama_casefold: str, q_casefold: str) -> int:
    """0 bila `nama_casefold` berawalan `q_casefold`, 1 bila sekadar mengandung.

    Kunci urutan pencarian desa: baris yang namanya berawalan query
    ditempatkan di atas baris yang query-nya cuma muncul sebagai substring
    di tengah/akhir nama.
    """
    return 0 if nama_casefold.startswith(q_casefold) else 1


def kunci_urutan(baris: dict[str, Any], q_casefold: str) -> tuple[int, str]:
    """Kunci `sorted()` hasil pencarian: peringkat kecocokan lalu `iddesa` menaik."""
    return (
        peringkat_kecocokan(baris["nmdesa"].casefold(), q_casefold),
        baris["iddesa"],
    )
