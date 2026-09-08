"""Akses data dan logika Desa Kembar: pembaca berkas kembar + join identitas.

Sumber data: `desa-kembar/<idkab>.json` berisi `{idkab, k, p95_jarak, desa:
{iddesa: [{iddesa, persen}]}}` — hanya `iddesa`+`persen` per tetangga.
Identitas (`nmdesa`, `nmkec`, `idkab`, `nmkab`) di-join di sini dari
`simpanan.indeks_per_desa`.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from src.config import ambil_pengaturan
from src.datastore import muat_json_atau_none
from src.desa_kembar.schemas import TetanggaKembar


@lru_cache(maxsize=ambil_pengaturan().maks_cache_kembar)
def baca_kembar_kab(dir_data_str: str, idkab: str) -> dict[str, Any] | None:
    """Baca `desa-kembar/<idkab>.json` apa adanya.

    Hasil di-cache LRU (`MAKS_CACHE_KEMBAR`, bawaan 16) berkunci
    `(dir_data_str, idkab)`. None
    bila berkas hilang/korup.
    """
    path = Path(dir_data_str) / "desa-kembar" / f"{idkab}.json"
    return muat_json_atau_none(path, f"desa kembar kab {idkab}")


def tetangga_terjoin(
    baris_tetangga: list[dict[str, Any]],
    indeks_per_desa: dict[str, dict[str, Any]],
) -> list[TetanggaKembar]:
    """Join identitas tiap tetangga dari `indeks_per_desa`.

    Tetangga yang `iddesa`-nya tak ada di indeks (data tak konsisten) diisi
    identitas None lewat `.get()`, bukan dilempar sebagai galat — urutan dan
    `persen` tetap dipertahankan apa adanya dari berkas kembar.
    """
    hasil = []
    for t in baris_tetangga:
        identitas = indeks_per_desa.get(t["iddesa"])
        hasil.append(
            TetanggaKembar(
                iddesa=t["iddesa"],
                nmdesa=identitas.get("nmdesa") if identitas else None,
                nmkec=identitas.get("nmkec") if identitas else None,
                idkab=identitas.get("idkab") if identitas else None,
                nmkab=identitas.get("nmkab") if identitas else None,
                persen=t["persen"],
            )
        )
    return hasil


def potong_tetangga(
    tetangga: list[TetanggaKembar], k: int | None
) -> list[TetanggaKembar]:
    """Potong `tetangga` ke `k` teratas; `k` None berarti kembalikan seluruhnya.

    `k` hanya memperkecil daftar — bila lebih besar dari jumlah tetangga
    tersedia, potongan Python (`[:k]`) sudah otomatis mengembalikan seluruh
    daftar tanpa perlu penanganan khusus.
    """
    if k is None:
        return tetangga
    return tetangga[:k]
