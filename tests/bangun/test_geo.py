"""Uji unit untuk bangun/geo.py — simplifikasi GeoJSON batas desa + gzip."""

import gzip
import json
from pathlib import Path

import pytest

from bangun.geo import sederhanakan_berkas, sederhanakan_semua


def _titik_kotak_redundan() -> list[list[float]]:
    """Cincin poligon kotak ~200 titik, banyak titik kolinear redundan per sisi."""
    sudut = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    n_per_sisi = 50
    titik: list[list[float]] = []
    for i in range(4):
        x0, y0 = sudut[i]
        x1, y1 = sudut[i + 1]
        for j in range(n_per_sisi):
            t = j / n_per_sisi
            titik.append([x0 + (x1 - x0) * t, y0 + (y1 - y0) * t])
    titik.append(list(sudut[0]))
    return titik


def _koleksi_dua_fitur() -> dict[str, object]:
    fitur_valid = {
        "type": "Feature",
        "properties": {
            "index": 0,
            "kdprov": "18",
            "kdkab": "1804",
            "kdkec": "180401",
            "kddesa": "1804010001",
            "iddesa": "1801040001",
            "nmprov": "Lampung",
            "nmkab": "Lampung Timur",
            "nmkec": "Kec Uji",
            "nmdesa": "UJI",
            "sumber": "uji",
            "periode": 2024,
        },
        "geometry": {"type": "Polygon", "coordinates": [_titik_kotak_redundan()]},
    }
    fitur_kosong = {
        "type": "Feature",
        "properties": {
            "index": 1,
            "kdprov": "18",
            "kdkab": "1804",
            "kdkec": "180401",
            "kddesa": "1804010002",
            "iddesa": "1801040002",
            "nmprov": "Lampung",
            "nmkab": "Lampung Timur",
            "nmkec": "Kec Uji",
            "nmdesa": "KOSONG",
            "sumber": "uji",
            "periode": 2024,
        },
        "geometry": {"type": "Polygon", "coordinates": []},
    }
    return {"type": "FeatureCollection", "features": [fitur_valid, fitur_kosong]}


@pytest.mark.unit
def test_sederhanakan_berkas_membuang_fitur_kosong_dan_memangkas_properti(
    tmp_path: Path,
) -> None:
    sumber = tmp_path / "sumber.geojson"
    sumber.write_text(json.dumps(_koleksi_dua_fitur()), encoding="utf-8")
    tujuan = tmp_path / "keluaran" / "hasil.geojson.gz"

    hasil = sederhanakan_berkas(sumber, tujuan, toleransi=0.0005)

    assert hasil["n_fitur"] == 1
    assert hasil["n_dibuang"] == 1
    assert hasil["bytes_masuk"] == sumber.stat().st_size
    assert hasil["bytes_keluar"] < hasil["bytes_masuk"]

    assert tujuan.is_file()
    with gzip.open(tujuan, "rt", encoding="utf-8") as berkas:
        isi = json.load(berkas)

    assert isi["type"] == "FeatureCollection"
    assert len(isi["features"]) == 1
    assert isi["features"][0]["properties"] == {
        "iddesa": "1801040001",
        "nmdesa": "UJI",
    }


@pytest.mark.unit
def test_sederhanakan_semua_satu_berkas_menghasilkan_satu_entri_manifest(
    tmp_path: Path,
) -> None:
    dir_sumber = tmp_path / "sumber"
    dir_sumber.mkdir()
    dir_tujuan = tmp_path / "tujuan"

    berkas_sumber = dir_sumber / "1801_uji.geojson"
    fitur = {
        "type": "Feature",
        "properties": {"iddesa": "1801040001", "nmdesa": "UJI"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]],
        },
    }
    koleksi = {"type": "FeatureCollection", "features": [fitur]}
    berkas_sumber.write_text(json.dumps(koleksi), encoding="utf-8")

    entri = sederhanakan_semua(dir_sumber, dir_tujuan, toleransi=0.0005)

    assert len(entri) == 1
    satu = entri[0]
    assert satu["path"] == "geo/1801.geojson.gz"
    assert satu["sumber"] == str(berkas_sumber)
    assert isinstance(satu["sha256"], str)
    assert len(satu["sha256"]) == 64
    assert satu["bytes"] > 0
