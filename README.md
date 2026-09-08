# `api/` — layanan backend SIMPUL DESA

Layanan HTTP baca-saja di atas artefak beku hasil `../data/`, ditambah tiga
fitur dinamis: Asisten Desa (Gemini), Berita Desa (panen RSS ke Supabase), dan
Laporan Desa (PDF). Berkas ini adalah peta operasional folder: apa yang ada di
mana, cara menjalankannya, dan kontrak apa yang dipegang. Berkas ini tidak
menggantikan dokumen lain — ia menunjuk ke sana.

| Mau tahu | Baca |
|---|---|
| Scope produk, matriks akses, daftar rute lengkap dengan detail per endpoint, kontrak galat | `PRD.md` — tidak ikut repo publik |
| Aturan kerja sesi + jebakan teknis yang tidak boleh diulang | `CLAUDE.md` — tidak ikut repo publik |
| Papan tugas lintas sesi | `TRACK.md` — tidak ikut repo publik |
| Definisi istilah produk (Skor Potensi, Zona Peran, Desa Kembar, dst.) | [../GLOSSARY.md](../GLOSSARY.md) |
| Kontrak artefak antar folder (siapa memproduksi apa untuk siapa) | [../README.md](../README.md) |
| Keputusan tahan lama beserta alasan penolakan alternatifnya | [../docs/adr/](../docs/adr/) |

## Status

Kedelapan fase PRD §9 complete per 8 September 2026: kerangka layanan, skrip
build data, endpoint baca, auth + matriks, Asisten Desa, Berita Desa, Admin,
dan Laporan Desa.

| Ukuran | Nilai |
|---|---|
| Rute API terdaftar di `/openapi.json` | 24 path, 24 operasi |
| Uji | 702 lulus, 7,4 detik |
| Cakupan uji `src/` + `bangun/` | 99% (target PRD ≥80%) |
| Kode Python `src/` | 84 berkas, ±6.700 baris |
| Kode uji `tests/` | 55 berkas uji, ±14.000 baris |

Artefak deployment Render sudah ada dan image-nya terverifikasi jalan
(`Dockerfile`, `render.yaml`); yang belum dilakukan hanya menekan deploy.
Langkahnya di [DEPLOY.md](./DEPLOY.md).

## Mulai cepat

Prasyarat: venv bersama proyek di `../.venv` (Python 3.14.6) — dipakai
bersama `../data/`, jangan buat venv terpisah tanpa bertanya. Folder
`../data/` harus ada dan berisi keluaran finalnya, karena build menyalin
dari sana.

```bash
cd api/

# 1. Dependensi (runtime + skrip build + alat pengembangan)
../.venv/bin/python -m pip install -r requirements.txt \
    -r requirements-build.txt -r requirements-dev.txt

# 2. Konfigurasi lokal
cp .env.example .env          # lalu isi kunci yang diperlukan, lihat bagian Konfigurasi

# 3. Bangun data-salinan/ dari ../data/ (sekali, ±125 MB, 363 artefak)
../.venv/bin/python -m bangun

# 4. Jalankan
../.venv/bin/python -m uvicorn src.main:app --reload

# 5. Verifikasi
curl -s localhost:8000/health
```

`/health` membalas amplop berisi versi build data (`hash` + `tanggal` dari
`data-salinan/manifest.json`). Dokumentasi interaktif ada di
`localhost:8000/docs`, skemanya di `localhost:8000/openapi.json`; keduanya
bagian kontrak publik (PRD §3), bukan alat pengembangan yang boleh
dimatikan di produksi.

Tanpa `data-salinan/`, layanan tetap boot tetapi endpoint yang butuh
artefak membalas 503 `DATA_BELUM_SIAP`. Itu perilaku yang disengaja, bukan
kegagalan boot.

## Peta folder

```
api/
├── src/            paket aplikasi — satu folder per domain (ADR-0008)
├── bangun/         skrip build data-salinan/ (CLI: python -m bangun)
├── tests/          suite pytest, cermin struktur src/
├── harness/        eval Asisten Desa — MENYENTUH Gemini sungguhan
├── supabase/       migrasi SQL; skema Supabase milik api/
├── data-salinan/   keluaran build (gitignored, 125 MB, regenerable)
├── .claude/        rencana + laporan PRP per fase, aturan ECC, aturan gaya
├── Dockerfile      image runtime, dua tahap (bongkar arsip data, lalu layanan)
├── render.yaml     blueprint Render — satu web service Docker
├── data-salinan.tar.gz  arsip artefak data (16 MB), SENGAJA ter-commit
├── PRD.md          kontrak produk dan kontrak API (lokal saja)
├── DEPLOY.md       langkah deploy, anggaran memori, jebakan produksi
├── CLAUDE.md       aturan kerja + jebakan teknis folder ini (lokal saja)
└── TRACK.md        papan tugas lintas sesi (lokal saja)
```

Lima subfolder punya README sendiri dengan detail yang tidak diulang di
sini: [`src/README.md`](./src/README.md),
[`bangun/README.md`](./bangun/README.md),
[`tests/README.md`](./tests/README.md),
[`harness/README.md`](./harness/README.md), dan
[`supabase/README.md`](./supabase/README.md).

## Arsitektur

### Lapis

Tidak ada basis data untuk data desa — sumbernya berkas JSON beku di
`data-salinan/`. Supabase dipakai hanya untuk data dinamis (peran pengguna,
berita) dan diakses lewat HTTP PostgREST, bukan lewat driver atau ORM.

```
permintaan HTTP
    │
    ├─ MiddlewareCORS          (terluar — respons galat/304/429 tetap berheader CORS)
    ├─ MiddlewareBatasLaju     (ambang global per-IP)
    ├─ MiddlewareCacheHTTP     (ETag + Cache-Control + 304, hanya prefiks anonim)
    │
    ├─ dependensi peran        (wajib_tamu · wajib_di_atas_tamu · wajib_pemerintah · wajib_admin)
    │
    ├─ router.py               validasi parameter di batas, susun amplop
    ├─ service.py              logika domain, filter, agregasi
    │
    └─ src/datastore.py        Simpanan startup + pembaca per-kabupaten ber-LRU
              │
              ├─ data-salinan/*.json   (beku, baca-saja)
              └─ Supabase PostgREST    (profil, berita_desa — lewat httpx)
```

Middleware yang ditambahkan terakhir berjalan paling luar. CORS diletakkan
terluar supaya respons 304, 429, dan 500 tetap membawa header CORS;
konsekuensi yang diterima adalah preflight `OPTIONS` dijawab sebelum
pembatas laju.

### Alur satu permintaan baca

`GET /api/model/kartu/1801010001` menempuh: cek prefiks cache (kirim 304
bila `If-None-Match` cocok) → validasi `iddesa` 10 digit di batas →
`kartu/service.py` membaca `data-salinan/kartu-ekonomi/kartu/1801.json`
lewat pembaca ber-LRU → `wajib()` melempar 503 `DATA_BELUM_SIAP` bila
artefaknya belum dibangun → 404 `DESA_TIDAK_ADA` bila `iddesa` tidak ada di
berkas itu → amplop sukses berstempel `ETag`.

### Penamaan berkas

Tiga tingkat, ditetapkan [ADR-0008](../docs/adr/0008-struktur-api-modular.md)
dan diterapkan berurutan: nama slot panduan fastapi-best-practices menang
bila slotnya ada (`router.py`, `service.py`, `schemas.py`, `constants.py`,
`dependencies.py`); berkas generik atau teknis tanpa nama fitur memakai
bahasa Inggris (`datastore.py`, `http_cache.py`, folder `auth/`,
`middleware/`); folder fitur produk memakai bahasa Indonesia dan namanya
sama dengan segmen URL yang menamai fitur itu (`citra_potensi/`,
`peta_peran/`, `desa_kembar/`). Tingkat ketiga mengikat dua arah — folder
tidak boleh diterjemahkan, dan segmen URL juga tidak.

## Rute

Daftar lengkap dengan sumber data dan detail per endpoint ada di PRD §5.
Ringkasnya, dikelompokkan menurut akses minimum:

| Akses | Rute |
|---|---|
| Anonim | `GET /health` · `GET /api/wilayah/{provinsi,kabupaten,desa,ringkasan}` · `GET /api/desa/cari` · `GET /api/model/kartu/{iddesa}` · `GET /api/geo/desa/{idkab}` |
| Tamu | `GET /api/model/peta-peran` (+ `/ringkasan`, `/{iddesa}`) · `GET /api/model/citra-potensi` (+ `/sel`) · `GET /api/model/jalur-ekonomi/{varian}` (+ `/{id_jalur}`) · `GET /api/model/desa-kembar/{iddesa}` · `GET /api/berita/{iddesa}` |
| Pemerintah / Swasta | `POST /api/chat` |
| Pemerintah | `GET /api/laporan/{iddesa}` |
| Admin | `POST /api/admin/berita/segarkan` · `DELETE /api/admin/berita/{id_berita}` · `GET /api/admin/pengguna` · `POST /api/admin/pengguna/{id_pengguna}/peran` · `GET /api/admin/status` |

`{varian}` ∈ `komoditas · gudang-kopdes · cold-storage · wisata`.

Tidak ada prefiks versi API. Paginasi seragam lewat `?hal=` (mulai 1,
maksimum 10.000) dan `?batas=` (bawaan 50, maksimum 500). `HAL_MAKS` ada
supaya `hal` sangat besar tidak memaksa sumber data membuang jutaan baris
sebelum membalas halaman kosong.

`HEAD` hanya terdaftar pada `/health`, sengaja lewat dekorator terpisah dari
`@router.get` — `APIRoute` FastAPI tidak menambahkan `HEAD` otomatis, dan
satu rute dua metode membuat `operationId` bertabrakan di `/openapi.json`.
Rute lain sengaja GET saja.

## Amplop respons dan kode galat

Semua respons JSON memakai amplop seragam. Tiga keluaran sengaja di luar
amplop: geo (GeoJSON mentah ter-gzip), laporan (PDF), dan
`/openapi.json` + `/docs` bawaan FastAPI.

```json
{ "sukses": true,  "data": null, "galat": null, "meta": { "total": 0, "hal": 1, "batas": 50 } }
{ "sukses": false, "data": null, "galat": { "kode": "DESA_TIDAK_ADA", "pesan": "…" }, "meta": null }
```

`meta` hanya terisi pada respons berpaginasi; `POST /api/chat` selalu
ber-`meta: null` karena jejak fungsi, model penjawab, cacah putaran alat,
dan peringatan guardrail semuanya ada di dalam `data`.

Kode galat berbahasa Indonesia, UPPER_SNAKE_CASE, terdaftar di satu modul:
`src/exceptions.py`. Pemetaan lengkap status HTTP ke kode ada di PRD §6.
Satu jebakan yang mengikat penambahan berikutnya: status yang tidak
terdaftar di `_KODE_PER_STATUS` jatuh ke `GALAT_SERVER`, jadi galat klien
baru yang muncul kelak harus ikut didaftarkan — kalau tidak, galat klien
dilaporkan sebagai galat server.

API mengirim angka JSON mentah. Konvensi tampilan GLOSSARY (koma desimal,
titik ribuan) sepenuhnya urusan `../app/`.

## Autentikasi dan peran

Autentikasi memakai Supabase: layanan memverifikasi JWT Supabase terhadap
JWKS proyek, lalu membaca peran dari kolom `profil.peran` lewat PostgREST.
Tanpa token = anonim. Empat peran sah: `tamu`, `pemerintah`, `swasta`,
`admin`; peran lebih tinggi mewarisi akses di bawahnya, dengan satu
pengecualian — laporan bukan hak swasta.

Penegakan terjadi di titik `include_router` pada `src/main.py`, bukan
di dalam tiap handler, sehingga satu router = satu gerbang peran.
Himpunan perannya konstanta di `src/auth/constants.py`.

Dua hal yang mudah salah dan sudah punya uji penjaga:

- `wajib_peran` mengembalikan `Identitas` (`id` + `peran`), bukan `str` —
  penjaga "admin tidak bisa mengubah peran sendiri" butuh `id` pemanggil.
- Nilai `peran` di luar empat peran sah membalas 403 `PERAN_TIDAK_DIKENAL`,
  bukan 503: basis data menjawab dengan benar, hanya nilainya yang asing.
  Nilai itu dan `id` penggunanya masuk log, tidak pernah ke pemanggil.

Kenaikan peran hanya lewat endpoint admin; registrasi mandiri selalu
menghasilkan `tamu`. Skema Supabase dan migrasinya milik folder ini —
lihat [`supabase/README.md`](./supabase/README.md).

## Middleware

Tiga `BaseHTTPMiddleware` di `src/middleware/`, dan ketiganya memisahkan
jalur berdasarkan prefiks path. Prefiks dicocokkan PER SEGMEN
(`path == p or path.startswith(p + "/")`), bukan `startswith` polos — dengan
`startswith` polos, rute masa depan seperti `/api/model/kartu-interno` akan
diam-diam mewarisi ETag publik milik prefiks `/api/model/kartu`.

| Middleware | Berkas | Yang dilakukan |
|---|---|---|
| `MiddlewareCORS` | `cors.py` | `GET` pada prefiks publik dibuka ke semua origin; endpoint bertoken dan seluruh non-`GET` dibatasi ke origin `../app/` |
| `MiddlewareBatasLaju` | `rate_limit.py` | ambang global per-IP (`LAJU_BAWAAN`), satu bucket per IP |
| `MiddlewareCacheHTTP` | `http_cache.py` | `ETag` (hash build) + `Cache-Control: public` + jawaban 304 pada prefiks data anonim; `no-store` pada prefiks bertoken |

Pemisahan prefiksnya:

| Himpunan | Isi |
|---|---|
| `PREFIKS_PUBLIK` (CORS terbuka) | `/health` · `/api/wilayah` · `/api/desa` · `/api/model/kartu` · `/api/geo` · `/openapi.json` · `/docs` |
| `PREFIKS_CACHE` (ETag + 304) | `/api/wilayah` · `/api/desa` · `/api/model/kartu` · `/api/geo` |
| `PREFIKS_TANPA_CACHE` (`no-store`) | `/api/model/peta-peran` · `/api/model/citra-potensi` · `/api/model/jalur-ekonomi` · `/api/model/desa-kembar` · `/api/berita` · `/api/admin` · `/api/laporan` · `/api/chat` |

Kenapa dipisah begitu: `Cache-Control: public` pada respons berotorisasi
membuat shared cache membocorkan body ke pemanggil lain, dan 304 dari
middleware dijawab SEBELUM dependensi auth berjalan. Keduanya temuan
CRITICAL fase 4; kontraknya di PRD §5.

Pembatas laju TIDAK memakai `SlowAPIMiddleware` bawaan slowapi. Sejak
FastAPI 0.141 `app.routes` berisi objek `_IncludedRouter` tanpa atribut
`endpoint`, lookup handler slowapi gagal, dan semua rute diam-diam lolos
rate limit. `MiddlewareBatasLaju` menggantikannya. Ambang `/api/chat`
(`LAJU_CHAT`) berlaku PER PENGGUNA lewat dekorator `@limiter.limit` di
`src/chat/router.py` dan berdampingan dengan ambang global per-IP — satu
permintaan chat dihitung di kedua bucket.

## Konfigurasi

Semua konfigurasi dari environment variable, dibaca `src/config.py` lewat
`pydantic-settings`; `.env` untuk pengembangan lokal dan tidak pernah
di-commit. Salin dari [`.env.example`](./.env.example), yang selalu
dijaga lengkap.

| Variabel | Bawaan | Peran |
|---|---|---|
| `LINGKUNGAN` | `dev` | di luar `dev`, konfigurasi rawan salah menggagalkan boot |
| `DIR_DATA` | `data-salinan` | akar artefak build yang dibaca runtime |
| `ORIGIN_APP` | `http://localhost:3000` | origin dasbor yang diizinkan untuk non-`GET` dan endpoint bertoken |
| `CACHE_MAX_AGE` | `3600` | umur `Cache-Control: public` pada prefiks cache |
| `SUPABASE_URL` | kosong | wajib `https://`; kosong = endpoint bertoken 503 |
| `SUPABASE_SERVICE_ROLE_KEY` | kosong | kunci sisi server, rahasia |
| `LAJU_BAWAAN` | `120/minute` | ambang global per-IP |
| `LAJU_CHAT` | `10/minute;200/day` | ambang `/api/chat` per pengguna |
| `JWT_AUDIENCE` | `authenticated` | klaim `aud` yang wajib ada di token |
| `WEB_CONCURRENCY` | `1` | WAJIB 1 di luar `dev` |
| `GEMINI_API_KEY` | kosong | kunci panen Berita Desa; kosong = rangkuman ekstraktif tanpa saring topik LLM |
| `GEMINI_API_KEY_CHAT` | kosong | kunci Asisten Desa; kosong = `/api/chat` 503 `AI_BELUM_SIAP` |
| `MODEL_CHAT` / `MODEL_CHAT_CADANGAN` | `gemini-flash-latest` / `gemini-flash-lite-latest` | alias `-latest` disengaja; nama pinned terbukti 404 di `generateContent` |
| `CHAT_MAKS_PESAN` / `CHAT_MAKS_KARAKTER` / `CHAT_MAKS_PUTARAN_ALAT` | `20` / `4000` / `5` | batas masukan dan putaran alat satu permintaan chat |
| `MAKS_CACHE_KARTU` / `MAKS_CACHE_JALUR` / `MAKS_CACHE_CITRA` / `MAKS_CACHE_KEMBAR` | `16` / `4` / `16` / `16` | `maxsize` empat cache LRU pembaca berkas. Tombol MEMORI, bukan kecepatan — lihat [DEPLOY.md](./DEPLOY.md) |

Dua hal yang gagal saat boot, bukan gagal saat dipakai, karena jalan
pincang lebih buruk daripada mati keras:

- `WEB_CONCURRENCY > 1` di luar `dev`. Gerbang "satu pekerjaan penyegaran
  pada satu waktu" (yang menjawab 409) menyimpan state di memori proses,
  jadi beberapa worker mengubahnya diam-diam menjadi satu pekerjaan PER
  worker — tiap worker bisa memanen sampai 50 desa sekaligus. Lock bersama
  ditolak untuk MVP; lihat
  [ADR-0010](../docs/adr/0010-api-satu-proses-bukan-lock-bersama.md).
- `ORIGIN_APP` non-https atau kredensial Supabase kosong di luar `dev`.

**Dua kunci Gemini terpisah, sengaja.** Panen Berita Desa dan Asisten Desa
memakai variabel berbeda. Satu penyegaran 50 desa bisa menghabiskan kuota
per-menit tepat saat pengguna sedang memakai chat, jadi kunci chat kosong
membalas 503 dan TIDAK PERNAH jatuh ke kunci berita.

## Data

Sumber data selalu salinan build dari keluaran `../data/`; layanan ini tidak
pernah menghitung ulang apa pun yang sudah dihitung di sana, dan tidak pernah
menulis ke `data-salinan/` saat runtime.

Build dijalankan dengan `python -m bangun` dan menghasilkan
`data-salinan/` beserta `manifest.json` (asal, sha256, ukuran per artefak,
plus hash gabungan dan tanggal yang menjadi versi data di `/health` dan
`ETag`). Tahapan, bendera CLI, dan tata letak keluarannya ada di
[`bangun/README.md`](./bangun/README.md).

Pemuatan runtime: `indeks.json` kartu dan berkas kecil dimuat sekali saat
start ke `app.state.simpanan`; berkas per kabupaten dibaca dari disk per
permintaan dengan cache LRU. Pilihan itu ada karena memori host produksi
tidak cukup untuk memuat semuanya.

Penjaga kontrak data yang mengikat semua endpoint (PRD §8) — diuji, bukan
diandaikan:

- Join berbasis `iddesa`, divalidasi di batas; 404 bila tidak dikenal.
- Koordinat placeholder Kemenparekraf (`-6.2297465, 106.829518`) disaring
  dari semua respons wisata.
- Hasil ML wisata tidak pernah tampil sebagai Skor Potensi
  ([ADR-0004](../docs/adr/0004-wisata-di-luar-skor-potensi.md)).
- Kode wilayah klaim sumber eksternal tidak dipercaya — hanya kode yang
  sudah diverifikasi `../data/` yang disajikan.
- Kolom mutu tidak pernah disaring dari respons: bendera keyakinan rendah,
  keadaan Belum Terpetakan, kode kosong, dan Sumber Potensi Dominan wajib
  ikut terkirim. Mutu harus terbaca.

Satu konsekuensi dari poin terakhir yang mudah dilanggar tanpa sadar:
artefak yang ADA tapi kehilangan kunci internal bukan hal yang sama dengan
artefak yang hilang. `muat_json_atau_none` sengaja tidak memvalidasi isi,
jadi tiap pemanggil harus memilih sikap dan menuliskan alasannya — kunci
tingkat atas hilang berarti 503 lewat `wajib()`, satu baris cacat berarti
dilewati plus `logger.warning`. Menambalnya dengan `.get()` berdefault
pada kolom mutu terlarang: `None` yang dikarang tidak bisa dibedakan
pembaca dari nilai kosong yang sah.

## Uji

```bash
../.venv/bin/python -m pytest                    # seluruh suite + laporan cakupan
../.venv/bin/python -m pytest tests/chat -q      # satu domain
../.venv/bin/python -m pytest -k nama_uji        # satu uji
```

`pyproject.toml` mengunci `testpaths = ["tests"]` dan menyalakan
`--cov=src --cov=bangun --cov-report=term-missing` secara bawaan. Suite
berjalan tanpa jaringan: Supabase ditiru, Gemini ditiru, artefak dibangun
di `tmp_path`. Kalau suite tiba-tiba berjalan puluhan detik alih-alih di
bawah sepuluh detik, curigai tiruan yang terlepas — bukan mesin yang
lambat. Konvensi, fixture, dan daftar uji penjaga ada di
[`tests/README.md`](./tests/README.md).

`harness/` sengaja di LUAR `testpaths` karena ia menyentuh Gemini
sungguhan. Melebarkan `testpaths` ke folder itu membuat `pytest` polos
membakar kuota; penjaganya `tests/chat/test_harness_terpisah.py`.

## Deploy

Satu web service Docker di Render, didefinisikan
[`render.yaml`](./render.yaml). Langkah, verifikasi, dan jebakannya di
[DEPLOY.md](./DEPLOY.md); di sini hanya bentuk besarnya.

Artefak data TIDAK dibangun di sisi Render. `python -m bangun` membaca
`../data/`, yang bukan bagian repo ini (ADR-0009), jadi folder itu tidak
pernah ada di lingkungan build. Yang dikirim adalah
`data-salinan.tar.gz` — 16 MB terkompresi dari 125 MB, ikut ter-commit,
dibongkar di tahap build terpisah supaya arsipnya tidak tinggal di image
jadi. Konsekuensinya: data produksi hanya berubah kalau tarball-nya
diperbarui dan di-commit. Keputusan itu beserta lima alternatif yang
ditolak ada di
[ADR-0011](../docs/adr/0011-artefak-data-api-tarball-ter-commit.md).

```bash
docker build --platform linux/amd64 -t simpul-desa-api .
docker run --rm -p 8000:8000 -e LINGKUNGAN=dev simpul-desa-api
```

Dua hal yang mengikat image dan tidak boleh dilepas:

- **`--proxy-headers` di `CMD`.** Tanpanya `request.client.host` selalu
  berisi IP proxy Render, dan `get_remote_address` slowapi menaruh seluruh
  pemanggil dalam satu bucket `LAJU_BAWAAN` — satu pengunjung ramai
  membuat semua orang kena 429.
- **`maxsize` cache diturunkan lewat environment.** Muat `Simpanan` saat
  start terukur 164 MB, satu entri cache jalur ekonomi ±103 MB, satu entri
  kartu ±13 MB. Dengan bawaan pengembangan, instance 512 MB dimatikan OOM
  tanpa satu baris log dari aplikasi. Nilai produksinya ada di
  `render.yaml`, perhitungannya di DEPLOY.md.

## Mutu kode

```bash
../.venv/bin/python -m black src tests bangun harness
../.venv/bin/python -m isort src tests bangun harness
../.venv/bin/python -m ruff check src tests bangun harness
../.venv/bin/python -m mypy src bangun
```

Keempatnya wajib (CLAUDE.md §6) — Ruff-saja ditolak karena membuang
pemeriksaan tipe, yang justru penjaga utama saat berkas dipindah antar
modul. `mypy` berjalan dengan `disallow_untyped_defs`, jadi setiap
signature fungsi butuh anotasi. Konfigurasi ketiganya di `pyproject.toml`.

## Peta dokumen folder ini

| Berkas | Isi |
|---|---|
| `README.md` | berkas ini — peta operasional |
| `PRD.md` | kontrak produk dan kontrak API, 13 bagian. Lokal saja |
| `DEPLOY.md` | deploy Render: langkah, anggaran memori terukur, jebakan produksi |
| `CLAUDE.md` | aturan kerja sesi + jebakan teknis yang sudah terbukti. Lokal saja |
| `TRACK.md` | papan tugas, satu subbab per sesi. Lokal saja |
| `src/README.md` | peta modul aplikasi + cara menambah domain baru |
| `bangun/README.md` | tahapan build, bendera CLI, tata letak keluaran |
| `tests/README.md` | menjalankan uji, fixture, konvensi, uji penjaga |
| `harness/README.md` | eval Asisten Desa dan rel kuotanya |
| `supabase/README.md` | migrasi SQL, replikasi ke proyek baru |
| `.claude/` | rencana dan laporan PRP per fase, aturan ECC, aturan gaya — catatan proses, lokal saja |
