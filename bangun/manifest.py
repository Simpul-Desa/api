"""Hitung sha256 artefak dan tulis manifest.json untuk data-salinan/."""

import hashlib
import json
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

UKURAN_POTONGAN = 65536


def sha256_berkas(path: Path) -> str:
    """Hitung digest sha256 heksadesimal dari isi berkas.

    Membaca berkas secara bertahap (chunked) agar tidak memuat seluruh isi
    ke memori sekaligus dan bekerja pada berkas biner apa pun.
    """
    hasher = hashlib.sha256()
    with path.open("rb") as sumber:
        for potongan in iter(lambda: sumber.read(UKURAN_POTONGAN), b""):
            hasher.update(potongan)
    return hasher.hexdigest()


def tulis_manifest(
    dir_keluaran: Path, entri: list[dict[str, object]]
) -> dict[str, object]:
    """Susun manifest dari daftar entri artefak dan tulis ke manifest.json.

    Entri diurutkan berdasarkan "path" agar hasil deterministik tidak
    bergantung urutan input. Hash gabungan dihitung dari sha256 atas
    konsatenasi "{path}:{sha256}\\n" tiap entri terurut, sehingga berubah
    kalau ada artefak yang isinya berubah. Manifest ditulis ke
    `dir_keluaran / "manifest.json"` dan dict yang sama dikembalikan.
    """
    artefak_terurut = sorted(entri, key=lambda item: str(item["path"]))

    hasher = hashlib.sha256()
    for item in artefak_terurut:
        hasher.update(f"{item['path']}:{item['sha256']}\n".encode())

    manifest: dict[str, object] = {
        "hash": hasher.hexdigest(),
        "tanggal": date.today().isoformat(),  # noqa: DTZ011 -- kontrak spek
        "artefak": artefak_terurut,
    }

    dir_keluaran.mkdir(parents=True, exist_ok=True)
    berkas_manifest = dir_keluaran / "manifest.json"
    berkas_manifest.write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("manifest ditulis ke %s", berkas_manifest)

    return manifest
