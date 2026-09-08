"""Orkestrator CLI build `data-salinan/` — jalankan seluruh tahapan build.

Modul ini menjalankan seluruh langkah build `data-salinan/` secara
berurutan: salin artefak kontrak, salin bahan metodologi, turunkan wilayah
dari kartu index, precompute desa kembar (opsional), sederhanakan geometri
batas desa (opsional), lalu tulis `manifest.json`. Dipakai sebagai skrip
CLI lewat `python -m bangun`.
"""

import argparse
import json
import logging
from pathlib import Path
from typing import cast

from bangun.geo import sederhanakan_semua
from bangun.kembar import precompute_semua
from bangun.konstanta import AKAR_DATA, DIR_BATAS_DESA, DIR_KELUARAN, TOLERANSI_GEO_BAKU
from bangun.manifest import sha256_berkas, tulis_manifest
from bangun.salin import salin_kontrak, salin_metodologi
from bangun.wilayah import tulis_wilayah

logger = logging.getLogger(__name__)


def _parse_argv(argv: list[str] | None) -> argparse.Namespace:
    """Susun dan parse argumen CLI orkestrator build `data-salinan/`."""
    parser = argparse.ArgumentParser(
        description="Bangun data-salinan/ dari data/ mentah."
    )
    parser.add_argument(
        "--toleransi-geo",
        type=float,
        default=TOLERANSI_GEO_BAKU,
        help="Toleransi simplifikasi geometri GeoJSON batas desa (derajat).",
    )
    parser.add_argument(
        "--lewati-geo",
        action="store_true",
        help="Lewati tahap simplifikasi geometri batas desa.",
    )
    parser.add_argument(
        "--lewati-kembar",
        action="store_true",
        help="Lewati tahap precompute desa kembar.",
    )
    parser.add_argument(
        "--akar-data",
        type=Path,
        default=AKAR_DATA,
        help="Akar direktori data/ sumber.",
    )
    parser.add_argument(
        "--dir-keluaran",
        type=Path,
        default=DIR_KELUARAN,
        help="Direktori keluaran build (data-salinan/).",
    )
    return parser.parse_args(argv)


def _bangun(args: argparse.Namespace) -> dict[str, object]:
    """Jalankan seluruh tahapan build berurutan dan tulis `manifest.json`.

    Urutan tahap: salin kontrak -> salin metodologi -> turunkan wilayah ->
    (opsional) precompute desa kembar -> (opsional) sederhanakan geometri ->
    tulis manifest. `tulis_manifest` SELALU jadi tahap terakhir, sehingga
    kegagalan tahap mana pun sebelumnya (mis. `ValueError` dari artefak
    kontrak yang hilang) menjamin `manifest.json` tidak pernah ditulis.
    """
    akar_data: Path = args.akar_data
    dir_keluaran: Path = args.dir_keluaran

    logger.info("Tahap 1/5: salin artefak kontrak")
    entri = salin_kontrak(akar_data=akar_data, dir_keluaran=dir_keluaran)

    logger.info("Tahap 2/5: salin bahan metodologi")
    entri += salin_metodologi(akar_proyek=akar_data.parent, dir_keluaran=dir_keluaran)

    logger.info("Tahap 3/5: turunkan wilayah dari kartu index")
    berkas_indeks = dir_keluaran / "kartu-ekonomi" / "indeks.json"
    indeks = json.loads(berkas_indeks.read_text(encoding="utf-8"))
    path_wilayah = tulis_wilayah(indeks, dir_keluaran)
    entri.append(
        {
            "path": "wilayah.json",
            "sumber": "turunan:indeks kartu + konstanta PROVINSI",
            "sha256": sha256_berkas(path_wilayah),
            "bytes": path_wilayah.stat().st_size,
        }
    )

    if args.lewati_kembar:
        logger.info("Tahap 4/5: dilewati (--lewati-kembar)")
    else:
        logger.info("Tahap 4/5: precompute desa kembar")
        entri += precompute_semua(akar_data=akar_data, dir_keluaran=dir_keluaran)

    if args.lewati_geo:
        logger.info("Tahap 5/5: dilewati (--lewati-geo)")
    else:
        logger.info("Tahap 5/5: sederhanakan geometri batas desa")
        entri += sederhanakan_semua(
            akar_data / DIR_BATAS_DESA, dir_keluaran / "geo", args.toleransi_geo
        )

    return tulis_manifest(dir_keluaran, entri)


def jalankan(argv: list[str] | None = None) -> int:
    """Jalankan orkestrator build `data-salinan/` end-to-end lewat CLI.

    Mengembalikan 0 kalau seluruh tahap sukses (`manifest.json` ditulis).
    Kalau ada tahap yang gagal (mis. artefak kontrak hilang), galat
    di-log lalu fungsi ini mengembalikan 1 -- `manifest.json` TIDAK ditulis
    karena `tulis_manifest` selalu jadi tahap terakhir (lihat `_bangun`).
    """
    logging.basicConfig(level=logging.INFO)
    args = _parse_argv(argv)

    try:
        manifest = _bangun(args)
    except Exception:
        logger.exception("Build data-salinan/ gagal")
        return 1

    artefak = cast(list[dict[str, object]], manifest["artefak"])
    n_artefak = len(artefak)
    total_bytes = sum(cast(int, item["bytes"]) for item in artefak)
    hash_pendek = str(manifest["hash"])[:12]

    print(
        f"Build data-salinan/ selesai: {n_artefak} artefak, "
        f"{total_bytes} bytes, hash {hash_pendek}, tanggal {manifest['tanggal']}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(jalankan())
