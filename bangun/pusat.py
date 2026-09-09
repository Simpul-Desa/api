"""Hitung pusat (rerata bbox per fitur) tiap kabupaten dari GeoJSON `bangun/geo.py`.

Dipakai `app/` sebagai koordinat lingkaran berjenjang provinsi->kabupaten pada
peta beranda (endpoint `GET /api/wilayah/pusat`, lihat `src/wilayah/router.py`
+ `src/datastore.py`). Pusat provinsi TIDAK dihitung di sini — itu rerata
pusat kabupatennya, dihitung API saat startup supaya menambah kabupaten baru
tidak perlu membangun ulang provinsi.

Pusat kabupaten = RERATA titik tengah bbox PER FITUR (satu titik per desa:
tengah bbox geometri tiap feature GeoJSON), BUKAN tengah bbox gabungan
seluruh fitur. Kabupaten berpulau melenceng jauh ke laut kalau dipakai bbox
gabungan — satu pulau terluar menyeret titik ekstrem bbox sejauh jaraknya
dari daratan utama, walau cuma satu desa kecil di pulau itu (terbukti:
Pangkajene 139 km ke laut, Kotabaru 55,8 km, Jepara 38 km karena Karimunjawa;
9 dari 97 kabupaten melenceng >15 km — lihat CLAUDE.md akar bagian jebakan
teknis). Merata-ratakan titik tengah bbox tiap desa membuat tiap desa
menyumbang bobot yang sama, sehingga satu-dua desa pencilan geografis tidak
menyandera hasil seperti pada bbox gabungan.

Bbox satu fitur = titik ekstrem (min/maks) lon/lat seluruh koordinat fitur
itu (Polygon maupun MultiPolygon — seluruh bagiannya tetap digabung jadi
SATU bbox milik fitur itu; formula baru hanya mengubah agregasi ANTAR fitur,
bukan bagaimana satu fitur ber-MultiPolygon dihitung). Aritmetika sederhana
saja — tanpa dependensi geospasial baru (shapely dipakai `bangun/geo.py`,
bukan di sini).
"""

import gzip
import json
import logging
import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from bangun.konstanta import AKHIRAN_GEO

logger = logging.getLogger(__name__)


def _telusuri_titik(koordinat: Any) -> Iterator[tuple[float, float]]:
    """Telusuri array `coordinates` GeoJSON rekursif, hasilkan tiap titik (lon, lat).

    Menangani Polygon (3 level nesting) maupun MultiPolygon (4 level) tanpa
    mengasumsikan kedalamannya: turun rekursif selama elemen pertama masih
    berupa list, berhenti begitu ketemu pasangan angka [lon, lat]. Array
    kosong (mis. geometri fitur yang dibuang `sederhanakan_berkas`) tidak
    menghasilkan titik apa pun.
    """
    if not koordinat:
        return
    if isinstance(koordinat[0], int | float):
        yield (koordinat[0], koordinat[1])
        return
    for sub in koordinat:
        yield from _telusuri_titik(sub)


def _pusat_bbox_fitur(fitur: dict[str, Any]) -> tuple[float, float] | None:
    """Titik tengah bbox geometri SATU fitur (satu desa).

    Bbox mencakup seluruh koordinat fitur itu (Polygon maupun MultiPolygon —
    seluruh bagian MultiPolygon-nya digabung jadi satu bbox milik fitur ini).
    None bila fitur tidak bergeometri (`geometry: null`, GeoJSON sah) atau
    geometrinya tidak berisi satu titik koordinat pun (mis. dibuang
    `sederhanakan_berkas` karena jadi kosong setelah simplifikasi).
    """
    geometri = fitur.get("geometry")
    if not geometri:
        return None

    min_lon = min_lat = math.inf
    max_lon = max_lat = -math.inf
    ada_titik = False
    for lon, lat in _telusuri_titik(geometri.get("coordinates", [])):
        ada_titik = True
        min_lon, max_lon = min(min_lon, lon), max(max_lon, lon)
        min_lat, max_lat = min(min_lat, lat), max(max_lat, lat)

    if not ada_titik:
        return None
    return ((min_lon + max_lon) / 2, (min_lat + max_lat) / 2)


def hitung_pusat_kabupaten(koleksi: dict[str, Any]) -> list[float] | None:
    """Pusat kabupaten = rerata titik tengah bbox tiap fitur (desa) `koleksi`.

    Tiap fitur menyumbang SATU titik tanpa memandang ukurannya, BUKAN tengah
    bbox gabungan seluruh fitur — lihat docstring modul untuk alasannya
    (kabupaten berpulau melenceng jauh ke laut dengan bbox gabungan). Fitur
    tanpa geometri atau berkoordinat kosong tidak menyumbang titik.

    None bila `koleksi` tidak berisi satu fitur bergeometri pun.
    """
    titik: list[tuple[float, float]] = []
    for fitur in koleksi.get("features", []):
        pusat_fitur = _pusat_bbox_fitur(fitur)
        if pusat_fitur is not None:
            titik.append(pusat_fitur)

    if not titik:
        return None

    n = len(titik)
    return [sum(t[0] for t in titik) / n, sum(t[1] for t in titik) / n]


def hitung_pusat_semua(dir_geo: Path) -> dict[str, object]:
    """Hitung pusat tiap kabupaten dari seluruh `*.geojson.gz` di `dir_geo`.

    idkab diambil dari nama berkas (`bangun/geo.py` menulis `<idkab>.geojson.gz`).
    Kabupaten yang berkasnya tidak berisi satu koordinat pun dilewati dengan
    log peringatan, bukan menghentikan build. Direktori kosong atau belum
    dibangun (`--lewati-geo` pada build pertama/output bersih) menghasilkan
    daftar kosong, bukan galat — tapi dicatat `logger.warning` (bukan info)
    karena artefak kosong berarti `src/datastore.py` menolak
    `pusat_wilayah.json` ini saat startup (503 `DATA_BELUM_SIAP`).
    """
    kabupaten: list[dict[str, object]] = []
    for berkas in sorted(dir_geo.glob(f"*{AKHIRAN_GEO}")):
        idkab = berkas.name.removesuffix(AKHIRAN_GEO)
        with gzip.open(berkas, "rt", encoding="utf-8") as sumber:
            koleksi = json.load(sumber)

        pusat = hitung_pusat_kabupaten(koleksi)
        if pusat is None:
            logger.warning(
                "%s: tidak ada satu koordinat pun, kabupaten %s dilewati dari pusat_wilayah",
                berkas,
                idkab,
            )
            continue

        kabupaten.append({"idkab": idkab, "pusat": pusat})

    if kabupaten:
        logger.info(
            "Hitung pusat wilayah: %d kabupaten dari %s", len(kabupaten), dir_geo
        )
    else:
        logger.warning(
            "Hitung pusat wilayah: 0 kabupaten dari %s (direktori geo kosong/belum dibangun)",
            dir_geo,
        )
    return {"kabupaten": kabupaten}


def tulis_pusat_wilayah(dir_geo: Path, dir_keluaran: Path) -> Path:
    """Hitung pusat dari `dir_geo` lalu tulis ke `dir_keluaran/pusat_wilayah.json`.

    Args:
        dir_geo: direktori `*.geojson.gz` per kabupaten (keluaran `bangun/geo.py`).
        dir_keluaran: direktori tujuan; dibuat (beserta induknya) jika belum
            ada.

    Returns:
        Path berkas `pusat_wilayah.json` yang ditulis.
    """
    pusat = hitung_pusat_semua(dir_geo)

    dir_keluaran.mkdir(parents=True, exist_ok=True)
    path_keluaran = dir_keluaran / "pusat_wilayah.json"
    path_keluaran.write_text(
        json.dumps(pusat, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Tulis pusat_wilayah.json ke %s", path_keluaran)

    return path_keluaran
