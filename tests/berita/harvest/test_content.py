"""Uji unit tahap isi artikel (`src/berita/isi.py`)."""

import logging
from typing import Any, Self

import pytest

from src.berita.harvest import content as isi

HTML_SEHAT = (
    "<html><head><title>Judul</title></head><body>"
    "<nav>Menu Beranda</nav>"
    "<p>Desa Contoh di Kabupaten Uji panen raya kopi. Hasilnya naik.</p>"
    "<script>var x = 1;</script>"
    "</body></html>" + "<!-- pengisi -->" * 200
)
HTML_BLOKIR = "<html><body>Just a moment... checking your browser</body></html>"


class _ResponsPalsu:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


class _ScraperPalsu:
    """Ganda `cloudscraper.create_scraper()`; `meledak` uji sesi ditutup saat galat."""

    def __init__(
        self, respons: _ResponsPalsu | None = None, meledak: bool = False
    ) -> None:
        self._respons = respons
        self._meledak = meledak
        self.n_panggil = 0
        self.n_tutup = 0

    def get(self, url: str, timeout: float) -> _ResponsPalsu:
        self.n_panggil += 1
        if self._meledak:
            raise ConnectionError("putus total")
        assert self._respons is not None
        return self._respons

    def close(self) -> None:
        self.n_tutup += 1

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@pytest.fixture(autouse=True)
def _tanpa_jeda(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(isi.time, "sleep", lambda detik: None)


@pytest.mark.unit
def test_kena_blokir_positif_dan_negatif() -> None:
    assert isi.kena_blokir(HTML_BLOKIR) is True
    assert isi.kena_blokir(HTML_SEHAT) is False


@pytest.mark.unit
def test_ambil_html_sukses_requests_percobaan_pertama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    panggilan: list[str] = []

    def _get(url: str, headers: dict[str, str], timeout: float) -> _ResponsPalsu:
        panggilan.append(url)
        return _ResponsPalsu(200, HTML_SEHAT)

    monkeypatch.setattr(isi.requests, "get", _get)

    # Act
    html, cara = isi.ambil_html("https://p.id/a")

    # Assert
    assert cara == "requests"
    assert html == HTML_SEHAT
    assert len(panggilan) == 1


@pytest.mark.unit
def test_ambil_html_403_gagal_cepat_tanpa_badai_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sinyal anti-bot langsung ganti cara — requests hanya dipanggil sekali."""
    panggilan: list[str] = []

    def _get(url: str, headers: dict[str, str], timeout: float) -> _ResponsPalsu:
        panggilan.append(url)
        return _ResponsPalsu(403, "Forbidden")

    scraper = _ScraperPalsu(_ResponsPalsu(403, "Forbidden"))
    monkeypatch.setattr(isi.requests, "get", _get)
    monkeypatch.setattr(isi.cloudscraper, "create_scraper", lambda: scraper)

    html, cara = isi.ambil_html("https://p.id/a")

    assert (html, cara) == (None, None)
    assert len(panggilan) == 1
    assert scraper.n_panggil == 1


@pytest.mark.unit
def test_ambil_html_blokir_200_pindah_ke_cloudscraper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Halaman blokir ber-status 200 tidak boleh lolos sebagai sukses."""
    monkeypatch.setattr(
        isi.requests,
        "get",
        lambda url, headers, timeout: _ResponsPalsu(200, HTML_BLOKIR),
    )
    scraper = _ScraperPalsu(_ResponsPalsu(200, HTML_SEHAT))
    monkeypatch.setattr(isi.cloudscraper, "create_scraper", lambda: scraper)

    html, cara = isi.ambil_html("https://p.id/a")

    assert cara == "cloudscraper"
    assert html == HTML_SEHAT


@pytest.mark.unit
def test_ambil_html_galat_transien_dicoba_ulang(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keadaan = {"n": 0}

    def _get(url: str, headers: dict[str, str], timeout: float) -> _ResponsPalsu:
        keadaan["n"] += 1
        if keadaan["n"] == 1:
            raise ConnectionError("putus sesaat")
        return _ResponsPalsu(200, HTML_SEHAT)

    monkeypatch.setattr(isi.requests, "get", _get)

    _html, cara = isi.ambil_html("https://p.id/a")

    assert cara == "requests"
    assert keadaan["n"] == 2


@pytest.mark.unit
def test_teks_dari_html_buang_nav_dan_script() -> None:
    teks = isi.teks_dari_html(HTML_SEHAT)

    assert "Desa Contoh di Kabupaten Uji panen raya kopi." in teks
    assert "Menu Beranda" not in teks
    assert "var x" not in teks


@pytest.mark.unit
def test_teks_dari_html_masukan_kosong_jadi_string_kosong() -> None:
    assert isi.teks_dari_html("") == ""


@pytest.mark.unit
def test_verifikasi_wajib_desa_dan_kabupaten() -> None:
    teks = "desa contoh panen raya di kabupaten uji"

    assert isi.verifikasi(teks, "Contoh", "Uji") is True
    assert isi.verifikasi("desa contoh panen raya", "Contoh", "Uji") is False
    assert isi.verifikasi("kabupaten uji membangun", "Contoh", "Uji") is False


@pytest.mark.unit
def test_rangkum_ekstraktif_pilih_kalimat_bersebut_desa() -> None:
    teks = (
        "Berita umum dulu. Desa Contoh panen kopi. Cuaca cerah. "
        "Warga Desa Contoh untung. Desa Contoh membangun gudang. "
        "Desa Contoh menang lagi."
    )

    hasil = isi.rangkum_ekstraktif(teks, "Contoh")

    assert hasil == (
        "Desa Contoh panen kopi. Warga Desa Contoh untung. "
        "Desa Contoh membangun gudang."
    )


@pytest.mark.unit
def test_rangkum_ekstraktif_fallback_kalimat_awal_dan_potong_600() -> None:
    teks = ("Kalimat panjang tanpa nama desa itu. " * 40).strip()

    hasil = isi.rangkum_ekstraktif(teks, "Contoh")

    assert hasil.startswith("Kalimat panjang")
    assert len(hasil) <= isi.MAKS_RANGKUMAN


@pytest.mark.unit
def test_ambil_html_galat_transien_tercatat_warning_dengan_url(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """`logging.debug` tak pernah tampil di produksi (INFO); galat scraping
    (DNS/TLS/cloudscraper) harus naik ke WARNING agar terlihat di log nyata."""

    def _get(url: str, headers: dict[str, str], timeout: float) -> _ResponsPalsu:
        raise ConnectionError("putus total")

    monkeypatch.setattr(isi.requests, "get", _get)
    scraper = _ScraperPalsu(meledak=True)
    monkeypatch.setattr(isi.cloudscraper, "create_scraper", lambda: scraper)

    with caplog.at_level(logging.WARNING):
        html, cara = isi.ambil_html("https://p.id/gagal-total")

    assert (html, cara) == (None, None)
    assert any(
        record.levelno == logging.WARNING
        and "https://p.id/gagal-total" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.unit
def test_teks_dari_html_parse_gagal_tercatat_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Sama seperti di atas: HTML tak terbaca sebagai artikel harus terlihat."""

    def _bs_meledak(html: str, parser: str) -> Any:
        raise ValueError("html rusak total")

    monkeypatch.setattr(isi, "BeautifulSoup", _bs_meledak)

    with caplog.at_level(logging.WARNING):
        hasil = isi.teks_dari_html("<html>rusak</html>")

    assert hasil == ""
    assert any(record.levelno == logging.WARNING for record in caplog.records)


@pytest.mark.unit
def test_ambil_html_sesi_cloudscraper_ditutup_setelah_sukses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`cloudscraper.create_scraper()` mewarisi `requests.Session` — sesi harus
    ditutup lewat `with`, bukan dibiarkan menunggu garbage collector."""
    monkeypatch.setattr(
        isi.requests,
        "get",
        lambda url, headers, timeout: _ResponsPalsu(403, "Forbidden"),
    )
    scraper = _ScraperPalsu(_ResponsPalsu(200, HTML_SEHAT))
    monkeypatch.setattr(isi.cloudscraper, "create_scraper", lambda: scraper)

    html, cara = isi.ambil_html("https://p.id/a")

    assert cara == "cloudscraper"
    assert html == HTML_SEHAT
    assert scraper.n_tutup == 1


@pytest.mark.unit
def test_ambil_html_sesi_cloudscraper_ditutup_setelah_galat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        isi.requests,
        "get",
        lambda url, headers, timeout: _ResponsPalsu(403, "Forbidden"),
    )
    scraper = _ScraperPalsu(meledak=True)
    monkeypatch.setattr(isi.cloudscraper, "create_scraper", lambda: scraper)

    html, cara = isi.ambil_html("https://p.id/a")

    assert (html, cara) == (None, None)
    assert scraper.n_tutup == 2  # 2 percobaan cloudscraper, sesi baru tiap percobaan


@pytest.mark.unit
def test_teks_dari_html_gagal_parse_kembalikan_kosong_dan_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Parser meledak = artikel tak terbaca, harus tercatat WARNING.

    Produksi berjalan level INFO (`src/main.py`), jadi kalau ini debug
    parser yang rusak total terlihat identik dengan "desa ini memang minim
    berita".
    """

    def _meledak(*args: object, **kwargs: object) -> Any:
        raise RuntimeError("parser meledak")

    monkeypatch.setattr(isi, "BeautifulSoup", _meledak)

    with caplog.at_level(logging.WARNING):
        hasil = isi.teks_dari_html("<html><body>apa pun</body></html>")

    assert hasil == ""
    assert "HTML tak terbaca" in caplog.text
