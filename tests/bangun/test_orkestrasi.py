"""Uji unit untuk bangun/__main__.py — orkestrator CLI build data-salinan/."""

import json
from pathlib import Path

import pytest

from bangun import __main__ as orkestrator
from bangun import konstanta
from bangun.__main__ import jalankan


def _tulis_json(path: Path, isi: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(isi), encoding="utf-8")


@pytest.fixture
def akar_data_lengkap(tmp_path: Path) -> Path:
    """Bangun pohon `data/` palsu yang mencakup seluruh `ARTEFAK_KONTRAK`.

    Entri tujuan "kartu-ekonomi/indeks.json" diisi daftar kartu index nyata
    (dipakai tahap wilayah, minimal "idkab" + "nmkab"); entri berkas lain
    diisi placeholder `{"x": 1}`; entri direktori diisi satu berkas contoh.
    Bahan metodologi (`BERKAS_METODOLOGI`) sengaja TIDAK dibuat -- itu
    opsional (warning + lewati), bukan kontrak wajib.
    """
    akar = tmp_path / "data"
    for sumber_rel, tujuan_rel in konstanta.ARTEFAK_KONTRAK:
        sumber = akar / sumber_rel
        if tujuan_rel == "kartu-ekonomi/indeks.json":
            _tulis_json(sumber, [{"idkab": "1801", "nmkab": "LAMPUNG BARAT"}])
        elif sumber.suffix == ".json":
            _tulis_json(sumber, {"x": 1})
        else:
            _tulis_json(sumber / "1801.json", {"x": 1})
    return akar


def _argv_lewati_semua(akar_data: Path, dir_keluaran: Path) -> list[str]:
    return [
        "--lewati-geo",
        "--lewati-kembar",
        "--akar-data",
        str(akar_data),
        "--dir-keluaran",
        str(dir_keluaran),
    ]


@pytest.mark.unit
def test_jalankan_happy_path_menulis_manifest_dan_wilayah(
    akar_data_lengkap: Path, tmp_path: Path
) -> None:
    dir_keluaran = tmp_path / "keluar"

    kode = jalankan(_argv_lewati_semua(akar_data_lengkap, dir_keluaran))

    assert kode == 0

    manifest_path = dir_keluaran / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(manifest.keys()) == {"hash", "tanggal", "artefak"}

    assert (dir_keluaran / "wilayah.json").is_file()

    path_artefak = {item["path"] for item in manifest["artefak"]}
    assert "wilayah.json" in path_artefak
    assert "pusat_wilayah.json" in path_artefak


@pytest.mark.unit
def test_jalankan_kontrak_hilang_return_1_tanpa_manifest(
    akar_data_lengkap: Path, tmp_path: Path
) -> None:
    sumber_rel, tujuan_rel = konstanta.ARTEFAK_KONTRAK[2]
    assert tujuan_rel != "kartu-ekonomi/indeks.json"
    (akar_data_lengkap / sumber_rel).unlink()

    dir_keluaran = tmp_path / "keluar"

    kode = jalankan(_argv_lewati_semua(akar_data_lengkap, dir_keluaran))

    assert kode == 1
    assert not (dir_keluaran / "manifest.json").exists()


@pytest.mark.unit
def test_jalankan_toleransi_geo_diparse(
    akar_data_lengkap: Path, tmp_path: Path
) -> None:
    dir_keluaran = tmp_path / "keluar"

    kode = jalankan(
        [
            "--toleransi-geo",
            "0.001",
            *_argv_lewati_semua(akar_data_lengkap, dir_keluaran),
        ]
    )

    assert kode == 0


@pytest.mark.unit
def test_jalankan_tanpa_bendera_lewati_menjalankan_kedua_tahap(
    akar_data_lengkap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cabang KERJA tahap 4 dan 5 (tanpa `--lewati-*`).

    Seluruh uji lain memakai `_argv_lewati_semua`, jadi cabang yang benar-benar
    memanggil precompute kembar dan penyederhanaan geo tidak pernah dijalankan
    — hapus salah satu pemanggilan itu dan suite tetap hijau. Tahapnya
    ditambal (bukan dijalankan sungguhan) karena keduanya butuh sklearn dan
    shapely atas data nyata; yang diuji di sini pemasangannya, bukan isinya.
    """
    dipanggil: list[str] = []

    def _precompute(**kwargs: object) -> list[dict[str, object]]:
        dipanggil.append("kembar")
        return []

    def _sederhanakan(*args: object) -> list[dict[str, object]]:
        dipanggil.append("geo")
        return []

    monkeypatch.setattr(orkestrator, "precompute_semua", _precompute)
    monkeypatch.setattr(orkestrator, "sederhanakan_semua", _sederhanakan)
    dir_keluaran = tmp_path / "keluar"

    kode = jalankan(
        [
            "--akar-data",
            str(akar_data_lengkap),
            "--dir-keluaran",
            str(dir_keluaran),
        ]
    )

    assert kode == 0
    assert dipanggil == ["kembar", "geo"]


@pytest.mark.unit
def test_bendera_lewati_tidak_memanggil_tahapnya(
    akar_data_lengkap: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pasangan uji di atas: dengan bendera, tahapnya TIDAK boleh terpanggil."""

    def _dilarang(*args: object, **kwargs: object) -> list[dict[str, object]]:
        raise AssertionError("tahap yang dilewati tidak boleh dipanggil")

    monkeypatch.setattr(orkestrator, "precompute_semua", _dilarang)
    monkeypatch.setattr(orkestrator, "sederhanakan_semua", _dilarang)
    dir_keluaran = tmp_path / "keluar"

    assert jalankan(_argv_lewati_semua(akar_data_lengkap, dir_keluaran)) == 0
