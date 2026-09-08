"""Turunkan daftar wilayah (provinsi & kabupaten) dari kartu index desa.

Modul ini membaca baris kartu index (masing-masing minimal punya "idkab"
dan "nmkab"), lalu menurunkan dua daftar: provinsi (dari `konstanta.PROVINSI`,
hanya yang benar-benar hadir di index) dan kabupaten unik. Kode provinsi
yang tidak dikenal dianggap korupsi data dan langsung menghentikan proses
(fail fast) alih-alih diam-diam dilewati.
"""

import json
import logging
from pathlib import Path

from bangun.konstanta import PROVINSI

logger = logging.getLogger(__name__)


def turunkan_wilayah(indeks: list[dict[str, object]]) -> dict[str, object]:
    """Turunkan daftar provinsi dan kabupaten unik dari baris kartu index.

    Args:
        indeks: daftar baris kartu index, tiap baris minimal berisi
            "idkab" (str 4 digit) dan "nmkab".

    Returns:
        dict dengan kunci "provinsi" (list dict idprov+nama, hanya provinsi
        yang hadir di `indeks`, terurut idprov) dan "kabupaten" (list dict
        idkab+nmkab+idprov, unik per idkab, terurut idkab).

    Raises:
        ValueError: jika ditemukan kode provinsi (2 digit awal idkab) yang
            tidak ada di `konstanta.PROVINSI` — indikasi data korup.
    """
    kabupaten_unik: dict[str, dict[str, object]] = {}
    idprov_hadir: set[str] = set()

    for baris in indeks:
        idkab = str(baris["idkab"])
        idprov = idkab[:2]

        if idprov not in PROVINSI:
            raise ValueError(
                f"Kode provinsi tidak dikenal: {idprov!r} (dari idkab {idkab!r})"
            )

        idprov_hadir.add(idprov)
        kabupaten_unik[idkab] = {
            "idkab": idkab,
            "nmkab": baris["nmkab"],
            "idprov": idprov,
        }

    provinsi = [
        {"idprov": idprov, "nama": PROVINSI[idprov]} for idprov in sorted(idprov_hadir)
    ]
    kabupaten = [kabupaten_unik[idkab] for idkab in sorted(kabupaten_unik)]

    logger.info(
        "Turunkan wilayah: %d provinsi, %d kabupaten dari %d baris index",
        len(provinsi),
        len(kabupaten),
        len(indeks),
    )

    return {"provinsi": provinsi, "kabupaten": kabupaten}


def tulis_wilayah(indeks: list[dict[str, object]], dir_keluaran: Path) -> Path:
    """Turunkan wilayah dari `indeks` lalu tulis ke `dir_keluaran/wilayah.json`.

    Args:
        indeks: daftar baris kartu index, diteruskan ke `turunkan_wilayah`.
        dir_keluaran: direktori tujuan; dibuat (beserta induknya) jika
            belum ada.

    Returns:
        Path berkas `wilayah.json` yang ditulis.
    """
    wilayah = turunkan_wilayah(indeks)

    dir_keluaran.mkdir(parents=True, exist_ok=True)
    path_keluaran = dir_keluaran / "wilayah.json"
    path_keluaran.write_text(
        json.dumps(wilayah, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Tulis wilayah.json ke %s", path_keluaran)

    return path_keluaran
