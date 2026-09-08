"""Uji unit orkestrator panen (`src/berita/panen.py`).

Seluruh tahap di-monkeypatch pada namespace modul `panen` (nama diimpor
langsung) — uji fokus pada alur keputusan, penghitungan, dan dedup.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from src.berita.harvest import orchestrator as panen
from src.berita.harvest.filter import HasilSaring
from src.berita.harvest.rss import ItemRSS
from src.berita.harvest.store import BarisBerita
from src.config import Pengaturan

_PENGATURAN_GEMINI = Pengaturan(
    supabase_url="https://uji.supabase.co",
    supabase_service_role_key="kunci-uji",
    gemini_api_key="kunci-gemini",
)
_PENGATURAN_TANPA_GEMINI = Pengaturan(
    supabase_url="https://uji.supabase.co",
    supabase_service_role_key="kunci-uji",
    gemini_api_key="",
)

_TERBIT = datetime(2026, 9, 1, tzinfo=UTC)
TEKS_UNTUNG = "Desa Contoh di Kabupaten Uji untung besar dari kopi. " * 10
TEKS_POLITIK = "Pilkades Desa Contoh Kabupaten Uji politik memanas hebat. " * 10

_ITEMS = [
    ItemRSS(
        judul="Desa Contoh untung di Uji", link="gA", terbit_pada=_TERBIT, sumber="S1"
    ),
    ItemRSS(judul="Pilkades Contoh", link="gB", terbit_pada=_TERBIT, sumber="S2"),
    ItemRSS(
        judul="Galeri Desa Contoh di Uji", link="gC", terbit_pada=None, sumber="S3"
    ),
    ItemRSS(
        judul="Berita tanpa nama kabupaten", link="gD", terbit_pada=_TERBIT, sumber="S4"
    ),
    ItemRSS(
        judul="Desa Contoh untung lagi Uji",
        link="gA2",
        terbit_pada=_TERBIT,
        sumber="S1",
    ),
]

_URL_PER_LINK = {
    "gA": "https://p.id/a",
    "gB": "https://p.id/b",
    "gC": "https://p.id/c",
    "gD": None,
    "gA2": "https://p.id/a",  # URL sama dengan gA — uji dedup
}
_TEKS_PER_URL = {
    "https://p.id/a": TEKS_UNTUNG,
    "https://p.id/b": TEKS_POLITIK,
    "https://p.id/c": "foto",  # galeri: terlalu pendek, jalur judul-rss
}


def _saring_palsu(teks: str, desa: str, kab: str, kunci: str) -> HasilSaring:
    return HasilSaring(
        relevan="untung" in teks,
        kategori=["Potensi produksi"] if "untung" in teks else [],
        rangkuman="Rangkuman Gemini.",
        desa_benar=True,
        alasan="uji",
    )


@pytest.fixture
def pipeline_palsu(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub seluruh tahap panen; kembalikan perekam panggilan simpan."""
    rekam: dict[str, Any] = {"disimpan": None, "n_select": 0}

    monkeypatch.setattr(panen.time, "sleep", lambda detik: None)
    monkeypatch.setattr(panen, "cari_rss", lambda kueri: list(_ITEMS))
    monkeypatch.setattr(panen, "dekode_link", lambda link: _URL_PER_LINK[link])
    monkeypatch.setattr(panen, "ambil_html", lambda url: (f"HTML:{url}", "requests"))
    monkeypatch.setattr(
        panen, "teks_dari_html", lambda html: _TEKS_PER_URL[html.removeprefix("HTML:")]
    )
    monkeypatch.setattr(panen, "saring_gemini", _saring_palsu)

    def _url_tersimpan(
        klien: httpx.Client, pengaturan: Pengaturan, iddesa: str
    ) -> dict[str, dict[str, Any]]:
        rekam["n_select"] += 1
        # Sama persis dengan kandidat "/c" (judul-rss, rangkuman None) —
        # peringkat sama sehingga penjaga downgrade FIX 1 tidak mengubah
        # apa pun di sini; itu diuji terpisah di bawah.
        return {
            "https://p.id/c": {
                "rangkuman": None,
                "kategori": [],
                "perangkum": "judul-rss",
            }
        }

    def _simpan(
        klien: httpx.Client, pengaturan: Pengaturan, baris: list[BarisBerita]
    ) -> None:
        rekam["disimpan"] = baris

    monkeypatch.setattr(panen, "url_tersimpan", _url_tersimpan)
    monkeypatch.setattr(panen, "simpan_berita", _simpan)
    return rekam


@pytest.mark.unit
def test_panen_campuran_saring_fallback_dedup_dan_hitung(
    pipeline_palsu: dict[str, Any],
) -> None:
    """5 item: 1 relevan + 1 duplikat URL-nya, 1 tak relevan, 1 galeri
    (judul-rss), 1 dekode gagal berjudul tanpa kabupaten (dibuang)."""
    klien = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))

    hasil = panen.panen_desa(klien, _PENGATURAN_GEMINI, "1801040001", "Contoh", "Uji")

    assert hasil.n_baru == 1  # https://p.id/a (gemini)
    assert hasil.n_duplikat == 1  # https://p.id/c sudah tersimpan
    assert hasil.n_dibuang == 2  # politik (tak relevan) + judul tanpa kab
    assert hasil.n_gagal == 0  # FIX 1: tak ada artikel yang melempar di sini
    disimpan = pipeline_palsu["disimpan"]
    assert {b.url for b in disimpan} == {"https://p.id/a", "https://p.id/c"}
    per_url = {b.url: b for b in disimpan}
    assert per_url["https://p.id/a"].perangkum == "gemini"
    assert per_url["https://p.id/a"].rangkuman == "Rangkuman Gemini."
    assert per_url["https://p.id/c"].perangkum == "judul-rss"
    assert per_url["https://p.id/c"].rangkuman is None


@pytest.mark.unit
def test_panen_tanpa_kunci_gemini_jalur_ekstraktif(
    pipeline_palsu: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _saring_dilarang(teks: str, desa: str, kab: str, kunci: str) -> HasilSaring:
        raise AssertionError("saring_gemini tidak boleh dipanggil tanpa kunci")

    monkeypatch.setattr(panen, "saring_gemini", _saring_dilarang)
    monkeypatch.setattr(panen, "cari_rss", lambda kueri: [_ITEMS[0]])
    klien = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))

    hasil = panen.panen_desa(
        klien, _PENGATURAN_TANPA_GEMINI, "1801040001", "Contoh", "Uji"
    )

    assert hasil.n_baru == 1
    baris = pipeline_palsu["disimpan"][0]
    assert baris.perangkum == "ekstraktif"
    assert "Desa Contoh" in baris.rangkuman
    assert baris.kategori == []


@pytest.mark.unit
def test_panen_gemini_gagal_total_turun_ke_ekstraktif(
    pipeline_palsu: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _saring_gagal(teks: str, desa: str, kab: str, kunci: str) -> HasilSaring:
        raise RuntimeError("kuota habis")

    monkeypatch.setattr(panen, "saring_gemini", _saring_gagal)
    monkeypatch.setattr(panen, "cari_rss", lambda kueri: [_ITEMS[0]])
    klien = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))

    hasil = panen.panen_desa(klien, _PENGATURAN_GEMINI, "1801040001", "Contoh", "Uji")

    assert hasil.n_baru == 1
    assert pipeline_palsu["disimpan"][0].perangkum == "ekstraktif"


@pytest.mark.unit
def test_panen_rss_kosong_tanpa_panggilan_postgrest(
    pipeline_palsu: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(panen, "cari_rss", lambda kueri: [])
    klien = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))

    hasil = panen.panen_desa(klien, _PENGATURAN_GEMINI, "1801040001", "Contoh", "Uji")

    assert hasil == panen.HasilPanen(
        iddesa="1801040001", n_baru=0, n_duplikat=0, n_dibuang=0, n_gagal=0
    )
    assert pipeline_palsu["n_select"] == 0
    assert pipeline_palsu["disimpan"] is None


@pytest.mark.unit
def test_panen_satu_artikel_gagal_tidak_menggagalkan_desa(
    pipeline_palsu: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """FIX 1: artikel yang MELEMPAR masuk `n_gagal`, BUKAN `n_dibuang` — beda
    dengan artikel yang ditolak saring/verifikasi (lihat uji di atas)."""

    def _dekode_meledak(link: str) -> str | None:
        raise RuntimeError("jaringan putus")

    monkeypatch.setattr(panen, "dekode_link", _dekode_meledak)
    monkeypatch.setattr(panen, "cari_rss", lambda kueri: [_ITEMS[0]])
    klien = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))

    hasil = panen.panen_desa(klien, _PENGATURAN_GEMINI, "1801040001", "Contoh", "Uji")

    assert hasil.n_gagal == 1
    assert hasil.n_dibuang == 0
    assert hasil.n_baru == 0


# --- FIX 1: re-panen tidak boleh menurunkan mutu ringkasan tersimpan -------
#
# Skenario di bawah masing-masing memakai satu item RSS berdiri sendiri
# (bukan `pipeline_palsu`/`_ITEMS`) supaya baris "lama" vs "baru" per URL
# bisa diatur persis tanpa mengganggu uji dedup/hitung yang sudah ada.

_ITEM_TUNGGAL = ItemRSS(
    judul="Warta Desa Contoh Kabupaten Uji",
    link="gX",
    terbit_pada=_TERBIT,
    sumber="S1",
)


def _pasang_dasar(
    monkeypatch: pytest.MonkeyPatch, tersimpan: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Pasang cari_rss/dekode_link/url_tersimpan/simpan_berita untuk satu item;
    kembalikan perekam `disimpan` dan `n_baru`/`n_duplikat` hasilnya."""
    rekam: dict[str, Any] = {"disimpan": None}
    monkeypatch.setattr(panen.time, "sleep", lambda detik: None)
    monkeypatch.setattr(panen, "cari_rss", lambda kueri: [_ITEM_TUNGGAL])
    monkeypatch.setattr(panen, "dekode_link", lambda link: "https://p.id/x")

    def _url_tersimpan(
        klien: httpx.Client, pengaturan: Pengaturan, iddesa: str
    ) -> dict[str, dict[str, Any]]:
        return tersimpan

    def _simpan(
        klien: httpx.Client, pengaturan: Pengaturan, baris: list[BarisBerita]
    ) -> None:
        rekam["disimpan"] = baris

    monkeypatch.setattr(panen, "url_tersimpan", _url_tersimpan)
    monkeypatch.setattr(panen, "simpan_berita", _simpan)
    return rekam


@pytest.mark.unit
def test_downgrade_dijaga_gemini_lama_menang_atas_judul_rss_baru(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scraping/Gemini gagal total kali ini (jatuh ke judul-rss) — ringkasan
    gemini yang sudah tersimpan TIDAK BOLEH tertimpa kosong."""
    rekam = _pasang_dasar(
        monkeypatch,
        {
            "https://p.id/x": {
                "rangkuman": "Rangkuman gemini lama.",
                "kategori": ["Wisata"],
                "perangkum": "gemini",
            }
        },
    )
    # html gagal total -> _olah_item jatuh ke _baris_judul_rss (jalur judul-rss).
    monkeypatch.setattr(panen, "ambil_html", lambda url: (None, None))

    def _saring_dilarang(teks: str, desa: str, kab: str, kunci: str) -> HasilSaring:
        raise AssertionError("saring_gemini tidak boleh dipanggil — html gagal total")

    monkeypatch.setattr(panen, "saring_gemini", _saring_dilarang)
    klien = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))

    sebelum = datetime.now(UTC)
    hasil = panen.panen_desa(klien, _PENGATURAN_GEMINI, "1801040001", "Contoh", "Uji")
    sesudah = datetime.now(UTC)

    baris = rekam["disimpan"][0]
    assert baris.perangkum == "gemini"
    assert baris.rangkuman == "Rangkuman gemini lama."
    assert baris.kategori == ["Wisata"]
    assert sebelum <= baris.dipanen_pada <= sesudah  # dipanen_pada tetap maju
    assert hasil.n_baru == 0
    assert hasil.n_duplikat == 1


@pytest.mark.unit
def test_downgrade_dijaga_gemini_baru_menang_atas_judul_rss_lama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Arah sebaliknya: ringkasan gemini segar HARUS menimpa judul-rss lama."""
    rekam = _pasang_dasar(
        monkeypatch,
        {
            "https://p.id/x": {
                "rangkuman": None,
                "kategori": [],
                "perangkum": "judul-rss",
            }
        },
    )
    monkeypatch.setattr(panen, "ambil_html", lambda url: ("HTML", "requests"))
    monkeypatch.setattr(
        panen,
        "teks_dari_html",
        lambda html: "Desa Contoh Kabupaten Uji berkembang pesat. " * 10,
    )
    monkeypatch.setattr(
        panen,
        "saring_gemini",
        lambda teks, desa, kab, kunci: HasilSaring(
            relevan=True,
            kategori=["Ekonomi"],
            rangkuman="Ringkasan segar.",
            desa_benar=True,
            alasan="uji",
        ),
    )
    klien = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))

    hasil = panen.panen_desa(klien, _PENGATURAN_GEMINI, "1801040001", "Contoh", "Uji")

    baris = rekam["disimpan"][0]
    assert baris.perangkum == "gemini"
    assert baris.rangkuman == "Ringkasan segar."
    assert baris.kategori == ["Ekonomi"]
    assert hasil.n_baru == 0
    assert hasil.n_duplikat == 1


@pytest.mark.unit
def test_downgrade_peringkat_sama_baris_baru_menang(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Peringkat sama (ekstraktif vs ekstraktif) — tanpa kasus khusus, baris
    baru yang menang, seperti sebelum FIX 1 ada."""
    rekam = _pasang_dasar(
        monkeypatch,
        {
            "https://p.id/x": {
                "rangkuman": "Ringkasan ekstraktif lama.",
                "kategori": [],
                "perangkum": "ekstraktif",
            }
        },
    )
    monkeypatch.setattr(panen, "ambil_html", lambda url: ("HTML", "requests"))
    monkeypatch.setattr(
        panen,
        "teks_dari_html",
        lambda html: "Desa Contoh Kabupaten Uji berkembang pesat. " * 10,
    )
    monkeypatch.setattr(
        panen, "rangkum_ekstraktif", lambda teks, desa: "Ringkasan ekstraktif baru."
    )
    klien = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))

    hasil = panen.panen_desa(
        klien, _PENGATURAN_TANPA_GEMINI, "1801040001", "Contoh", "Uji"
    )

    baris = rekam["disimpan"][0]
    assert baris.perangkum == "ekstraktif"
    assert baris.rangkuman == "Ringkasan ekstraktif baru."
    assert hasil.n_baru == 0
    assert hasil.n_duplikat == 1


@pytest.mark.unit
def test_downgrade_url_baru_tak_tersentuh(monkeypatch: pytest.MonkeyPatch) -> None:
    """URL yang belum pernah tersimpan tidak boleh disentuh penjaga downgrade,
    dan tetap terhitung n_baru (bukan n_duplikat)."""
    rekam = _pasang_dasar(monkeypatch, {})
    monkeypatch.setattr(panen, "ambil_html", lambda url: (None, None))

    klien = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))

    hasil = panen.panen_desa(klien, _PENGATURAN_GEMINI, "1801040001", "Contoh", "Uji")

    baris = rekam["disimpan"][0]
    assert baris.perangkum == "judul-rss"
    assert baris.rangkuman is None
    assert hasil.n_baru == 1
    assert hasil.n_duplikat == 0


@pytest.mark.unit
def test_jalur_ekstraktif_teks_tanpa_nama_desa_dibuang(
    pipeline_palsu: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Penjaga sebut-desa jalur EKSTRAKTIF punya cabang sendiri.

    Uji ekstraktif yang ada memakai teks yang sudah memuat nama desa dan
    kabupaten, jadi cabang penolakannya tidak pernah dijalankan — hapus
    penjaganya dan suite tetap hijau sambil meloloskan artikel di luar topik
    lewat jalur ini.
    """
    monkeypatch.setattr(panen, "cari_rss", lambda kueri: [_ITEMS[0]])
    monkeypatch.setattr(
        panen,
        "teks_dari_html",
        lambda html: "Berita nasional tanpa sebut apa pun. " * 20,
    )
    klien = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))

    hasil = panen.panen_desa(
        klien, _PENGATURAN_TANPA_GEMINI, "1801040001", "Contoh", "Uji"
    )

    assert hasil.n_baru == 0
    assert hasil.n_dibuang == 1
    assert hasil.n_gagal == 0
    # Tanpa kandidat, `panen_desa` pulang sebelum menyentuh jaringan sama
    # sekali — `simpan_berita` tidak pernah dipanggil, jadi stub-nya tetap
    # None (bukan daftar kosong).
    assert not pipeline_palsu["disimpan"]
