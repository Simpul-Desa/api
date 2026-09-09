"""Skrip build: sederhanakan geometri batas desa (GeoJSON) dan kompres gzip.

Menyederhanakan geometri MultiPolygon batas desa dengan shapely.simplify
(preserve_topology=True), memangkas properti ke {"iddesa", "nmdesa"} saja,
lalu menulis FeatureCollection hasil sebagai .geojson.gz (gzip level 9).
Sengaja hanya pakai `json` + `shapely` (tanpa geopandas) untuk menghindari
dependensi driver I/O geopandas.
"""

import gzip
import hashlib
import json
import logging
from pathlib import Path

from shapely.geometry import mapping, shape

from bangun.konstanta import AKHIRAN_GEO

logger = logging.getLogger(__name__)

PROPERTI_DIPERTAHANKAN = ("iddesa", "nmdesa")


def sederhanakan_berkas(sumber: Path, tujuan: Path, toleransi: float) -> dict[str, int]:
    """Sederhanakan satu berkas GeoJSON batas desa, tulis sebagai .geojson.gz.

    Tiap fitur disederhanakan dengan shapely.simplify (preserve_topology=True).
    Fitur yang geometrinya jadi kosong setelah disederhanakan dibuang dan
    dihitung; total yang dibuang dicatat lewat log peringatan (hanya bila
    ada yang dibuang). Properti fitur yang disimpan hanya "iddesa" dan
    "nmdesa". Hasil ditulis sebagai FeatureCollection JSON yang dikompres
    gzip level 9 ke `tujuan` (direktori induk dibuat bila belum ada).
    """
    bytes_masuk = sumber.stat().st_size
    data = json.loads(sumber.read_text(encoding="utf-8"))

    fitur_keluaran: list[dict[str, object]] = []
    n_dibuang = 0
    for fitur in data["features"]:
        geom = shape(fitur["geometry"]).simplify(toleransi, preserve_topology=True)
        if geom.is_empty:
            n_dibuang += 1
            continue

        properti_asli = fitur.get("properties", {})
        properti_baru = {
            kunci: properti_asli.get(kunci) for kunci in PROPERTI_DIPERTAHANKAN
        }
        fitur_keluaran.append(
            {
                "type": "Feature",
                "properties": properti_baru,
                "geometry": mapping(geom),
            }
        )

    if n_dibuang > 0:
        logger.warning(
            "%s: %d fitur dibuang karena geometri kosong setelah simplifikasi",
            sumber,
            n_dibuang,
        )

    koleksi = {"type": "FeatureCollection", "features": fitur_keluaran}
    isi_gz = gzip.compress(json.dumps(koleksi).encode("utf-8"), compresslevel=9)

    tujuan.parent.mkdir(parents=True, exist_ok=True)
    tujuan.write_bytes(isi_gz)

    return {
        "n_fitur": len(fitur_keluaran),
        "n_dibuang": n_dibuang,
        "bytes_masuk": bytes_masuk,
        "bytes_keluar": len(isi_gz),
    }


def sederhanakan_semua(
    dir_sumber: Path, dir_tujuan: Path, toleransi: float
) -> list[dict[str, object]]:
    """Sederhanakan semua `*.geojson` di `dir_sumber`, kembalikan entri manifest.

    idkab diambil dari 4 karakter pertama nama berkas sumber. Tiap berkas
    ditulis ke `dir_tujuan/<idkab>.geojson.gz`. sha256 keluaran dihitung
    lewat `bangun.manifest.sha256_berkas` (diimpor lambat karena modul itu
    ditulis paralel); bila modul itu belum ada, jatuh ke hashlib langsung
    supaya fungsi ini tidak terblokir.
    """
    entri: list[dict[str, object]] = []
    for berkas_sumber in sorted(dir_sumber.glob("*.geojson")):
        idkab = berkas_sumber.name[:4]
        berkas_tujuan = dir_tujuan / f"{idkab}{AKHIRAN_GEO}"

        hasil = sederhanakan_berkas(berkas_sumber, berkas_tujuan, toleransi)

        try:
            from bangun.manifest import sha256_berkas

            hash_keluaran = sha256_berkas(berkas_tujuan)
        except ImportError:
            hash_keluaran = hashlib.sha256(berkas_tujuan.read_bytes()).hexdigest()

        logger.info(
            "%s: %d -> %d bytes, %d fitur dibuang",
            idkab,
            hasil["bytes_masuk"],
            hasil["bytes_keluar"],
            hasil["n_dibuang"],
        )

        entri.append(
            {
                "path": f"geo/{idkab}.geojson.gz",
                "sumber": str(berkas_sumber),
                "sha256": hash_keluaran,
                "bytes": hasil["bytes_keluar"],
            }
        )

    return entri
