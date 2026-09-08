"""Uji unit tahap RSS (`src/berita/rss.py`)."""

from datetime import UTC, datetime

import pytest

from src.berita.harvest import rss

XML_TIGA_ITEM = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title> Panen raya Desa Contoh </title>
  <link>https://news.google.com/rss/articles/AAA</link>
  <pubDate>Mon, 01 Sep 2026 03:00:00 GMT</pubDate>
  <source url="https://contoh.id">Contoh News</source>
</item>
<item>
  <title>BUMDes Contoh untung besar</title>
  <link>https://news.google.com/rss/articles/BBB</link>
  <pubDate>bukan tanggal</pubDate>
</item>
<item>
  <title>Item ketiga</title>
  <link>https://news.google.com/rss/articles/CCC</link>
  <pubDate>Tue, 02 Sep 2026 03:00:00 GMT</pubDate>
</item>
</channel></rss>"""


class _ResponsPalsu:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


def _pasang_rss(monkeypatch: pytest.MonkeyPatch, xml: str) -> None:
    def _get(url: str, headers: dict[str, str], timeout: float) -> _ResponsPalsu:
        return _ResponsPalsu(xml.encode())

    monkeypatch.setattr(rss.requests, "get", _get)


@pytest.mark.unit
def test_kueri_desa_bentuk_prd() -> None:
    assert rss.kueri_desa("Contoh", "Uji Raya") == "desa Contoh Uji Raya"


@pytest.mark.unit
def test_cari_rss_parse_item_lengkap(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    _pasang_rss(monkeypatch, XML_TIGA_ITEM)

    # Act
    items = rss.cari_rss("desa Contoh Uji")

    # Assert
    assert len(items) == 3
    assert items[0].judul == "Panen raya Desa Contoh"
    assert items[0].link == "https://news.google.com/rss/articles/AAA"
    assert items[0].sumber == "Contoh News"
    assert items[0].terbit_pada is not None
    assert items[0].terbit_pada.year == 2026
    assert items[2].sumber == ""


@pytest.mark.unit
def test_cari_rss_pubdate_rusak_jadi_none_bukan_galat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pasang_rss(monkeypatch, XML_TIGA_ITEM)

    items = rss.cari_rss("desa Contoh Uji")

    assert items[1].terbit_pada is None


@pytest.mark.unit
def test_cari_rss_hormati_maks(monkeypatch: pytest.MonkeyPatch) -> None:
    _pasang_rss(monkeypatch, XML_TIGA_ITEM)

    items = rss.cari_rss("desa Contoh Uji", maks=1)

    assert len(items) == 1


@pytest.mark.unit
def test_cari_rss_tanpa_item_daftar_kosong(monkeypatch: pytest.MonkeyPatch) -> None:
    _pasang_rss(
        monkeypatch,
        '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>',
    )

    assert rss.cari_rss("desa Tak Ada Berita") == []


@pytest.mark.unit
def test_parse_terbit_tanpa_zona_dianggap_utc() -> None:
    """RFC 822 boleh tak menyebut zona; stdlib lalu balikin naive — harus UTC."""
    hasil = rss._parse_terbit("Mon, 01 Sep 2026 03:00:00")

    assert hasil == datetime(2026, 9, 1, 3, 0, 0, tzinfo=UTC)


@pytest.mark.unit
def test_parse_terbit_dengan_gmt_tak_berubah() -> None:
    hasil = rss._parse_terbit("Mon, 01 Sep 2026 03:00:00 GMT")

    assert hasil == datetime(2026, 9, 1, 3, 0, 0, tzinfo=UTC)


@pytest.mark.unit
def test_parse_terbit_tak_terparse_kembalikan_none() -> None:
    assert rss._parse_terbit("bukan tanggal") is None
