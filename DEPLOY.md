# Deploy `api/` ke Render

Layanan berjalan sebagai satu web service Docker di Render. Blueprint-nya
[`render.yaml`](./render.yaml), image-nya [`Dockerfile`](./Dockerfile).
Peta folder ada di [README.md](./README.md); kontrak produk di
`PRD.md` (lokal saja).

Terverifikasi lokal 8 September 2026: image `linux/amd64` dibangun, dijalankan,
dan disentuh — `/health`, `/api/wilayah/ringkasan`, `/api/model/kartu/{iddesa}`
(dengan `ETag` + 304), dan `/openapi.json` semuanya 200; rute bertoken 503
karena Supabase belum disetel, sesuai desain.

## Kenapa data tidak dibangun di Render

`python -m bangun` membaca `../data/`. Folder itu **bukan** bagian repo ini —
`api/` repo tersendiri ([ADR-0009](../docs/adr/0009-dua-repo-git-akar-dan-api.md)) —
jadi begitu repo ini di-clone Render, `../data/` tidak ada. Membiarkan build
mencoba jalan berarti layanan boot dengan semua endpoint membalas 503
`DATA_BELUM_SIAP`.

Karena itu artefaknya dikirim sebagai **`data-salinan.tar.gz` yang ikut
ter-commit**: 16 MB terkompresi (dari 125 MB, 364 berkas), jauh di bawah batas
berkas GitHub. `Dockerfile` membongkarnya di tahap build terpisah supaya
arsipnya tidak tinggal di image jadi. Keputusan itu beserta lima alternatif
yang ditolak — build di sisi Render, commit folder mentah, aset GitHub
Release, registry image, dan Git LFS — tercatat di
[ADR-0011](../docs/adr/0011-artefak-data-api-tarball-ter-commit.md).

Konsekuensinya, dan ini yang paling mudah lupa: **data di produksi hanya
berubah kalau tarball-nya diperbarui dan di-commit.** Menjalankan
`python -m bangun` di mesin sendiri tidak mengubah apa pun di Render.

## Prasyarat

- Repo `api/` sudah ada di GitHub (atau GitLab/Bitbucket) dan bisa diakses akun
  Render.
- Proyek Supabase sudah berjalan dengan kedelapan migrasi terpasang — lihat
  [`supabase/README.md`](./supabase/README.md).
- Dua kunci Gemini: satu untuk panen Berita Desa, satu untuk Asisten Desa.
- Docker lokal, hanya bila mau menguji image sebelum push.

## Langkah

### 1. Segarkan arsip data

Jalankan dari `api/`, setiap kali keluaran `../data/` berubah:

```bash
../.venv/bin/python -m bangun          # bangun ulang data-salinan/
rm -f data-salinan.tar.gz
# macOS (bsdtar):
tar --no-xattrs --no-mac-metadata --numeric-owner --uid 0 --gid 0 \
    -czf data-salinan.tar.gz data-salinan
# Linux (GNU tar):
# tar --numeric-owner --owner=0 --group=0 -czf data-salinan.tar.gz data-salinan
```

`--no-xattrs --no-mac-metadata` bukan hiasan: tanpa keduanya arsip dari macOS
membawa atribut `com.apple.provenance`, dan `tar` di dalam image Linux
memuntahkan satu baris `Ignoring unknown extended header keyword` per berkas —
364 baris peringatan di log build setiap kali.

Verifikasi sebelum commit:

```bash
tar tzf data-salinan.tar.gz | wc -l    # harus 379 entri
ls -lh data-salinan.tar.gz             # ±16 MB
```

### 2. Uji image di lokal (opsional, disarankan)

```bash
docker build --platform linux/amd64 -t simpul-desa-api .
docker run --rm -p 8000:8000 -e LINGKUNGAN=dev simpul-desa-api
curl -s localhost:8000/health
```

`--platform linux/amd64` penting di Mac Apple Silicon: Render menjalankan
amd64, dan membangun arm64 saja menyembunyikan masalah ketersediaan wheel.
`LINGKUNGAN=dev` dipakai supaya boot tidak menuntut kredensial Supabase —
untuk sekadar membuktikan image hidup dan data terbaca.

### 3. Push, lalu pasang blueprint

```bash
git add data-salinan.tar.gz Dockerfile .dockerignore render.yaml DEPLOY.md \
        requirements.txt requirements-build.txt
git commit -m "chore: artefak deployment Render"
git push -u origin <cabang>
```

Di Dashboard Render: **New → Blueprint**, pilih repo ini. Render membaca
`render.yaml` dan meminta lima nilai yang sengaja tidak ada di repo:

| Variabel | Isi |
|---|---|
| `ORIGIN_APP` | URL **https** dasbor `app/`, tanpa garis miring ekor. Ini satu-satunya origin yang boleh mengirim non-`GET` dan memakai endpoint bertoken |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co`, tanpa garis miring ekor |
| `SUPABASE_SERVICE_ROLE_KEY` | kunci service role (Settings → API). Rahasia sisi server |
| `GEMINI_API_KEY` | kunci panen Berita Desa |
| `GEMINI_API_KEY_CHAT` | kunci Asisten Desa. **Harus berbeda** dari yang di atas |

Kelimanya wajib terisi sebelum deploy pertama. `render.yaml` menyetel
`LINGKUNGAN=produksi`, dan di luar `dev` boot **gagal keras** bila
`ORIGIN_APP` bukan https atau kredensial Supabase kosong (`src/config.py`).
Itu disengaja: layanan yang jalan pincang dengan CORS mempercayai localhost
lebih buruk daripada layanan yang menolak start.

### 4. Verifikasi

```bash
BASIS=https://<nama-service>.onrender.com
curl -s $BASIS/health
curl -s $BASIS/api/wilayah/ringkasan
curl -sI $BASIS/api/model/kartu/1801040001 | grep -iE 'etag|cache-control'
```

Yang harus terlihat:

- `/health` membalas `versi_data` (hash manifest) dan `tanggal_data`. Kalau
  keduanya kosong, arsip data tidak sampai ke image.
- `/api/wilayah/ringkasan` melaporkan 5 provinsi, 97 kabupaten, 17.467 desa.
- Rute kartu membawa `ETag` dan `Cache-Control: public, max-age=3600`.
- Rute bertoken (`/api/model/peta-peran`) membalas 401 tanpa token, bukan 503.
  503 di situ berarti kredensial Supabase belum terbaca.
- `$BASIS/docs` terbuka — bagian kontrak publik menurut PRD bagian 3, sengaja
  tidak disembunyikan di produksi.

### 5. Sambungkan dasbor

Setel basis URL API di `../app/` ke `$BASIS`, dan pastikan `ORIGIN_APP` di
Render sama persis dengan origin dasbor. Cocokkan skema, host, dan port —
`_cocok_publik` di `src/middleware/cors.py` membandingkan origin secara tepat,
bukan per pola.

## Anggaran memori

Instance 512 MB tidak muat kalau cache dibiarkan seagresif bawaan
pengembangan. Angka terukur di mesin ini:

| Komponen | Terukur |
|---|---|
| Muat `Simpanan` saat start | 164 MB |
| Container idle setelah menyentuh rute anonim | 171 MiB |
| Satu entri cache jalur ekonomi (`hasil_komoditas.json`, 15,6 MB di disk) | ±103 MB |
| Satu entri cache kartu kabupaten (1,9 MB di disk) | ±13 MB |
| Satu entri cache citra potensi / desa kembar | jauh di bawah 1 MB |

Perbandingannya bukan linear terhadap ukuran berkas: JSON 15,6 MB menjadi
objek Python ±103 MB, sekitar tujuh kali. Itu sebabnya `maxsize` empat cache
dijadikan variabel environment (`MAKS_CACHE_KARTU`, `MAKS_CACHE_JALUR`,
`MAKS_CACHE_CITRA`, `MAKS_CACHE_KEMBAR`) dan diturunkan di `render.yaml`:

| Variabel | Bawaan dev | `render.yaml` | Beban puncak di produksi |
|---|---|---|---|
| `MAKS_CACHE_JALUR` | 4 | 1 | ±103 MB |
| `MAKS_CACHE_KARTU` | 16 | 4 | ±52 MB |
| `MAKS_CACHE_CITRA` | 16 | 4 | beberapa MB |
| `MAKS_CACHE_KEMBAR` | 16 | 8 | beberapa MB |

Total puncak ±330 MB dari 512 MB — sisa ±180 MB untuk lonjakan permintaan dan
perakitan PDF. Dengan bawaan pengembangan, angka yang sama menembus 700 MB dan
instance dimatikan OOM tanpa satu baris log dari aplikasi.

Nilai 0 dan negatif ditolak saat boot: `lru_cache` membaca keduanya sebagai
"tanpa cache", yang membuat setiap permintaan mem-parse ulang berkas 15,6 MB —
kegagalan performa senyap, bukan galat.

## Plan dan region

`render.yaml` memakai `plan: free` dan `region: singapore`.

- **`free`** ikut spin-down setelah menganggur. Permintaan pertama sesudahnya
  menunggu cold start: tarik image, boot uvicorn, muat `Simpanan` 164 MB.
  Untuk demo berjuri, naikkan ke **`starter`** — RAM-nya sama 512 MB, yang
  hilang hanya spin-down-nya.
- **`singapore`** region terdekat ke Indonesia. Ganti hanya sebelum service
  dibuat; region tidak bisa dipindah setelahnya.

## Jebakan

- **`--proxy-headers` wajib.** Ada di `CMD` `Dockerfile`. Tanpanya
  `request.client.host` selalu berisi IP proxy Render, dan
  `get_remote_address` slowapi menaruh SELURUH pemanggil dalam satu bucket
  `LAJU_BAWAAN` — satu pengunjung ramai membuat semua orang kena 429.
  Konsekuensi yang diterima: `X-Forwarded-For` bisa dipalsukan, jadi ambang
  per-IP adalah pertahanan terbaik-usaha, bukan jaminan.
- **`WEB_CONCURRENCY` harus tetap 1.** Gerbang "satu pekerjaan penyegaran pada
  satu waktu" (yang menjawab 409) menyimpan state di memori proses. Lebih dari
  satu worker mengubahnya diam-diam menjadi satu pekerjaan **per worker**, dan
  tiap worker bisa memanen sampai 50 desa sekaligus
  ([ADR-0010](../docs/adr/0010-api-satu-proses-bukan-lock-bersama.md)). Boot
  gagal bila nilainya lebih dari 1 di luar `dev`.
- **Penyegaran berita adalah pekerjaan berjam-jam.** `POST
  /api/admin/berita/segarkan` untuk satu desa berisi 10 artikel terukur 3 menit
  37 detik. Untuk 50 desa, jangan berharap selesai sebelum request timeout —
  rutenya memang membalas 202 dan bekerja di latar. Di instance `free`,
  spin-down saat menganggur bisa memotong pekerjaan latar yang masih berjalan.
- **Restart menghapus state rate limit dan pekerjaan latar.** Keduanya
  in-memory; tiap deploy mengosongkannya. Disengaja untuk MVP.
- **`.env` tidak pernah masuk image.** Dikecualikan `.dockerignore`. Semua
  konfigurasi produksi datang dari environment variable Render.
- **Versi dependensi terpatok** di `requirements.txt`. Jangan melepasnya untuk
  "biar dapat versi terbaru": proyek ini sudah pernah kehilangan seluruh rate
  limit tanpa satu galat pun gara-gara FastAPI naik ke 0.141 (CLAUDE.md bagian
  12). Seluruh versi terpatok punya wheel cp314 manylinux x86_64, jadi image
  tidak butuh compiler; menaikkan satu versi berarti memeriksa ulang hal itu.

## Yang sengaja tidak dipakai

- **Build data di Render.** `../data/` tidak ada di repo ini; lihat bagian
  pertama.
- **Registry image (GHCR/Docker Hub).** Blueprint membangun langsung dari repo;
  registry menambah satu langkah push manual tiap kali data berubah.
- **Aset GitHub Release.** Memindahkan artefak ke luar versi membuat satu
  commit tidak lagi menggambarkan dirinya sendiri.
- **Git LFS untuk arsip data.** 16 MB muat dalam batas Git biasa; LFS menambah
  ketergantungan pada dukungan LFS di sisi build Render.

Alasan penolakan empat yang pertama — build di sisi Render, registry image,
aset GitHub Release, Git LFS — ada di
[ADR-0011](../docs/adr/0011-artefak-data-api-tarball-ter-commit.md), bersama
satu alternatif kelima yang tidak muncul di daftar ini (commit
`data-salinan/` mentah).
- **Persistent disk.** Layanan tidak pernah menulis ke disk saat runtime.
- **Redis / Key Value untuk rate limit dan lock pekerjaan.** Butuh keputusan
  skema tersendiri; ADR-0010 menetapkan satu proses untuk MVP.
