"""Konstanta skrip build data-salinan/ — path sumber, cakupan, dan daftar artefak."""

from pathlib import Path

AKAR_DATA = Path(__file__).resolve().parents[2] / "data"
DIR_KELUARAN = Path(__file__).resolve().parents[1] / "data-salinan"

# Nama provinsi cakupan MVP (PRD akar §2). Nama tidak ada di artefak mana pun;
# konstanta konfigurasi, bukan angka hasil.
PROVINSI = {
    "18": "Lampung",
    "33": "Jawa Tengah",
    "52": "Nusa Tenggara Barat",
    "63": "Kalimantan Selatan",
    "73": "Sulawesi Selatan",
}

# Toleransi simplifikasi GeoJSON dalam derajat (~50 m). Pertanyaan terbuka
# PRD §13 — angka final menunggu cek visual di peta app/.
TOLERANSI_GEO_BAKU = 0.0005

# Artefak kontrak README akar: (sumber relatif AKAR_DATA, tujuan relatif
# DIR_KELUARAN). Entri direktori disalin per berkas *.json di dalamnya.
ARTEFAK_KONTRAK: list[tuple[str, str]] = [
    ("fitur/kartu-ekonomi-desa/keluaran/indeks.json", "kartu-ekonomi/indeks.json"),
    ("fitur/kartu-ekonomi-desa/keluaran/kartu", "kartu-ekonomi/kartu"),
    ("fitur/peta-peran/keluaran/peta_peran.json", "peta-peran/peta_peran.json"),
    (
        "fitur/peta-peran/keluaran/ringkasan_kab.json",
        "peta-peran/ringkasan_kab.json",
    ),
    (
        "machine-learning/citra-potensi-desa/v5/produksi/indeks.json",
        "citra-potensi/indeks.json",
    ),
    (
        "machine-learning/jalur-ekonomi/varian-komoditas/hasil_komoditas.json",
        "jalur-ekonomi/hasil_komoditas.json",
    ),
    (
        "machine-learning/jalur-ekonomi/varian-gudang-kopdes/hasil_gudang.json",
        "jalur-ekonomi/hasil_gudang.json",
    ),
    (
        "machine-learning/jalur-ekonomi/varian-cold-storage/hasil_cold_storage.json",
        "jalur-ekonomi/hasil_cold_storage.json",
    ),
    (
        "machine-learning/jalur-ekonomi/varian-wisata/hasil_wisata.json",
        "jalur-ekonomi/hasil_wisata.json",
    ),
    *[
        (
            f"machine-learning/citra-potensi-desa/v5/produksi/{prov}",
            f"citra-potensi/produksi/{prov}",
        )
        for prov in ("18", "33", "52", "63", "73")
    ],
]

# Bahan grounding metodologi Asisten Desa (PRD §7 butir 4).
# (sumber ABSOLUT-relatif akar proyek, tujuan relatif DIR_KELUARAN/metodologi)
BERKAS_METODOLOGI: list[tuple[str, str]] = [
    ("GLOSSARY.md", "GLOSSARY.md"),
    ("data/README.md", "data-README.md"),
    ("data/fitur/kartu-ekonomi-desa/README.md", "kartu-ekonomi-README.md"),
    ("data/fitur/peta-peran/README.md", "peta-peran-README.md"),
    ("data/machine-learning/desa-kembar/README.md", "desa-kembar-README.md"),
    ("data/machine-learning/jalur-ekonomi/MODEL.md", "jalur-ekonomi-MODEL.md"),
]

DIR_BATAS_DESA = "panen/batas_desa"
AKHIRAN_GEO = ".geojson.gz"  # akhiran berkas keluaran tahap 5 (geo.py) & 6 (pusat.py)
BERKAS_MODEL_KEMBAR = "machine-learning/desa-kembar/model_desa_kembar_v3.json"
DIR_SKRIP_KEMBAR = "machine-learning/desa-kembar"
