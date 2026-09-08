"""Uji unit untuk amplop respons seragam."""

import pytest

from src.models import Amplop, Meta, gagal, sukses


@pytest.mark.unit
def test_sukses_tanpa_meta() -> None:
    hasil = sukses({"a": 1})

    assert hasil.model_dump() == {
        "sukses": True,
        "data": {"a": 1},
        "galat": None,
        "meta": None,
    }


@pytest.mark.unit
def test_sukses_dengan_meta() -> None:
    hasil = sukses([1], meta=Meta(total=1, hal=1, batas=50))

    dump = hasil.model_dump()
    assert dump["meta"] == {"total": 1, "hal": 1, "batas": 50, "parameter": None}
    assert dump["sukses"] is True
    assert dump["data"] == [1]
    assert dump["galat"] is None


@pytest.mark.unit
def test_gagal() -> None:
    hasil = gagal("DESA_TIDAK_ADA", "desa tidak dikenal")

    assert hasil.model_dump() == {
        "sukses": False,
        "data": None,
        "galat": {"kode": "DESA_TIDAK_ADA", "pesan": "desa tidak dikenal"},
        "meta": None,
    }


@pytest.mark.unit
def test_kunci_json_persis() -> None:
    hasil = sukses({"a": 1})

    assert set(hasil.model_dump().keys()) == {"sukses", "data", "galat", "meta"}


@pytest.mark.unit
def test_amplop_tipe_dict() -> None:
    amplop: Amplop[dict] = Amplop(sukses=True, data={"x": 1})

    assert amplop.data == {"x": 1}
