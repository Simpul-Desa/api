"""Uji unit untuk modul manifest (bangun/manifest.py)."""

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from bangun.manifest import sha256_berkas, tulis_manifest


@pytest.mark.unit
def test_sha256_berkas_cocok_hashlib(tmp_path: Path) -> None:
    berkas = tmp_path / "contoh.txt"
    berkas.write_bytes(b"abc")

    hasil = sha256_berkas(berkas)

    assert hasil == hashlib.sha256(b"abc").hexdigest()


@pytest.mark.unit
def test_tulis_manifest_menulis_berkas_dan_terurut(tmp_path: Path) -> None:
    entri = [
        {"path": "b/kedua.json", "sumber": "sumber-b", "sha256": "bb", "bytes": 2},
        {"path": "a/pertama.json", "sumber": "sumber-a", "sha256": "aa", "bytes": 1},
    ]

    hasil = tulis_manifest(tmp_path, entri)

    berkas_manifest = tmp_path / "manifest.json"
    assert berkas_manifest.exists()

    isi = json.loads(berkas_manifest.read_text(encoding="utf-8"))
    assert set(isi.keys()) == {"hash", "tanggal", "artefak"}
    assert isi == hasil
    assert [item["path"] for item in isi["artefak"]] == [
        "a/pertama.json",
        "b/kedua.json",
    ]


@pytest.mark.unit
def test_tulis_manifest_deterministik_tanpa_bergantung_urutan(
    tmp_path: Path,
) -> None:
    entri_1 = [
        {"path": "b.json", "sumber": "s", "sha256": "hb", "bytes": 2},
        {"path": "a.json", "sumber": "s", "sha256": "ha", "bytes": 1},
    ]
    entri_2 = [
        {"path": "a.json", "sumber": "s", "sha256": "ha", "bytes": 1},
        {"path": "b.json", "sumber": "s", "sha256": "hb", "bytes": 2},
    ]

    hasil_1 = tulis_manifest(tmp_path / "keluar1", entri_1)
    hasil_2 = tulis_manifest(tmp_path / "keluar2", entri_2)

    assert hasil_1["hash"] == hasil_2["hash"]


@pytest.mark.unit
def test_tulis_manifest_hash_berbeda_jika_sha256_berbeda(tmp_path: Path) -> None:
    entri_dasar = [{"path": "a.json", "sumber": "s", "sha256": "ha", "bytes": 1}]
    entri_ubah = [{"path": "a.json", "sumber": "s", "sha256": "hz", "bytes": 1}]

    hasil_dasar = tulis_manifest(tmp_path / "keluar1", entri_dasar)
    hasil_ubah = tulis_manifest(tmp_path / "keluar2", entri_ubah)

    assert hasil_dasar["hash"] != hasil_ubah["hash"]


@pytest.mark.unit
def test_tulis_manifest_hash_sesuai_kontrak_gabungan(tmp_path: Path) -> None:
    entri = [
        {"path": "a.json", "sumber": "s", "sha256": "ha", "bytes": 1},
        {"path": "b.json", "sumber": "s", "sha256": "hb", "bytes": 2},
    ]

    hasil = tulis_manifest(tmp_path, entri)

    gabungan = "a.json:ha\n" + "b.json:hb\n"
    assert hasil["hash"] == hashlib.sha256(gabungan.encode("utf-8")).hexdigest()


@pytest.mark.unit
def test_tulis_manifest_tanggal_hari_ini(tmp_path: Path) -> None:
    hasil = tulis_manifest(tmp_path, [])

    assert hasil["tanggal"] == date.today().isoformat()  # noqa: DTZ011
