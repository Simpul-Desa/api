"""Uji unit untuk bangun/salin.py — salin artefak kontrak dan metodologi."""

import json
import logging
import re
from pathlib import Path

import pytest

from bangun.konstanta import ARTEFAK_KONTRAK, BERKAS_METODOLOGI
from bangun.salin import salin_kontrak, salin_metodologi

REGEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _tulis_json(path: Path, isi: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(isi), encoding="utf-8")


@pytest.fixture
def akar_data_palsu(tmp_path: Path) -> Path:
    """Bangun pohon sumber palsu yang meniru layout ARTEFAK_KONTRAK.

    Entri berakhiran ".json" dibuat sebagai berkas tunggal; entri lain
    (mis. direktori "kartu") dibuat sebagai direktori berisi dua berkas
    JSON contoh.
    """
    akar = tmp_path / "data"
    for sumber_rel, _tujuan_rel in ARTEFAK_KONTRAK:
        sumber = akar / sumber_rel
        if sumber.suffix == ".json":
            _tulis_json(sumber, {"x": 1})
        else:
            _tulis_json(sumber / "1801.json", {"x": 1})
            _tulis_json(sumber / "1802.json", {"x": 1})
    return akar


@pytest.fixture
def akar_proyek_sebagian(tmp_path: Path) -> Path:
    """Akar proyek palsu yang hanya punya GLOSSARY.md dari BERKAS_METODOLOGI."""
    akar = tmp_path / "proyek"
    akar.mkdir(parents=True, exist_ok=True)
    (akar / "GLOSSARY.md").write_text("# Glossary\n", encoding="utf-8")
    return akar


@pytest.mark.unit
def test_salin_kontrak_menyalin_semua_berkas(
    akar_data_palsu: Path, tmp_path: Path
) -> None:
    dir_keluaran = tmp_path / "keluar"

    entri = salin_kontrak(akar_data=akar_data_palsu, dir_keluaran=dir_keluaran)

    assert len(entri) == 20
    for item in entri:
        assert REGEX_SHA256.match(str(item["sha256"]))
        assert isinstance(item["bytes"], int)
        assert item["bytes"] > 0

    entri_kartu = [
        item for item in entri if str(item["path"]).startswith("kartu-ekonomi/kartu/")
    ]
    assert len(entri_kartu) == 2


@pytest.mark.unit
def test_salin_kontrak_menyalin_direktori_produksi_provinsi(
    akar_data_palsu: Path, tmp_path: Path
) -> None:
    """Direktori produksi citra per provinsi (mis. prov 18) tersalin ke citra-potensi/produksi/<prov>/."""
    dir_keluaran = tmp_path / "keluar"
    sumber_produksi = (
        akar_data_palsu
        / "machine-learning"
        / "citra-potensi-desa"
        / "v5"
        / "produksi"
        / "18"
    )
    _tulis_json(sumber_produksi / "sel_uji.json", {"x": 1})

    entri = salin_kontrak(akar_data=akar_data_palsu, dir_keluaran=dir_keluaran)

    tujuan = dir_keluaran / "citra-potensi" / "produksi" / "18" / "sel_uji.json"
    assert tujuan.exists()
    entri_produksi = [
        item
        for item in entri
        if str(item["path"]) == "citra-potensi/produksi/18/sel_uji.json"
    ]
    assert len(entri_produksi) == 1


@pytest.mark.unit
def test_salin_kontrak_sumber_hilang_raise_value_error(
    akar_data_palsu: Path, tmp_path: Path
) -> None:
    sumber_rel, _tujuan_rel = ARTEFAK_KONTRAK[2]
    sumber_hilang = akar_data_palsu / sumber_rel
    sumber_hilang.unlink()

    with pytest.raises(ValueError, match=re.escape(str(sumber_hilang))):
        salin_kontrak(akar_data=akar_data_palsu, dir_keluaran=tmp_path / "keluar")


@pytest.mark.unit
def test_salin_metodologi_sebagian_hilang_warning_tanpa_exception(
    akar_proyek_sebagian: Path,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    dir_keluaran = tmp_path / "keluar"

    entri = salin_metodologi(
        akar_proyek=akar_proyek_sebagian, dir_keluaran=dir_keluaran
    )

    assert len(entri) == 1
    assert entri[0]["path"] == "metodologi/GLOSSARY.md"

    jumlah_hilang = len(BERKAS_METODOLOGI) - 1
    assert caplog.text.count("tidak ditemukan") == jumlah_hilang
