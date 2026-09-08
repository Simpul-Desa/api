"""Uji unit untuk bangun/wilayah.py — turunan provinsi/kabupaten dari indeks."""

import json
from pathlib import Path

import pytest

from bangun.wilayah import tulis_wilayah, turunkan_wilayah


def _indeks_contoh() -> list[dict[str, object]]:
    return [
        {"idkab": "1801", "nmkab": "Lampung Selatan"},
        {"idkab": "1802", "nmkab": "Lampung Tengah"},
        {"idkab": "1801", "nmkab": "Lampung Selatan"},
        {"idkab": "3301", "nmkab": "Cilacap"},
        {"idkab": "1802", "nmkab": "Lampung Tengah"},
    ]


@pytest.mark.unit
def test_turunkan_wilayah_dedup_dan_urut_kabupaten() -> None:
    hasil = turunkan_wilayah(_indeks_contoh())

    assert hasil["kabupaten"] == [
        {"idkab": "1801", "nmkab": "Lampung Selatan", "idprov": "18"},
        {"idkab": "1802", "nmkab": "Lampung Tengah", "idprov": "18"},
        {"idkab": "3301", "nmkab": "Cilacap", "idprov": "33"},
    ]


@pytest.mark.unit
def test_turunkan_wilayah_provinsi_hanya_yang_hadir_dan_urut() -> None:
    hasil = turunkan_wilayah(_indeks_contoh())

    assert hasil["provinsi"] == [
        {"idprov": "18", "nama": "Lampung"},
        {"idprov": "33", "nama": "Jawa Tengah"},
    ]


@pytest.mark.unit
def test_turunkan_wilayah_prefix_tak_dikenal_raise_value_error() -> None:
    indeks: list[dict[str, object]] = [{"idkab": "9901", "nmkab": "Entah"}]

    with pytest.raises(ValueError, match="99"):
        turunkan_wilayah(indeks)


@pytest.mark.unit
def test_tulis_wilayah_menulis_berkas_dan_round_trip(tmp_path: Path) -> None:
    indeks = _indeks_contoh()

    path_keluaran = tulis_wilayah(indeks, tmp_path)

    assert path_keluaran == tmp_path / "wilayah.json"
    assert path_keluaran.is_file()

    isi = json.loads(path_keluaran.read_text(encoding="utf-8"))
    assert isi == turunkan_wilayah(indeks)


@pytest.mark.unit
def test_tulis_wilayah_membuat_direktori_induk(tmp_path: Path) -> None:
    dir_keluaran = tmp_path / "sub" / "dir"

    path_keluaran = tulis_wilayah(_indeks_contoh(), dir_keluaran)

    assert path_keluaran.is_file()
