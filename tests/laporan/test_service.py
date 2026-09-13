"""Uji unit perakitan isi Laporan Desa (`src/laporan/service.py`).

Kartu sintetis di fixture `dir_data_lengkap` (`tests/conftest.py`,
`_kartu_per_kab`) cuma memuat tiga seksi (`identitas`, `peta_peran`,
`mutu_data`) dan `identitas` di sana tidak punya `lon`/`lat`/`luas_km2`/
`kode_dagri`. Berkas ini merakit sendiri satu kartu LENGKAP (kesembilan
seksi terisi) untuk menguji jalur normal, dan memakai bentuk sejarang
fixture itu untuk menguji jalur kosong/hilang tanpa melempar.
"""

from typing import Any

import pytest

from src.laporan.constants import JUDUL_SEKSI, KOORDINAT_PLACEHOLDER, NILAI_KOSONG
from src.laporan.schemas import RingkasanLaporan, SeksiRingkas, SeksiTabel
from src.laporan.service import (
    _koordinat,
    _seksi_ai_insight,
    _seksi_desa_kembar,
    _seksi_potensi,
    _teks,
    rakit_ringkasan,
)


def _kartu_lengkap(**override: Any) -> dict[str, Any]:
    """Kartu sintetis dengan kesembilan seksi terisi — bentuk mengikuti
    contoh nyata `data-salinan/kartu-ekonomi/kartu/1801.json`."""
    dasar: dict[str, Any] = {
        "identitas": {
            "iddesa": "1801040001",
            "kode_dagri": "18.04.04.2002",
            "nama": "KUBU PERAHU",
            "kecamatan": "BALIK BUKIT",
            "kabupaten": "LAMPUNG BARAT",
            "provinsi": "18",
            "tipe": "desa",
            "lon": 104.061928,
            "lat": -5.071913,
            "luas_km2": 42.94,
        },
        "peta_peran": {
            "peringkat_sp_kab": 20,
            "peringkat_sk_kab": 12,
        },
        "rekomendasi_aksi": "Siap dipertemukan dengan mitra offtaker.",
        "potensi": {
            "dominan": "Simpul Logistik",
            "sumber_dominan": "heuristik-belum-teruji",
            "detail_dominan": None,
            "sub_skor": {
                "tp": {"persentil": 0.0, "label": "Tanaman Pangan"},
                "ikan": {"persentil": 94.44, "label": "Perikanan Budidaya"},
            },
        },
        "kesiapan": {
            "kelembagaan": {"lumbung": 0, "penggilingan": 0},
            "amenitas_poi": {"poi_layanan_dasar": 2, "poi_niaga": 3},
        },
        "logistik": {
            "menit_ke_pusat_kota": 4.0,
            "pusat_kota": "Liwa",
            "menit_ke_bandara": 22.2,
            "bandara": "Bandar Udara Muhammad Taufiq Kiemas",
            "menit_ke_pelabuhan": 125.7,
            "pelabuhan": "Pelabuhan Kota Agung",
        },
        "jalur_ekonomi": None,
        "desa_kembar": [
            {
                "iddesa": "1801055009",
                "nmdesa": "SUMBER REJO",
                "nmkec": "BATU KETULIS",
                "kemiripan": 35.2,
                "zona": "Zona Bantuan",
            },
        ],
        "fakta_program": {
            "jadesta": None,
            "desa_wisata_sisparnas": None,
            "n_daya_tarik_wisata": 3,
            "kampung_budidaya": None,
            "kampung_nelayan": None,
            "cold_storage_eksisting": None,
            "cold_storage_terlayani": None,
            "belum_tersentuh": True,
            "catatan": "fakta registri — tidak pernah ikut menyusun skor",
        },
        "mutu_data": {
            "punya_geometri": True,
            "punya_st2023": True,
            "punya_idm": True,
            "kelengkapan_bukti_sk": 1.0,
        },
    }
    dasar.update(override)
    return dasar


def _pp_lengkap(**override: Any) -> dict[str, Any]:
    """Satu baris penuh `peta_peran.json` — BEDA bentuk dari
    `kartu["peta_peran"]` (lihat GOTCHA 3 rencana fase 8)."""
    dasar: dict[str, Any] = {
        "iddesa": "1801040001",
        "zona": "Zona Mitra",
        "nomor_zona": 2.0,
        "keyakinan": "normal",
        "alasan_belum_terpetakan": "",
        "SP": 97.78,
        "SK": 45.83,
        "desil_sp": 9.0,
        "desil_sk": 10.0,
        "ambang_sp": 90.18,
        "ambang_sk": 31.92,
        "jarak_ke_ambang": 7.6,
        "kelengkapan_sk": 1.0,
        "komponen_sk_hilang": "",
        "idm": 0.89,
        "idm_status": "MANDIRI",
        "infra_per_1000_ruta": 0.0,
        "sentralitas_menit": 46.8,
    }
    dasar.update(override)
    return dasar


def _manifest_lengkap() -> dict[str, Any]:
    return {"hash": "abcdef0123456789fefefefe", "tanggal": "2026-09-01"}


def _judul_unik_berurutan(laporan: RingkasanLaporan) -> list[str]:
    """Judul seksi tanpa duplikat BERURUTAN — "Potensi Dominan" bisa
    muncul dua entri berurutan (ringkas lalu tabel sub-skor) berbagi
    judul yang sama; ini menganggapnya SATU seksi konseptual."""
    unik: list[str] = []
    for seksi in laporan.seksi:
        if not unik or unik[-1] != seksi.judul:
            unik.append(seksi.judul)
    return unik


def _label_ke_nilai(laporan: RingkasanLaporan) -> dict[str, str]:
    """Kumpulkan `label -> nilai` dari semua `SeksiRingkas` di laporan.
    Melempar `AssertionError` kalau ada label ganda antar seksi ringkas —
    tidak terjadi selama label unik per seksi seperti dirancang."""
    hasil: dict[str, str] = {}
    for seksi in laporan.seksi:
        if isinstance(seksi, SeksiRingkas):
            for baris in seksi.baris:
                hasil[baris.label] = baris.nilai
    return hasil


@pytest.mark.unit
def test_sembilan_seksi_terbentuk() -> None:
    laporan = rakit_ringkasan(_kartu_lengkap(), _pp_lengkap(), _manifest_lengkap())

    assert tuple(_judul_unik_berurutan(laporan)) == JUDUL_SEKSI


@pytest.mark.unit
def test_kolom_mutu_selalu_ikut() -> None:
    kartu = _kartu_lengkap()
    kartu["potensi"]["sumber_dominan"] = ""
    pp = _pp_lengkap(keyakinan="", alasan_belum_terpetakan="")

    laporan = rakit_ringkasan(kartu, pp, _manifest_lengkap())

    label_ke_nilai = _label_ke_nilai(laporan)
    assert label_ke_nilai["Keyakinan"] == NILAI_KOSONG
    assert label_ke_nilai["Alasan Belum Terpetakan"] == NILAI_KOSONG
    assert label_ke_nilai["Sumber Model"] == NILAI_KOSONG


@pytest.mark.unit
def test_koordinat_placeholder_disaring() -> None:
    lat_placeholder, lon_placeholder = KOORDINAT_PLACEHOLDER
    kartu_placeholder = _kartu_lengkap()
    kartu_placeholder["identitas"]["lat"] = lat_placeholder
    kartu_placeholder["identitas"]["lon"] = lon_placeholder

    laporan_placeholder = rakit_ringkasan(
        kartu_placeholder, _pp_lengkap(), _manifest_lengkap()
    )
    assert _label_ke_nilai(laporan_placeholder)["Koordinat"] == "tidak tersedia"

    laporan_normal = rakit_ringkasan(
        _kartu_lengkap(), _pp_lengkap(), _manifest_lengkap()
    )
    nilai_koordinat = _label_ke_nilai(laporan_normal)["Koordinat"]
    assert nilai_koordinat != "tidak tersedia"
    assert "104.061928" in nilai_koordinat
    assert "-5.071913" in nilai_koordinat


@pytest.mark.unit
def test_wisata_bukan_skor_potensi() -> None:
    laporan = rakit_ringkasan(_kartu_lengkap(), _pp_lengkap(), _manifest_lengkap())

    for seksi in laporan.seksi:
        if isinstance(seksi, SeksiTabel):
            assert not any("wisata" in sel.lower() for baris in seksi.baris for sel in baris)
        elif isinstance(seksi, SeksiRingkas):
            for baris in seksi.baris:
                if "skor potensi" in baris.label.lower():
                    assert "wisata" not in baris.nilai.lower()


@pytest.mark.unit
def test_seksi_kosong_tidak_melempar() -> None:
    """Kartu sejarang fixture `dir_data_lengkap` — hanya `identitas` (tanpa
    lon/lat), `peta_peran`, `mutu_data`; `desa_kembar` hilang; `pp` minim."""
    kartu_sejarang = {
        "identitas": {
            "iddesa": "1801040001",
            "nama": "KUBU PERAHU",
            "kecamatan": "BALIK BUKIT",
            "kabupaten": "LAMPUNG BARAT",
            "provinsi": "18",
            "tipe": "desa",
        },
        "peta_peran": {},
        "mutu_data": {
            "punya_geometri": True,
            "punya_st2023": True,
            "punya_idm": True,
            "kelengkapan_bukti_sk": 1.0,
        },
        "jalur_ekonomi": None,
    }
    pp_minim: dict[str, Any] = {"iddesa": "1801040001"}

    laporan = rakit_ringkasan(kartu_sejarang, pp_minim, _manifest_lengkap())

    assert tuple(_judul_unik_berurutan(laporan)) == JUDUL_SEKSI
    label_ke_nilai = _label_ke_nilai(laporan)
    assert label_ke_nilai["Koordinat"] == NILAI_KOSONG
    assert label_ke_nilai["Kode Dagri"] == NILAI_KOSONG
    assert label_ke_nilai["Desa Kembar"] == "tidak ada"


@pytest.mark.unit
def test_catatan_kaki_tanpa_manifest() -> None:
    laporan = rakit_ringkasan(_kartu_lengkap(), _pp_lengkap(), None)

    assert "data build tidak diketahui" in laporan.catatan_kaki


@pytest.mark.unit
def test_catatan_kaki_manifest_tanpa_kunci_tidak_melempar() -> None:
    """`muat_manifest` (`src/datastore.py`) sengaja tidak memvalidasi isi
    manifest — tanggung jawab pemanggil. Manifest ada tapi kosong (build
    parsial/hand-edit/skew versi penulis) tidak boleh melempar `KeyError`
    yang jatuh ke 500 GALAT_SERVER; ini cuma catatan kaki, boleh degradasi
    seperti jalur `manifest is None` tiga baris di atasnya."""
    laporan = rakit_ringkasan(_kartu_lengkap(), _pp_lengkap(), {})

    assert isinstance(laporan.catatan_kaki, str)
    assert laporan.catatan_kaki != ""


@pytest.mark.unit
def test_catatan_kaki_manifest_tanpa_tanggal_tidak_melempar() -> None:
    laporan = rakit_ringkasan(_kartu_lengkap(), _pp_lengkap(), {"hash": "abc"})

    assert isinstance(laporan.catatan_kaki, str)
    assert laporan.catatan_kaki != ""


@pytest.mark.unit
def test_teks_bool_dicek_sebelum_int() -> None:
    assert _teks(True) == "ya"
    assert _teks(False) == "tidak"


@pytest.mark.unit
def test_teks_none_dan_kosong_jadi_nilai_kosong() -> None:
    assert _teks(None) == NILAI_KOSONG
    assert _teks("") == NILAI_KOSONG


@pytest.mark.unit
def test_teks_angka_apa_adanya_tanpa_format() -> None:
    assert _teks(1234567.89) == "1234567.89"
    assert _teks(42) == "42"


@pytest.mark.unit
def test_teks_list_kosong_dan_berisi() -> None:
    assert _teks([]) == NILAI_KOSONG
    assert _teks(["a", "b"]) == "a, b"


@pytest.mark.unit
def test_koordinat_salah_satu_hilang() -> None:
    assert _koordinat({"lat": -5.0}) == NILAI_KOSONG
    assert _koordinat({"lon": 104.0}) == NILAI_KOSONG
    assert _koordinat({}) == NILAI_KOSONG


@pytest.mark.unit
def test_koordinat_placeholder_beda_presisi_desimal_tetap_disaring() -> None:
    """Placeholder Kemenparekraf sudah tiga kali menyesatkan proyek ini lewat
    kode wilayah klaim sumber eksternal (`../CLAUDE.md`); nilai float yang
    diserialisasi ulang lewat sumber lain bisa berbeda di presisi desimal
    ke-7 tanpa jadi koordinat yang beda secara nyata. Filter kesetaraan
    persis (`==`) gagal menangkap kasus ini — penyaringan harus toleran
    lewat `math.isclose`. Ini pengerasan (hardening): data saat ini tidak
    punya kecocokan sama sekali, bukan bug yang sudah terjadi."""
    lat_placeholder, lon_placeholder = KOORDINAT_PLACEHOLDER

    hasil = _koordinat({"lat": lat_placeholder + 1e-7, "lon": lon_placeholder - 1e-7})

    assert hasil == "tidak tersedia"


@pytest.mark.unit
def test_koordinat_beda_nyata_tidak_disaring() -> None:
    """Koordinat yang benar-benar berbeda (bukan sekadar noise presisi)
    tetap dicetak apa adanya, tidak ikut tersaring toleransi."""
    lat_placeholder, lon_placeholder = KOORDINAT_PLACEHOLDER

    hasil = _koordinat({"lat": lat_placeholder + 1.0, "lon": lon_placeholder})

    assert hasil != "tidak tersedia"


@pytest.mark.unit
def test_seksi_potensi_sub_skor_kosong_kembalikan_tabel_none() -> None:
    ringkas, tabel = _seksi_potensi({"potensi": {"dominan": "X", "sub_skor": {}}})

    assert isinstance(ringkas, SeksiRingkas)
    assert tabel is None


@pytest.mark.unit
def test_seksi_desa_kembar_kosong_jadi_ringkas_satu_baris() -> None:
    seksi = _seksi_desa_kembar({"desa_kembar": []})

    assert isinstance(seksi, SeksiRingkas)
    assert len(seksi.baris) == 1
    assert seksi.baris[0].label == "Desa Kembar"
    assert seksi.baris[0].nilai == "tidak ada"


@pytest.mark.unit
def test_seksi_desa_kembar_berisi_jadi_tabel() -> None:
    seksi = _seksi_desa_kembar(
        {
            "desa_kembar": [
                {
                    "iddesa": "1801055009",
                    "nmdesa": "SUMBER REJO",
                    "nmkec": "BATU KETULIS",
                    "kemiripan": 35.2,
                    "zona": "Zona Bantuan",
                }
            ]
        }
    )

    assert isinstance(seksi, SeksiTabel)
    assert seksi.kepala == ["Kode desa", "Nama", "Kecamatan", "Kemiripan", "Zona"]
    assert seksi.baris == [
        ["1801055009", "SUMBER REJO", "BATU KETULIS", "35.2", "Zona Bantuan"]
    ]


@pytest.mark.unit
def test_kode_kosong_sub_skor_ikut_terbawa() -> None:
    """Kode kosong (`TIDAK-BERLAKU`, `TIDAK-DINILAI`) wajib ikut tercetak.

    PRD bagian 8 menyebutnya kolom mutu yang tidak pernah boleh disaring.
    Data nyata memuatnya: `sub_skor.tangkap` pada kabupaten 1801 bernilai
    `{"persentil": null, "kosong": "TIDAK-BERLAKU", ...}`. Tanpa kolom
    Keterangan, baris itu cuma tampil "-" dan pembaca tidak bisa
    membedakan data hilang dari data yang memang tidak berlaku.
    """
    kartu = _kartu_lengkap(
        potensi={
            "dominan": "Simpul Logistik",
            "sumber_dominan": "citra",
            "detail_dominan": None,
            "sub_skor": {
                "simpul": {"persentil": 97.78, "label": "Simpul Logistik"},
                "tangkap": {
                    "persentil": None,
                    "kosong": "TIDAK-BERLAKU",
                    "label": "Perikanan Tangkap",
                },
            },
        }
    )

    laporan = rakit_ringkasan(kartu, _pp_lengkap(), _manifest_lengkap())

    tabel = next(
        s
        for s in laporan.seksi
        if isinstance(s, SeksiTabel) and s.judul == "Kartu Ekonomi Desa"
    )
    assert tabel.kepala == ["Subsektor", "Skor", "Keterangan"]
    assert ["Perikanan Tangkap", NILAI_KOSONG, "TIDAK-BERLAKU"] in tabel.baris
    assert ["Simpul Logistik", "97.78", NILAI_KOSONG] in tabel.baris


@pytest.mark.unit
def test_nama_provinsi_menggantikan_kode_bila_disuplai() -> None:
    """`identitas.provinsi` berisi KODE provinsi, bukan namanya.

    Kode telanjang ("33") tidak terbaca di dokumen dinas. Pemanggil boleh
    menyuplai nama dari `wilayah.json`; tanpa suplai itu kode aslinya
    tetap dicetak apa adanya, tidak pernah dibuang.
    """
    kartu = _kartu_lengkap()
    kartu["identitas"] = {**kartu["identitas"], "provinsi": "33"}

    tanpa = rakit_ringkasan(kartu, _pp_lengkap(), _manifest_lengkap())
    dengan = rakit_ringkasan(kartu, _pp_lengkap(), _manifest_lengkap(), "Jawa Tengah")

    assert ", 33 ·" in tanpa.subjudul
    assert ", Jawa Tengah ·" in dengan.subjudul
    assert "33" not in dengan.subjudul.split("·")[0]


# ── AI Insight Desa ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_seksi_ai_insight_none_kembalikan_status_belum() -> None:
    """Jika ai_insight=None, seksi harus memuat teks 'AI Insight belum di generate'."""
    seksi = _seksi_ai_insight(None)

    assert isinstance(seksi, SeksiRingkas)
    assert seksi.judul == "AI Insight Desa"
    assert any("belum di generate" in b.nilai for b in seksi.baris)


@pytest.mark.unit
def test_seksi_ai_insight_dict_kosong_kembalikan_status_belum() -> None:
    """Dict kosong {} dianggap belum di-generate."""
    seksi = _seksi_ai_insight({})

    assert isinstance(seksi, SeksiRingkas)
    assert any("belum di generate" in b.nilai for b in seksi.baris)


@pytest.mark.unit
def test_seksi_ai_insight_terisi_kondisi_ekonomi() -> None:
    """Jika kondisi_ekonomi terisi, label 'Kondisi Ekonomi' ada di baris."""
    seksi = _seksi_ai_insight(
        {"kondisi_ekonomi": "Desa ini memiliki potensi besar.", "rekomendasi_aktor": []}
    )

    assert isinstance(seksi, SeksiRingkas)
    assert any(b.label == "Kondisi Ekonomi" for b in seksi.baris)
    assert any("potensi besar" in b.nilai for b in seksi.baris)


@pytest.mark.unit
def test_seksi_ai_insight_rekomendasi_aktor_jadi_baris_aksi() -> None:
    """Setiap item rekomendasi_aktor menjadi BarisNilai bertanda 'Aksi (...)'."""
    seksi = _seksi_ai_insight(
        {
            "kondisi_ekonomi": "Kondisi baik.",
            "rekomendasi_aktor": [
                {"aktor": "Swasta", "aksi": "Berinvestasi dalam kopi."},
                {"aktor": "Pemerintah Desa", "aksi": "Gunakan Dana Desa."},
            ],
        }
    )

    label_set = {b.label for b in seksi.baris}
    assert "Aksi (Swasta)" in label_set
    assert "Aksi (Pemerintah Desa)" in label_set


@pytest.mark.unit
def test_seksi_ai_insight_teks_lengkap_fallback() -> None:
    """Jika rekomendasi_aktor kosong tapi teks_lengkap ada, pakai teks_lengkap."""
    seksi = _seksi_ai_insight(
        {"kondisi_ekonomi": "", "rekomendasi_aktor": [], "teks_lengkap": "Analisis lengkap."}
    )

    # kondisi_ekonomi kosong → tidak ada baris Kondisi Ekonomi
    # teks_lengkap tersedia sebagai fallback
    assert any("Ringkasan Analisis" in b.label or "Analisis lengkap" in b.nilai for b in seksi.baris)


@pytest.mark.unit
def test_rakit_ringkasan_ai_insight_none_ikut_serta() -> None:
    """Tanpa ai_insight, laporan tetap terbentuk dan seksi AI Insight hadir
    dengan status belum di-generate."""
    laporan = rakit_ringkasan(_kartu_lengkap(), _pp_lengkap(), _manifest_lengkap())

    seksi_ai = next(
        (s for s in laporan.seksi if s.judul == "AI Insight Desa"),
        None,
    )
    assert seksi_ai is not None
    assert isinstance(seksi_ai, SeksiRingkas)
    assert any("belum di generate" in b.nilai for b in seksi_ai.baris)


@pytest.mark.unit
def test_rakit_ringkasan_ai_insight_tersedia_tampil_di_seksi() -> None:
    """Jika ai_insight disuplai, kontennya muncul di seksi AI Insight."""
    ai_insight = {
        "iddesa": "1801040001",
        "kondisi_ekonomi": "Potensi logistik sangat tinggi.",
        "rekomendasi_aktor": [{"aktor": "Swasta", "aksi": "Bangun gudang distribusi."}],
        "teks_lengkap": "Desa ini strategis.",
    }
    laporan = rakit_ringkasan(
        _kartu_lengkap(), _pp_lengkap(), _manifest_lengkap(), ai_insight=ai_insight
    )

    seksi_ai = next(s for s in laporan.seksi if s.judul == "AI Insight Desa")
    assert isinstance(seksi_ai, SeksiRingkas)
    assert any(b.label == "Kondisi Ekonomi" for b in seksi_ai.baris)
    assert any("Aksi (Swasta)" in b.label for b in seksi_ai.baris)


@pytest.mark.unit
def test_rakit_ringkasan_judul_seksi_urutan_benar() -> None:
    """JUDUL_SEKSI mencakup 'AI Insight Desa' dan urutan seksi sesuai konstanta."""
    laporan = rakit_ringkasan(_kartu_lengkap(), _pp_lengkap(), _manifest_lengkap())

    assert tuple(_judul_unik_berurutan(laporan)) == JUDUL_SEKSI
    assert JUDUL_SEKSI[-1] == "AI Insight Desa"
