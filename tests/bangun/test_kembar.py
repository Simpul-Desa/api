"""Uji untuk bangun/kembar.py — precompute desa kembar (kNN dalam kabupaten)."""

from pathlib import Path

import numpy as np
import pytest

from bangun.kembar import hitung_tetangga_kab, precompute_semua


def _matriks_lima_titik() -> np.ndarray:
    """5 titik 16-dim: d0≈d1 (jarak kecil), d2/d3 sedang, d4 jauh."""
    skalar = np.array([0.0, 0.05, 5.0, 6.0, 100.0])
    return np.repeat(skalar[:, None], 16, axis=1)


@pytest.mark.unit
def test_hitung_tetangga_kab_titik_dekat_jadi_tetangga_pertama() -> None:
    x16 = _matriks_lima_titik()
    iddesa = ["d0", "d1", "d2", "d3", "d4"]

    pemetaan, p95 = hitung_tetangga_kab(x16, iddesa, k=3)

    assert pemetaan["d0"][0]["iddesa"] == "d1"
    assert p95 > 0.0


@pytest.mark.unit
def test_hitung_tetangga_kab_diri_sendiri_tidak_pernah_muncul() -> None:
    x16 = _matriks_lima_titik()
    iddesa = ["d0", "d1", "d2", "d3", "d4"]

    pemetaan, _ = hitung_tetangga_kab(x16, iddesa, k=3)

    for id_asal, tetangga in pemetaan.items():
        assert all(t["iddesa"] != id_asal for t in tetangga)


@pytest.mark.unit
def test_hitung_tetangga_kab_persen_dalam_rentang_dan_maks_k() -> None:
    x16 = _matriks_lima_titik()
    iddesa = ["d0", "d1", "d2", "d3", "d4"]
    k = 3

    pemetaan, _ = hitung_tetangga_kab(x16, iddesa, k=k)

    for tetangga in pemetaan.values():
        assert len(tetangga) <= k
        for t in tetangga:
            assert 0.0 <= t["persen"] <= 100.0


@pytest.mark.unit
def test_hitung_tetangga_kab_terurut_menurun_persen() -> None:
    x16 = _matriks_lima_titik()
    iddesa = ["d0", "d1", "d2", "d3", "d4"]

    pemetaan, _ = hitung_tetangga_kab(x16, iddesa, k=3)

    for tetangga in pemetaan.values():
        persen_list = [t["persen"] for t in tetangga]
        assert persen_list == sorted(persen_list, reverse=True)


@pytest.mark.unit
def test_hitung_tetangga_kab_satu_desa() -> None:
    x16 = np.zeros((1, 16))

    pemetaan, p95 = hitung_tetangga_kab(x16, ["d0"], k=5)

    assert pemetaan == {"d0": []}
    assert p95 == 0.0


@pytest.mark.unit
def test_hitung_tetangga_kab_kosong() -> None:
    x16 = np.zeros((0, 16))

    pemetaan, p95 = hitung_tetangga_kab(x16, [], k=5)

    assert pemetaan == {}
    assert p95 == 0.0


@pytest.mark.unit
def test_hitung_tetangga_kab_titik_identik_persen_100_tanpa_crash() -> None:
    # n == k+1 (k=2 -> k_efektif=3=n) supaya diri sendiri pasti ikut
    # terpilih walau tiap jarak berpasangan 0 (lihat catatan tie-break
    # di docstring hitung_tetangga_kab).
    x16 = np.zeros((3, 16))
    iddesa = ["d0", "d1", "d2"]

    pemetaan, p95 = hitung_tetangga_kab(x16, iddesa, k=2)

    assert p95 == 0.0
    for id_asal, tetangga in pemetaan.items():
        assert len(tetangga) == 2
        assert all(t["persen"] == 100.0 for t in tetangga)
        assert all(t["iddesa"] != id_asal for t in tetangga)


@pytest.mark.integration
def test_precompute_semua_satu_kabupaten_kota_metro(tmp_path: Path) -> None:
    manifest_entries = precompute_semua(hanya_kab={"1872"}, dir_keluaran=tmp_path)

    berkas = tmp_path / "desa-kembar" / "1872.json"
    assert berkas.is_file()

    import json

    payload = json.loads(berkas.read_text(encoding="utf-8"))
    assert payload["idkab"] == "1872"
    assert payload["k"] == 12
    assert len(payload["desa"]) == 22

    for tetangga in payload["desa"].values():
        assert 0 < len(tetangga) <= 12
        persen_list = [t["persen"] for t in tetangga]
        assert persen_list == sorted(persen_list, reverse=True)

    assert len(manifest_entries) == 1
    assert manifest_entries[0]["path"] == "desa-kembar/1872.json"
