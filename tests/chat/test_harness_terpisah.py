"""Penjaga: `harness/` tidak boleh ikut terkumpul pytest.

`harness/jalankan.py` memanggil Gemini SUNGGUHAN dan memakan kuota free
tier. Yang menahannya hanyalah `testpaths = ["tests"]` di `pyproject.toml`.
Melebarkan nilai itu membuat `pytest` polos membakar kuota tanpa ada yang
menyadarinya - tidak ada galat, hanya tagihan dan kuota habis. Uji ini
gagal begitu penjaganya dilepas.
"""

# `tomllib` didahulukan dari `from pathlib import Path`: isort (mengenal
# stdlib lewat runtime 3.14, tempat `tomllib` sudah stdlib) menerima urutan
# ini, tapi ruff (daftar stdlib bawaannya belum mengenal `tomllib`)
# menganggapnya bukan stdlib. noqa meredam ketidaksepakatan itu tanpa
# mengubah urutan yang isort inginkan. Ruff menempatkan diagnosis I001 di
# baris PERTAMA blok impor yang dianggapnya tak-runtut -- sejak `import re`
# ditambah di depan, baris itulah (bukan lagi baris `tomllib`) yang wajib
# membawa noqa-nya.
import re  # noqa: I001
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_AKAR = Path(__file__).resolve().parents[2]

# `hakimi` hanya bisa menembak jaringan lewat `genai.Client` (satu-satunya
# panggilan vendor di `harness/hakim.py`). Berkas uji yang menambalnya --
# pola persis yang dipakai `tests/chat/test_penilai.py` -- tidak mungkin
# menyentuh Gemini sungguhan walau memanggil `hakimi`. Regex tahan spasi
# ganda/baris baru di sekitar argumen `setattr`.
_POLA_TAMBALAN_KLIEN_HAKIM = re.compile(
    r"setattr\s*\(\s*hakim\.genai\s*,\s*[\"']Client[\"']"
)


def _periksa_isi_uji(isi: str, penanda: str) -> None:
    """Tegaskan satu isi berkas uji (sebagai string) tidak bisa menembak
    Gemini sungguhan lewat jalur `harness/`.

    `harness.jalankan` dilarang MUTLAK, tanpa pengecualian -- itu runner
    yang benar-benar memanggil API. `hakimi` boleh disebut/dipanggil HANYA
    bila `penanda` yang sama juga menambal `genai.Client` milik modul
    hakim: tanpa tambalan itu, `hakimi` menembak Gemini sungguhan; dengan
    tambalan itu, NOL jaringan terjadi apa pun isi berkas selebihnya.
    """
    assert "harness.jalankan" not in isi, f"{penanda} mengimpor harness.jalankan"
    if "hakimi" in isi:
        assert _POLA_TAMBALAN_KLIEN_HAKIM.search(isi), (
            f"{penanda} menyebut/memanggil hakimi tapi tidak menambal "
            "genai.Client milik modul hakim (pola: monkeypatch.setattr("
            '"hakim.genai", "Client", ...)). Tanpa tambalan itu, hakimi '
            "menembak Gemini sungguhan. Tambal genai.Client sebelum "
            "memanggil hakimi di uji ini."
        )


def test_testpaths_hanya_tests() -> None:
    with open(_AKAR / "pyproject.toml", "rb") as berkas:
        konfigurasi = tomllib.load(berkas)
    testpaths = konfigurasi["tool"]["pytest"]["ini_options"]["testpaths"]
    assert testpaths == ["tests"]


def test_harness_di_luar_testpaths() -> None:
    dir_harness = _AKAR / "harness"
    dir_tests = _AKAR / "tests"
    assert dir_harness.is_dir()
    assert dir_tests not in dir_harness.parents
    assert dir_harness not in dir_tests.parents


def test_runner_harness_tidak_diimpor_uji() -> None:
    # `harness.penilai` (fungsi `nilai`, murni) DAN `parse_putusan` dari
    # `harness.hakim` DIIZINKAN diimpor uji — keduanya sekadar parser/aturan
    # tanpa panggilan jaringan (lihat tests/chat/test_penilai.py). Yang
    # dilarang MUTLAK: modul `harness.jalankan` (runner, memanggil Gemini
    # sungguhan). Simbol `hakimi` sendiri BOLEH disebut/dipanggil uji —
    # yang tidak boleh adalah menjalankannya terhadap klien Gemini
    # SUNGGUHAN, dan `genai.Client` adalah satu-satunya pintu jaringan yang
    # bisa dicapai `hakimi`. Karena itu `_periksa_isi_uji` meloloskan
    # `hakimi` hanya bila berkas yang sama juga menambal `genai.Client`
    # milik modul hakim (lihat tests/chat/test_penilai.py). Berkas penjaga
    # ini sendiri dikecualikan dari pindaian karena literal string "hakimi"
    # di komentar ini akan menandai dirinya sendiri.
    diri_sendiri = Path(__file__).resolve()
    for berkas in (_AKAR / "tests").rglob("*.py"):
        if berkas.resolve() == diri_sendiri:
            continue
        isi = berkas.read_text(encoding="utf-8")
        _periksa_isi_uji(isi, str(berkas))


def test_penjaga_menolak_hakimi_tanpa_tambalan_klien() -> None:
    isi_berbahaya = (
        "from harness.hakim import hakimi\n\n"
        "async def test_x() -> None:\n"
        "    await hakimi(kasus, jawaban, pengaturan)\n"
    )
    with pytest.raises(AssertionError, match="menyebut/memanggil hakimi"):
        _periksa_isi_uji(isi_berbahaya, "berkas-uji-palsu.py")

    isi_aman = isi_berbahaya + (
        '\nmonkeypatch.setattr(hakim.genai, "Client", _KlienGagalPalsu)\n'
    )
    _periksa_isi_uji(isi_aman, "berkas-uji-palsu.py")  # tidak melempar
