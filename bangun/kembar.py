"""Precompute Desa Kembar — tetangga terdekat (kNN) per desa dalam kabupaten.

Modul ini menghitung, untuk tiap kabupaten, daftar "desa kembar" (desa
berprofil mirip) bagi setiap desa di dalamnya, memakai model
`model_desa_kembar_v3.json` (16 kolom terbobot, k=12, metrik Manhattan).
Pencarian tetangga SELALU dalam kabupaten sendiri (README desa-kembar),
tidak lintas kabupaten.

Transformasi fitur (z-score per kabupaten atas kolom mentah + persentil
per kabupaten) DIREPLIKASI dari `siapkan_semua()` pada
`../data/machine-learning/desa-kembar/eksperimen_knn2.py`, TANPA bagian
penyaringan target — `siapkan_semua()` membuang kabupaten yang tak punya
label latih (89 dari 97 kabupaten selamat), padahal Desa Kembar harus
mencakup SEMUA 97 kabupaten. `../data/` bersifat baca-saja (frozen); modul
sumber diimpor secara lambat (lazy) via manipulasi `sys.path`, termasuk
nama privat `_persentil` — sengaja, karena fungsi itu adalah satu-satunya
sumber kebenaran untuk rumus persentil per kabupaten dan tidak ada
salinan publik.

Rumus kemiripan (GLOSSARY.md, baku):
    persen = clip((1 - jarak / p95) * 100, 0, 100)
dengan p95 = persentil ke-95 jarak Manhattan berpasangan antar desa DALAM
kabupaten yang sama, di ruang 16 kolom terbobot model.
"""

import json
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import pairwise_distances
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from bangun.konstanta import (
    AKAR_DATA,
    BERKAS_MODEL_KEMBAR,
    DIR_KELUARAN,
    DIR_SKRIP_KEMBAR,
)

try:
    from bangun.manifest import sha256_berkas
except ImportError:  # pragma: no cover - fallback bila manifest.py belum ditulis
    import hashlib

    def sha256_berkas(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as sumber:
            for potongan in iter(lambda: sumber.read(65536), b""):
                hasher.update(potongan)
        return hasher.hexdigest()


logger = logging.getLogger(__name__)

JUMLAH_KAB_PROGRES = 10


def hitung_tetangga_kab(
    x16: np.ndarray, iddesa: list[str], k: int
) -> tuple[dict[str, list[dict[str, object]]], float]:
    """Hitung tetangga terdekat (desa kembar) tiap desa dalam SATU kabupaten.

    Fungsi murni: tidak ada I/O. `x16` adalah matriks (n, 16) fitur desa
    dalam satu kabupaten yang SUDAH dikalikan bobot kolom model; `iddesa`
    adalah daftar id desa sepanjang n, sejajar barisnya dengan `x16`.

    Jarak antar desa dihitung dengan metrik Manhattan (cityblock). Jarak
    dipetakan ke persen kemiripan dengan rumus baku (GLOSSARY.md):
    persen = clip((1 - jarak / p95) * 100, 0, 100), dengan p95 = persentil
    ke-95 dari jarak Manhattan berpasangan antar SEMUA desa dalam
    kabupaten ini. Kalau p95 == 0 (seluruh desa identik setelah
    standardisasi, kasus langka), setiap tetangga diberi persen 100.0
    alih-alih membagi dengan nol.

    Diri sendiri tidak pernah muncul di daftar tetangganya sendiri (dibuang
    berdasarkan indeks baris, bukan jarak, sehingga aman walau ada desa
    lain yang jaraknya juga 0 terhadap desa tersebut). Catatan tie-break:
    kalau lebih dari `k+1` desa identik (jarak 0 satu sama lain), diri
    sendiri dijamin ikut terpilih HANYA kalau `k+1 >= n` (yaitu semua desa
    dalam kabupaten diminta sebagai tetangga) — di luar itu urutan tie
    bergantung implementasi sklearn dan tidak dijamin.

    Args:
        x16: matriks (n, 16) fitur desa, sudah dikalikan bobot kolom.
        iddesa: daftar id desa sepanjang n, sejajar baris dengan `x16`.
        k: jumlah tetangga maksimum per desa (tidak termasuk diri sendiri).

    Returns:
        Tuple (pemetaan iddesa -> daftar tetangga, p95_jarak). Tiap
        tetangga adalah dict {"iddesa": str, "persen": float} dan daftar
        terurut menurun berdasarkan persen.
    """
    n = len(iddesa)
    if n == 0:
        return {}, 0.0
    if n == 1:
        return {iddesa[0]: []}, 0.0

    jarak_pasangan = pairwise_distances(x16, metric="cityblock")
    baris_atas, kolom_atas = np.triu_indices(n, k=1)
    p95 = float(np.percentile(jarak_pasangan[baris_atas, kolom_atas], 95))

    k_efektif = min(k + 1, n)
    model_nn = NearestNeighbors(
        n_neighbors=k_efektif, metric="manhattan", algorithm="brute"
    )
    model_nn.fit(x16)
    jarak, indeks = model_nn.kneighbors(x16)

    hasil: dict[str, list[dict[str, object]]] = {}
    for baris, id_asal in enumerate(iddesa):
        tetangga: list[dict[str, object]] = []
        for jarak_i, idx_i in zip(jarak[baris], indeks[baris]):
            if idx_i == baris:
                continue
            if p95 == 0.0:
                persen = 100.0
            else:
                persen = float(np.clip((1 - jarak_i / p95) * 100, 0.0, 100.0))
            tetangga.append({"iddesa": iddesa[idx_i], "persen": round(persen, 1)})
        hasil[id_asal] = tetangga[:k]
    return hasil, p95


def precompute_semua(
    akar_data: Path = AKAR_DATA,
    dir_keluaran: Path = DIR_KELUARAN,
    hanya_kab: set[str] | None = None,
) -> list[dict[str, object]]:
    """Precompute desa kembar untuk tiap kabupaten dan tulis satu JSON per kabupaten.

    Memuat model (`kolom`, `bobot_kolom`, `k`) dari `BERKAS_MODEL_KEMBAR`,
    lalu mengimpor modul sumber `eksperimen_knn2.py` secara lambat (lazy,
    lewat `sys.path`) untuk memakai ulang `muat()`, `MENTAH`, `SEMUA_NAMA`,
    dan `_persentil()` — replikasi transformasi fitur `siapkan_semua()`
    TANPA penyaringan target, supaya seluruh kabupaten tercakup (lihat
    docstring modul).

    Args:
        akar_data: akar `data/` proyek (default `AKAR_DATA`).
        dir_keluaran: akar keluaran; berkas ditulis ke
            `dir_keluaran / "desa-kembar" / f"{idkab}.json"`.
        hanya_kab: kalau diisi, hanya proses kabupaten dengan idkab di
            himpunan ini (dipakai untuk uji cepat / precompute parsial).

    Returns:
        Daftar entri manifest (satu per berkas kabupaten ditulis): path
        relatif, sumber, sha256, dan ukuran bytes.
    """
    model = json.loads((akar_data / BERKAS_MODEL_KEMBAR).read_text(encoding="utf-8"))
    kolom: list[str] = model["kolom"]
    bobot_kolom = np.asarray(model["bobot_kolom"], dtype=float)
    k: int = model["k"]

    sys.path.insert(0, str(akar_data / DIR_SKRIP_KEMBAR))
    from eksperimen_knn2 import (
        MENTAH,
        SEMUA_NAMA,
        _persentil,
        muat,
    )

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)
        df: pd.DataFrame = muat()
        for kol in MENTAH:
            df[f"pr:{kol}"] = _persentil(df[kol], df["idkab"])

    idx = [SEMUA_NAMA.index(kol) for kol in kolom]

    daftar_kab = sorted(df["idkab"].unique())
    if hanya_kab is not None:
        daftar_kab = [kab for kab in daftar_kab if kab in hanya_kab]

    dir_kembar = dir_keluaran / "desa-kembar"
    dir_kembar.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict[str, object]] = []
    for i, kab in enumerate(daftar_kab):
        g = df[df.idkab == kab].reset_index(drop=True)
        x_kab = StandardScaler().fit_transform(g[SEMUA_NAMA].to_numpy(float))
        x_kab = np.nan_to_num(x_kab)
        x16 = x_kab[:, idx] * bobot_kolom
        iddesa_list: list[str] = g["iddesa"].tolist()

        pemetaan, p95 = hitung_tetangga_kab(x16, iddesa_list, k)

        path_keluaran = dir_kembar / f"{kab}.json"
        payload = {"idkab": kab, "k": k, "p95_jarak": p95, "desa": pemetaan}
        path_keluaran.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8"
        )

        manifest_entries.append(
            {
                "path": f"desa-kembar/{kab}.json",
                "sumber": "turunan:model_desa_kembar_v3 + desa_ml.csv",
                "sha256": sha256_berkas(path_keluaran),
                "bytes": path_keluaran.stat().st_size,
            }
        )

        if (i + 1) % JUMLAH_KAB_PROGRES == 0:
            logger.info(
                "precompute desa-kembar: %d/%d kabupaten", i + 1, len(daftar_kab)
            )

    logger.info(
        "precompute desa-kembar selesai: %d kabupaten, %d berkas ditulis",
        len(daftar_kab),
        len(manifest_entries),
    )
    return manifest_entries
