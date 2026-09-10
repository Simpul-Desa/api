# Layanan Backend SIMPUL DESA

API HTTP baca-saja di atas artefak data beku, ditambah tiga fitur dinamis:
Asisten Desa (LLM), Berita Desa (panen RSS ke Supabase), dan Laporan Desa
(PDF).

Repo ini adalah satu dari empat sistem SIMPUL DESA (DATATHON 2026 — Sistem
Intelijen Potensi dan Kesiapan Ekonomi Desa):

| Sistem | Repo | Peran |
|---|---|---|
| API | repo ini | layanan backend yang menyajikan seluruh endpoint |
| Portal | [Simpul-Desa/portal](https://github.com/Simpul-Desa/portal) | dasbor web pengguna, konsumen utama API ini |
| Data | [Simpul-Desa/data](https://github.com/Simpul-Desa/data) | panen data dan pemodelan; produsen artefak yang disajikan API ini |
| Dokumentasi | [Simpul-Desa/docs](https://github.com/Simpul-Desa/docs) | situs dokumentasi produk dan rujukan REST API |

Berkas ini adalah peta operasional repo API: apa yang ada di mana, cara
menjalankannya, dan kontrak apa yang dipegang.

## Status

Delapan fase pengembangan selesai per 10 September 2026: kerangka layanan,
skrip build data, endpoint baca, autentikasi dan matriks akses, Asisten Desa,
Berita Desa, Administrasi, dan Laporan Desa.

| Ukuran | Nilai |
|---|---|
| Rute terdaftar di `/openapi.json` | 26 path, 26 operasi, 14 tag |
| Uji | 755 lulus, ±8 detik |
| Cakupan uji `src/` + `bangun/` | 99% |
| Kode aplikasi `src/` | 87 berkas, ±7.300 baris |
| Kode uji `tests/` | 58 berkas uji, ±15.000 baris |

**Live:** `https://simpul-desa-api-production.up.railway.app`
Langkah deploy, anggaran biaya, dan jebakan produksinya ada di
[DEPLOY.md](./DEPLOY.md).

## Mulai cepat

Prasyarat: Python 3.14. Contoh di bawah memakai venv di `.venv/`; sesuaikan
kalau venv Anda di tempat lain.

```bash
# 1. Dependensi (runtime + alat pengembangan)
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt

# 2. Konfigurasi lokal
cp .env.example .env          # lalu isi kunci yang diperlukan, lihat bagian Konfigurasi

# 3. Artefak data (±125 MB setelah dibongkar)
tar xzf data-salinan.tar.gz

# 4. Jalankan
.venv/bin/python -m uvicorn src.main:app --reload

# 5. Verifikasi
curl -s localhost:8000/health
```

`/health` membalas amplop berisi versi build data (`hash` + `tanggal` dari
`data-salinan/manifest.json`). Dokumentasi interaktif ada di
`localhost:8000/docs`, skemanya di `localhost:8000/openapi.json`; keduanya
bagian kontrak publik, bukan alat pengembangan yang boleh dimatikan di
produksi.

Tanpa `data-salinan/`, layanan tetap boot tetapi endpoint yang butuh artefak
membalas 503 `DATA_BELUM_SIAP`. Itu perilaku yang disengaja, bukan kegagalan
boot.

Perhatian saat memakai `/docs` dari sesi lokal: pemilih server di sana
berbawaan **produksi**, jadi pilih `http://localhost:8000` lebih dulu sebelum
memakai "Try it out" — kalau tidak, permintaannya menembak API produksi.

### Membangun ulang artefak data

`data-salinan.tar.gz` adalah hasil build yang ikut ter-commit, jadi
pengembangan sehari-hari tidak perlu membangun apa pun. Membangun ulang hanya
diperlukan saat data hulu berubah, dan itu butuh repo Data di-clone sebagai
folder tetangga bernama `data/`:

```bash
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python -m bangun          # menghasilkan data-salinan/ + manifest.json
```

Tahapan, bendera CLI, dan tata letak keluarannya ada di
[`bangun/README.md`](./bangun/README.md); cara menyegarkan tarball-nya ada di
[DEPLOY.md](./DEPLOY.md).

## Peta folder

```
api/
├── src/            paket aplikasi — satu folder per domain
├── bangun/         skrip build data-salinan/ (CLI: python -m bangun)
├── tests/          suite pytest, cermin struktur src/
├── harness/        eval Asisten Desa — MENYENTUH LLM sungguhan
├── supabase/       migrasi SQL; skema Supabase milik repo ini
├── data-salinan/   keluaran build (tidak ikut repo, 125 MB, regenerable)
├── Dockerfile      image runtime, dua tahap (bongkar arsip data, lalu layanan)
├── data-salinan.tar.gz  arsip artefak data (16 MB), SENGAJA ter-commit
└── DEPLOY.md       langkah deploy, anggaran memori, jebakan produksi
```

Lima subfolder punya README sendiri dengan detail yang tidak diulang di sini:
[`src/README.md`](./src/README.md), [`bangun/README.md`](./bangun/README.md),
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
konsekuensi yang diterima adalah preflight `OPTIONS` dijawab sebelum pembatas
laju.

### Alur satu permintaan baca

`GET /api/model/kartu/1801010001` menempuh: cek prefiks cache (kirim 304 bila
`If-None-Match` cocok) → validasi `iddesa` 10 digit di batas →
`kartu/service.py` membaca `data-salinan/kartu-ekonomi/kartu/1801.json` lewat
pembaca ber-LRU → `wajib()` melempar 503 `DATA_BELUM_SIAP` bila artefaknya
belum dibangun → 404 `DESA_TIDAK_ADA` bila `iddesa` tidak ada di berkas itu →
amplop sukses berstempel `ETag`.

### Penamaan berkas

Tiga tingkat, diterapkan berurutan: nama slot panduan fastapi-best-practices
menang bila slotnya ada (`router.py`, `service.py`, `schemas.py`,
`constants.py`, `dependencies.py`); berkas generik atau teknis tanpa nama
fitur memakai bahasa Inggris (`datastore.py`, `http_cache.py`, folder `auth/`,
`middleware/`); folder fitur produk memakai bahasa Indonesia dan namanya sama
dengan segmen URL yang menamai fitur itu (`citra_potensi/`, `peta_peran/`,
`desa_kembar/`). Tingkat ketiga mengikat dua arah — folder tidak boleh
diterjemahkan, dan segmen URL juga tidak.

## Rute

Rujukan lengkap per endpoint ada di `/docs` dan di situs dokumentasi.
Ringkasnya, dikelompokkan menurut akses minimum:

| Akses | Rute |
|---|---|
| Anonim | `GET /health` · `GET /api/wilayah/{provinsi,kabupaten,desa,ringkasan,pusat}` · `GET /api/desa/cari` · `GET /api/model/kartu/{iddesa}` · `GET /api/geo/desa/{idkab}` |
| Tamu | `GET /api/profil/saya` · `GET /api/model/peta-peran` (+ `/ringkasan`, `/{iddesa}`) · `GET /api/model/citra-potensi` (+ `/sel`) · `GET /api/model/jalur-ekonomi/{varian}` (+ `/{id_jalur}`) · `GET /api/model/desa-kembar/{iddesa}` · `GET /api/berita/{iddesa}` |
| Pemerintah / Swasta | `POST /api/chat` |
| Pemerintah | `GET /api/laporan/{iddesa}` |
| Admin | `POST /api/admin/berita/segarkan` · `DELETE /api/admin/berita/{id_berita}` · `GET /api/admin/pengguna` · `POST /api/admin/pengguna/{id_pengguna}/peran` · `GET /api/admin/status` |

`{varian}` ∈ `komoditas · gudang-kopdes · cold-storage · wisata`.

Tidak ada prefiks versi API. Paginasi seragam lewat `?hal=` (mulai 1, maksimum
10.000) dan `?batas=` (bawaan 50, maksimum 500). Batas atas `hal` ada supaya
nilai sangat besar tidak memaksa sumber data membuang jutaan baris sebelum
membalas halaman kosong.

`HEAD` hanya terdaftar pada `/health`, sengaja lewat dekorator terpisah dari
`@router.get` — `APIRoute` FastAPI tidak menambahkan `HEAD` otomatis, dan satu
rute dua metode membuat `operationId` bertabrakan di `/openapi.json`. Rute
lain sengaja GET saja.

### Tag dan server `/openapi.json`

Setiap operasi memakai tepat satu tag, dan **nama tag adalah nama tampil**
berbahasa Indonesia. Delapan di antaranya nama fitur produk (Peta Peran,
Kartu Ekonomi Desa, Jalur Ekonomi, Desa Kembar, Citra Potensi Desa, Asisten
Desa, Berita Desa, Laporan Desa), enam sisanya kelompok pendukung (Wilayah,
Pencarian Desa, Batas Desa, Kesehatan, Akun, Administrasi). Keempat belasnya
terdaftar berurut di `TAG_OPENAPI` pada [`src/main.py`](./src/main.py); urutan
itulah yang dipakai `/docs` dan sidebar situs dokumentasi, dan `description`
tiap tag menjadi isi halaman indeks kelompoknya di situs itu. Router domain
baru wajib mengambil salah satu nama di daftar itu; tanpa itu operasinya
mengapung tanpa grup.

`servers` juga diisi di `src/main.py` (`SERVER_OPENAPI`): produksi lebih dulu,
lalu `http://localhost:8000`. Contoh kode di situs dokumentasi dirakit dari
daftar ini, dan itulah sebabnya pemilih server di `/docs` berbawaan produksi.

Docstring handler rute, docstring model Pydantic, dan `description` tiap tag
semuanya **terbit sebagai teks publik** — FastAPI memakai seluruh docstring,
dan situs dokumentasi menampilkannya apa adanya. Karena itu teksnya hanya
memuat apa yang dikirim dan diterima klien, kapan galat mana muncul, dan
aturan yang mengikat klien; alasan internal ditulis sebagai komentar `#` di
atas dekorator atau kelasnya. Rute baru juga wajib membawa `summary=` dan
`response_description=`, dan `responses=RESPONS_VALIDASI` (`src/models.py`)
bila punya parameter atau badan permintaan — tanpa itu judul endpoint jatuh ke
nama fungsi Python dan deskripsi responsnya berbunyi "Successful Response".

## Amplop respons dan kode galat

Semua respons JSON memakai amplop seragam. Tiga keluaran sengaja di luar
amplop: geo (GeoJSON mentah ter-gzip), laporan (PDF), dan `/openapi.json` +
`/docs` bawaan FastAPI.

```json
{ "sukses": true,  "data": null, "galat": null, "meta": { "total": 0, "hal": 1, "batas": 50 } }
{ "sukses": false, "data": null, "galat": { "kode": "DESA_TIDAK_ADA", "pesan": "…" }, "meta": null }
```

`meta` hanya terisi pada respons berpaginasi; `POST /api/chat` selalu
ber-`meta: null` karena jejak fungsi, model penjawab, cacah putaran alat, dan
peringatan guardrail semuanya ada di dalam `data`.

Kode galat berbahasa Indonesia, UPPER_SNAKE_CASE, terdaftar di satu modul:
`src/exceptions.py`. Satu jebakan yang mengikat penambahan berikutnya: status
HTTP yang tidak terdaftar di `_KODE_PER_STATUS` jatuh ke `GALAT_SERVER`, jadi
galat klien baru yang muncul kelak harus ikut didaftarkan — kalau tidak, galat
klien dilaporkan sebagai galat server.

API mengirim angka JSON mentah. Pemformatan tampilan (koma desimal, titik
ribuan) sepenuhnya urusan sisi klien.

## Autentikasi dan peran

Autentikasi memakai Supabase: layanan memverifikasi JWT Supabase terhadap JWKS
proyek, lalu membaca peran dari kolom `profil.peran` lewat PostgREST. Tanpa
token = anonim. Empat peran sah: `tamu`, `pemerintah`, `swasta`, `admin`;
peran lebih tinggi mewarisi akses di bawahnya, dengan satu pengecualian —
laporan bukan hak swasta.

Penegakan terjadi di titik `include_router` pada `src/main.py`, bukan di dalam
tiap handler, sehingga satu router = satu gerbang peran. Satu pengecualian
yang disengaja: `GET /api/profil/saya` menegakkan akses di tanda tangan
handler, karena nilai `Identitas`-nya sekaligus menjadi isi respons. Himpunan
perannya konstanta di `src/auth/constants.py`.

Dua hal yang mudah salah dan sudah punya uji penjaga:

- `wajib_peran` mengembalikan `Identitas` (`id` + `peran`), bukan `str` —
  penjaga "admin tidak bisa mengubah peran sendiri" butuh `id` pemanggil.
- Nilai `peran` di luar empat peran sah membalas 403 `PERAN_TIDAK_DIKENAL`,
  bukan 503: basis data menjawab dengan benar, hanya nilainya yang asing.
  Nilai itu dan `id` penggunanya masuk log, tidak pernah ke pemanggil.

Kenaikan peran hanya lewat endpoint admin; registrasi mandiri selalu
menghasilkan `tamu`. Kolom `profil.email` adalah cermin `auth.users.email` dan
hanya untuk pencarian pengguna di halaman admin — otorisasi selalu dari kolom
`peran`, dan identitas selalu dari klaim `sub` token yang terverifikasi. Skema
Supabase dan migrasinya milik repo ini — lihat
[`supabase/README.md`](./supabase/README.md).

## Middleware

Tiga `BaseHTTPMiddleware` di `src/middleware/`, dan ketiganya memisahkan jalur
berdasarkan prefiks path. Prefiks dicocokkan PER SEGMEN (`path == p or
path.startswith(p + "/")`), bukan `startswith` polos — dengan `startswith`
polos, rute masa depan seperti `/api/model/kartu-interno` akan diam-diam
mewarisi ETag publik milik prefiks `/api/model/kartu`.

| Middleware | Berkas | Yang dilakukan |
|---|---|---|
| `MiddlewareCORS` | `cors.py` | `GET` pada prefiks publik dibuka ke semua origin; endpoint bertoken dan seluruh non-`GET` dibatasi ke origin dasbor |
| `MiddlewareBatasLaju` | `rate_limit.py` | ambang global per-IP (`LAJU_BAWAAN`), satu bucket per IP |
| `MiddlewareCacheHTTP` | `http_cache.py` | `ETag` (hash build) + `Cache-Control: public` + jawaban 304 pada prefiks data anonim; `no-store` pada prefiks bertoken |

Pemisahan prefiksnya:

| Himpunan | Isi |
|---|---|
| `PREFIKS_PUBLIK` (CORS terbuka) | `/health` · `/api/wilayah` · `/api/desa` · `/api/model/kartu` · `/api/geo` · `/openapi.json` · `/docs` |
| `PREFIKS_CACHE` (ETag + 304) | `/api/wilayah` · `/api/desa` · `/api/model/kartu` · `/api/geo` |
| `PREFIKS_TANPA_CACHE` (`no-store`) | `/api/model/peta-peran` · `/api/model/citra-potensi` · `/api/model/jalur-ekonomi` · `/api/model/desa-kembar` · `/api/berita` · `/api/profil` · `/api/admin` · `/api/laporan` · `/api/chat` |

Kenapa dipisah begitu: `Cache-Control: public` pada respons berotorisasi
membuat shared cache membocorkan body ke pemanggil lain, dan 304 dari
middleware dijawab SEBELUM dependensi auth berjalan. Keduanya temuan
keamanan berat yang sudah pernah terjadi di repo ini.

CORS menerima **satu** origin dan mencocokkannya persis — tanpa daftar, tanpa
pola, tanpa wildcard. Konsekuensinya, deployment preview dasbor (yang
mendapat URL unik setiap deploy) membuat seluruh rute bertoken dan non-`GET`
ditolak sementara `GET` publik tetap 200; gejalanya dasbor "setengah jalan",
dan penyebabnya satu variabel `ORIGIN_APP` di sisi API.

Pembatas laju TIDAK memakai `SlowAPIMiddleware` bawaan slowapi. Sejak FastAPI
0.141 `app.routes` berisi objek `_IncludedRouter` tanpa atribut `endpoint`,
lookup handler slowapi gagal, dan semua rute diam-diam lolos rate limit.
`MiddlewareBatasLaju` menggantikannya. Ambang `/api/chat` (`LAJU_CHAT`)
berlaku PER PENGGUNA lewat dekorator `@limiter.limit` di
`src/chat/router.py` dan berdampingan dengan ambang global per-IP — satu
permintaan chat dihitung di kedua bucket.

## Konfigurasi

Semua konfigurasi dari environment variable, dibaca `src/config.py` lewat
`pydantic-settings`; `.env` untuk pengembangan lokal dan tidak pernah
di-commit. Salin dari [`.env.example`](./.env.example), yang selalu dijaga
lengkap.

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

Dua hal yang gagal saat boot, bukan gagal saat dipakai, karena jalan pincang
lebih buruk daripada mati keras:

- `WEB_CONCURRENCY > 1` di luar `dev`. Gerbang "satu pekerjaan penyegaran pada
  satu waktu" (yang menjawab 409) menyimpan state di memori proses, jadi
  beberapa worker mengubahnya diam-diam menjadi satu pekerjaan PER worker —
  tiap worker bisa memanen sampai 50 desa sekaligus. Lock bersama sengaja
  ditolak untuk lingkup MVP.
- `ORIGIN_APP` non-https atau kredensial Supabase kosong di luar `dev`.

**Dua kunci Gemini terpisah, sengaja.** Panen Berita Desa dan Asisten Desa
memakai variabel berbeda. Satu penyegaran 50 desa bisa menghabiskan kuota
per-menit tepat saat pengguna sedang memakai chat, jadi kunci chat kosong
membalas 503 dan TIDAK PERNAH jatuh ke kunci berita.

## Data

Sumber data selalu salinan build dari keluaran repo Data; layanan ini tidak
pernah menghitung ulang apa pun yang sudah dihitung di sana, dan tidak pernah
menulis ke `data-salinan/` saat runtime.

`manifest.json` hasil build memuat asal, sha256, dan ukuran per artefak, plus
hash gabungan dan tanggal yang menjadi versi data di `/health` dan `ETag`.

Pemuatan runtime: `indeks.json` kartu dan berkas kecil dimuat sekali saat
start ke `app.state.simpanan`; berkas per kabupaten dibaca dari disk per
permintaan dengan cache LRU. Pilihan itu ada karena memori host produksi tidak
cukup untuk memuat semuanya.

Penjaga kontrak data yang mengikat semua endpoint — diuji, bukan diandaikan:

- Join berbasis `iddesa`, divalidasi di batas; 404 bila tidak dikenal.
- Koordinat placeholder yang menjangkiti data pariwisata hulu
  (`-6.2297465, 106.829518`) disaring dari semua respons wisata.
- Hasil pemodelan wisata tidak pernah tampil sebagai Skor Potensi.
- Kode wilayah klaim sumber eksternal tidak dipercaya — hanya kode yang sudah
  diverifikasi di hulu yang disajikan.
- Kolom mutu tidak pernah disaring dari respons: bendera keyakinan rendah,
  keadaan Belum Terpetakan, kode kosong, dan Sumber Potensi Dominan wajib ikut
  terkirim. Mutu harus terbaca.

Satu konsekuensi dari poin terakhir yang mudah dilanggar tanpa sadar: artefak
yang ADA tapi kehilangan kunci internal bukan hal yang sama dengan artefak
yang hilang. `muat_json_atau_none` sengaja tidak memvalidasi isi, jadi tiap
pemanggil harus memilih sikap dan menuliskan alasannya — kunci tingkat atas
hilang berarti 503 lewat `wajib()`, satu baris cacat berarti dilewati plus
`logger.warning`. Menambalnya dengan `.get()` berdefault pada kolom mutu
terlarang: `None` yang dikarang tidak bisa dibedakan pembaca dari nilai kosong
yang sah.

## Uji

```bash
.venv/bin/python -m pytest                    # seluruh suite + laporan cakupan
.venv/bin/python -m pytest tests/chat -q      # satu domain
.venv/bin/python -m pytest -k nama_uji        # satu uji
```

`pyproject.toml` mengunci `testpaths = ["tests"]` dan menyalakan
`--cov=src --cov=bangun --cov-report=term-missing` secara bawaan. Suite
berjalan tanpa jaringan: Supabase ditiru, Gemini ditiru, artefak dibangun di
`tmp_path`. Kalau suite tiba-tiba berjalan puluhan detik alih-alih di bawah
sepuluh detik, curigai tiruan yang terlepas — bukan mesin yang lambat.
Konvensi, fixture, dan daftar uji penjaga ada di
[`tests/README.md`](./tests/README.md).

`harness/` sengaja di LUAR `testpaths` karena ia menyentuh LLM sungguhan.
Melebarkan `testpaths` ke folder itu membuat `pytest` polos membakar kuota;
penjaganya `tests/chat/test_harness_terpisah.py`.

## Deploy

Satu service Docker di Railway, dideploy dari direktori lokal dengan
`railway up` — service ini sengaja TIDAK tersambung repo. Langkah,
verifikasi, anggaran biaya, dan jebakannya di [DEPLOY.md](./DEPLOY.md); di
sini hanya bentuk besarnya.

Artefak data TIDAK dibangun di sisi host. `python -m bangun` membaca folder
tetangga `data/` yang bukan bagian repo ini, jadi folder itu tidak pernah ada
di lingkungan build. Yang dikirim adalah `data-salinan.tar.gz` — 16 MB
terkompresi dari 125 MB, ikut ter-commit, dibongkar di tahap build terpisah
supaya arsipnya tidak tinggal di image jadi. Konsekuensinya: data produksi
hanya berubah kalau tarball-nya diperbarui dan di-commit.

```bash
railway up --detach -m "<ringkasan>"           # deploy
railway deployment list --json | head -40      # tunggu SUCCESS

docker build --platform linux/amd64 -t simpul-desa-api .   # uji image lokal
docker run --rm -p 8000:8000 -e LINGKUNGAN=dev simpul-desa-api
```

Karena `railway up` mendeploy WORKING TREE dan bukan commit, versi yang hidup
bisa berbeda dari isi git tanpa satu jejak pun. Periksa `git status` dan
`git rev-parse HEAD` vs `origin/main` sebelum menyebut produksi sama dengan
`main`.

Dua hal yang mengikat image dan tidak boleh dilepas:

- **`--proxy-headers` di `CMD`.** Tanpanya `request.client.host` selalu berisi
  IP proxy host, dan `get_remote_address` slowapi menaruh seluruh pemanggil
  dalam satu bucket `LAJU_BAWAAN` — satu pengunjung ramai membuat semua orang
  kena 429.
- **`maxsize` cache diturunkan lewat environment.** Muat `Simpanan` saat start
  terukur 164 MB, satu entri cache jalur ekonomi ±103 MB, satu entri kartu
  ±13 MB. Railway menagih pemakaian nyata, jadi ini sekaligus tombol biaya;
  nilai produksinya 4/1/4/8 dan perhitungannya di DEPLOY.md.

Versi di `requirements.txt` terpatok, jangan dilepas: repo ini sudah pernah
kehilangan seluruh rate limit tanpa satu galat pun gara-gara FastAPI naik
minor. Seluruh versi terpatok sudah diverifikasi punya wheel cp314 manylinux
x86_64 sehingga image tidak butuh compiler; menaikkan satu versi berarti
memeriksa ulang hal itu. Dependensi skrip build sengaja dipisah ke
`requirements-build.txt` dan TIDAK masuk image.

## Mutu kode

```bash
.venv/bin/python -m black src tests bangun harness
.venv/bin/python -m isort src tests bangun harness
.venv/bin/python -m ruff check src tests bangun harness
.venv/bin/python -m mypy src bangun
```

Keempatnya wajib. Ruff-saja ditolak karena membuang pemeriksaan tipe, yang
justru penjaga utama saat berkas dipindah antar modul. `mypy` berjalan dengan
`disallow_untyped_defs`, jadi setiap signature fungsi butuh anotasi.
Konfigurasi ketiganya di `pyproject.toml`.

## Peta dokumen repo ini

| Berkas | Isi |
|---|---|
| `README.md` | berkas ini — peta operasional |
| `DEPLOY.md` | deploy Railway: langkah, verifikasi, anggaran biaya dan memori, jebakan produksi |
| `src/README.md` | peta modul aplikasi + cara menambah domain baru |
| `bangun/README.md` | tahapan build, bendera CLI, tata letak keluaran |
| `tests/README.md` | menjalankan uji, fixture, konvensi, uji penjaga |
| `harness/README.md` | eval Asisten Desa dan rel kuotanya |
| `supabase/README.md` | migrasi SQL, replikasi ke proyek baru |
