# `bangun/` — skrip build `data-salinan/`

Menyiapkan artefak yang dibaca layanan saat runtime: menyalin keluaran
`../../data/`, menurunkan dua artefak baru, dan menstempel `manifest.json`
sebagai versi data. Dijalankan sebelum layanan dinyalakan dan sebelum
deploy — bukan saat permintaan masuk.

Kontrak artefak antar folder ada di [../../README.md](../../README.md);
tahapan build sebagai keputusan produk ada di `../PRD.md` §7 (lokal saja).

## Pemakaian

```bash
cd api/
../.venv/bin/python -m bangun                          # build penuh
../.venv/bin/python -m bangun --lewati-geo             # tanpa simplifikasi GeoJSON (tahap terlama)
../.venv/bin/python -m bangun --lewati-kembar          # tanpa precompute Desa Kembar
../.venv/bin/python -m bangun --toleransi-geo 0.001    # toleransi simplifikasi lain
```

| Bendera | Bawaan | Arti |
|---|---|---|
| `--toleransi-geo` | `0.0005` (±50 m) | toleransi `shapely.simplify` dalam derajat |
| `--lewati-geo` | mati | lewati tahap 5 |
| `--lewati-kembar` | mati | lewati tahap 4 |
| `--akar-data` | `../data` | akar direktori sumber |
| `--dir-keluaran` | `./data-salinan` | direktori keluaran build |

Keluar dengan kode 0 bila seluruh tahap sukses, 1 bila ada tahap yang gagal.
Sukses dicetak sebagai satu baris ringkasan: cacah artefak, total byte, hash
pendek, dan tanggal.

Angka referensi build 7 September 2026: 363 artefak, ±125 MB.

## Tahapan

Berjalan berurutan; `tulis_manifest` SELALU tahap terakhir, sehingga
kegagalan tahap mana pun menjamin `manifest.json` tidak pernah ditulis. Itu
yang membuat "ada manifest" bisa dipercaya sebagai "build selesai utuh".

| # | Tahap | Modul | Isi |
|---|---|---|---|
| 1 | Salin artefak kontrak | `salin.py` | kartu ekonomi (indeks + per kabupaten), peta peran + ringkasan kabupaten, citra potensi (indeks + skor per sel lima provinsi), empat hasil jalur ekonomi |
| 2 | Salin bahan metodologi | `salin.py` | `GLOSSARY.md` akar plus lima README/MODEL.md `data/`, sebagai grounding jawaban metodologi Asisten Desa |
| 3 | Turunkan wilayah | `wilayah.py` | `wilayah.json`: provinsi (nama dari konstanta) + kabupaten unik dari indeks kartu |
| 4 | Precompute Desa Kembar | `kembar.py` | tetangga terdekat per desa, disimpan JSON per kabupaten |
| 5 | Sederhanakan batas desa | `geo.py` | GeoJSON per kabupaten disederhanakan + gzip |
| 6 | Hitung pusat kabupaten | `pusat.py` | `pusat_wilayah.json`: pusat tiap kabupaten (rerata tengah bbox per fitur/desa) dari GeoJSON tahap 5 |
| — | Tulis manifest | `manifest.py` | `manifest.json`: entri per artefak + hash gabungan + tanggal |

Tahap 6 membaca KELUARAN tahap 5 (`dir_keluaran/geo`), bukan `data/` mentah —
tanpa bendera lewati sendiri, jadi tetap jalan walau `--lewati-geo` dipakai.
Tapi kalau `--lewati-geo` dipakai pada `--dir-keluaran` yang bersih (`geo/`
belum pernah dibangun sebelumnya), `pusat_wilayah.json` yang ditulis
berisi `kabupaten` kosong; `src/datastore.py` menolak artefak kosong itu
sebagai belum siap (503 `DATA_BELUM_SIAP`), bukan menyajikannya kosong ke
`app/`.

## Keluaran

```
data-salinan/
├── manifest.json              versi data — dibaca /health dan jadi ETag
├── wilayah.json               turunan tahap 3
├── kartu-ekonomi/
│   ├── indeks.json            baris ringkas seluruh desa, dimuat sekali saat start
│   └── kartu/<idkab>.json     kartu penuh, dibaca per permintaan (LRU)
├── peta-peran/
│   ├── peta_peran.json
│   └── ringkasan_kab.json
├── citra-potensi/
│   ├── indeks.json
│   └── produksi/<prov>/*.json skor per sel, lima provinsi cakupan
├── jalur-ekonomi/hasil_{komoditas,gudang,cold_storage,wisata}.json
├── desa-kembar/<idkab>.json   turunan tahap 4
├── geo/<idkab>.geojson.gz     turunan tahap 5
├── pusat_wilayah.json         turunan tahap 6, dari geo/ di atas
└── metodologi/*.md            turunan tahap 2
```

Satu entri manifest berbentuk:

```json
{
  "path": "citra-potensi/indeks.json",
  "sumber": "/abs/path/ke/data/machine-learning/citra-potensi-desa/v5/produksi/indeks.json",
  "sha256": "4fe20e43…",
  "bytes": 14886
}
```

Di tingkat atas, manifest membawa `hash` (gabungan seluruh artefak),
`tanggal` (format `YYYY-MM-DD`), dan `artefak` (daftar entri di atas).

Folder `data-salinan/` gitignored seluruhnya — 125 MB yang bisa dibangun
ulang dari `../../data/` kapan saja. Ia BUKAN sampah: layanan membacanya
setiap permintaan.

## Dua tahap yang bukan sekadar menyalin

**Tahap 4, Desa Kembar.** Perhitungan turunan milik `api/`, bukan salinan:
`../../data/` beku, jadi tetangga terdekat dihitung di sini memakai
spesifikasi `model_desa_kembar_v3.json` (16 kolom terbobot, k=12, metrik
Manhattan) atas fitur `desa_ml.csv`. Pencarian SELALU di dalam kabupaten
sendiri, tidak lintas kabupaten. Transformasi fiturnya (z-score per
kabupaten + persentil per kabupaten) direplikasi dari `siapkan_semua()`
pada `../../data/machine-learning/desa-kembar/eksperimen_knn2.py` TANPA
bagian penyaringan target — penyaringan itu membuang kabupaten yang tak
punya label latih (89 dari 97 selamat), sedangkan Desa Kembar harus
mencakup semua 97 kabupaten. Persen kemiripan memakai rumus GLOSSARY.

**Tahap 5, GeoJSON.** `shapely.simplify(preserve_topology=True)`, properti
dipangkas ke `{"iddesa", "nmdesa", "pusat"}` — `pusat` (`[lon, lat]`) adalah
titik tengah bbox geometri SETELAH disederhanakan, dibulatkan 5 desimal,
dihitung lewat `bangun.pusat.pusat_bbox_fitur` — lalu ditulis gzip level 9.
Sengaja hanya `json` + `shapely`, tanpa geopandas, untuk menghindari
dependensi driver I/O-nya. Toleransi finalnya masih pertanyaan terbuka PRD
§13 — angkanya menunggu cek visual di peta `../../app/`.

## Cakupan dan konstanta

Lima provinsi cakupan MVP, namanya konstanta di `konstanta.py` karena tidak
ada di artefak mana pun: `18` Lampung, `33` Jawa Tengah, `52` Nusa Tenggara
Barat, `63` Kalimantan Selatan, `73` Sulawesi Selatan. Kode provinsi yang
tidak dikenal saat menurunkan wilayah dianggap korupsi data dan
menghentikan proses — gagal cepat, bukan diam-diam dilewati.

Daftar artefak kontrak, bahan metodologi, dan path sumber semuanya di
`konstanta.py`. Menambah artefak yang dikonsumsi layanan berarti menambah
satu entri di sana, bukan menyunting `salin.py`.

## Uji

```bash
../.venv/bin/python -m pytest tests/bangun
```

Enam berkas uji, satu per modul plus satu untuk orkestrasi
(`test_orkestrasi.py`). Cakupan `bangun/` ikut dihitung `pytest --cov`
bawaan folder `api/`.
