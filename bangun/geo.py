"""Skrip build: sederhanakan geometri batas desa (GeoJSON) dan kompres gzip.

Menyederhanakan geometri MultiPolygon batas desa dengan shapely.simplify
(preserve_topology=True), memangkas properti ke {"iddesa", "nmdesa"} plus
`pusat` (titik tengah bbox geometri SETELAH disederhanakan, dibulatkan 5
desimal — lihat `bangun.pusat.pusat_bbox_fitur`), lalu menulis
FeatureCollection hasil sebagai .geojson.gz (gzip level 9). Sengaja hanya
pakai `json` + `shapely` (tanpa geopandas) untuk menghindari dependensi
driver I/O geopandas.
"""

import gzip
import hashlib
import json
import logging
from pathlib import Path

from shapely.geometry import mapping, shape

from bangun.konstanta import AKHIRAN_GEO
from bangun.pusat import pusat_bbox_fitur

logger = logging.getLogger(__name__)

PROPERTI_DIPERTAHANKAN = ("iddesa", "nmdesa")


def sederhanakan_berkas(sumber: Path, tujuan: Path, toleransi: float) -> dict[str, int]:
    """Sederhanakan satu berkas GeoJSON batas desa, tulis sebagai .geojson.gz.

    Tiap fitur disederhanakan dengan shapely.simplify (preserve_topology=True).
    Fitur tanpa geometri (`geometry: null`, GeoJSON sah) menggagalkan build
    dengan `ValueError` bernama `iddesa` dan berkas sumbernya — desa tanpa
    batas adalah masalah data di `data/` yang harus dibetulkan di sana, bukan
    baris yang boleh hilang diam-diam dari artefak yang disajikan `api/`.
    Fitur yang geometrinya jadi kosong setelah disederhanakan dibuang dan
    dihitung; total yang dibuang dicatat lewat log peringatan (hanya bila ada
    yang dibuang). Properti fitur yang disimpan adalah "iddesa", "nmdesa",
    dan `pusat` (titik tengah bbox geometri SETELAH disederhanakan,
    dibulatkan 5 desimal — lihat `bangun.pusat.pusat_bbox_fitur`). Hasil
    ditulis sebagai FeatureCollection JSON yang dikompres gzip level 9 ke
    `tujuan` (direktori induk dibuat bila belum ada).
    """
    bytes_masuk = sumber.stat().st_size
    data = json.loads(sumber.read_text(encoding="utf-8"))

    fitur_keluaran: list[dict[str, object]] = []
    n_dibuang = 0
    for fitur in data["features"]:
        geometri = fitur.get("geometry")
        if geometri is None:
            # Desa tanpa geometri adalah masalah data di data/, bukan sesuatu
            # yang boleh diserap api/ dengan membuang barisnya diam-diam dari
            # artefak yang disajikan (itu memindahkan sebuah desa dari peta
            # tanpa jejak). Alternatif "lewati + hitung terpisah" sudah
            # dipertimbangkan dan ditolak: build yang gagal keras — seperti
            # perilaku shape(None) sebelum properti `pusat` ada — lebih baik
            # daripada kehilangan data senyap di artefak yang dilayani.
            iddesa = fitur.get("properties", {}).get("iddesa")
            raise ValueError(
                f"{sumber}: fitur iddesa={iddesa!r} tidak bergeometri (geometry: null)"
            )

        geom = shape(geometri).simplify(toleransi, preserve_topology=True)
        if geom.is_empty:
            n_dibuang += 1
            continue

        properti_asli = fitur.get("properties", {})
        properti_baru = {
            kunci: properti_asli.get(kunci) for kunci in PROPERTI_DIPERTAHANKAN
        }
        geometri_keluar = mapping(geom)
        pusat = pusat_bbox_fitur({"geometry": geometri_keluar})
        if pusat is None:
            # Tercapai bila geom tidak punya kunci `coordinates` di
            # mapping()-nya walau lolos cek is_empty di atas — mis.
            # GeometryCollection tak-kosong, yang di-mapping jadi
            # {"type", "geometries"} tanpa "coordinates" sama sekali.
            logger.warning(
                "%s: iddesa=%s pusat tidak terhitung (geometri tanpa coordinates)",
                sumber,
                properti_baru.get("iddesa"),
            )
        properti_baru["pusat"] = (
            [round(pusat[0], 5), round(pusat[1], 5)] if pusat is not None else None
        )
        fitur_keluaran.append(
            {
                "type": "Feature",
                "properties": properti_baru,
                "geometry": geometri_keluar,
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
