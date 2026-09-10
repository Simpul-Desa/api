# Deploy `api/` ke Railway

Layanan berjalan sebagai satu service Docker di Railway, dideploy dari
direktori lokal — bukan dari repo. Peta folder ada di [README.md](./README.md).

**Live:** `https://simpul-desa-api-production.up.railway.app`

| | |
|---|---|
| Project | `simpul-desa-api` · `0f2e654e-ce73-4263-b1b5-945c613af13d` |
| Service | `simpul-desa-api` · `a4fe5ee2-9e35-42d0-8fe1-d8d4f4f9089d` |
| Environment | `production` · `f9b3a922-b215-4d5b-be25-105382ef474f` |
| Region | asia-southeast1 (bawaan workspace) |
| Deploy pertama | 8 September 2026, `BUILDING → DEPLOYING → SUCCESS` dalam 35 detik |

## Kenapa dari direktori lokal, bukan dari repo

`railway up` mengarsipkan working tree, mengunggahnya, dan membangun
`Dockerfile` di sisi Railway. Service ini sengaja TIDAK tersambung repo —
`repoTriggers` kosong, bisa diperiksa sendiri:

```bash
railway api 'query($id: String!) { service(id: $id) { repoTriggers { edges { node { repository } } } } }' \
  --variables '{"id":"a4fe5ee2-9e35-42d0-8fe1-d8d4f4f9089d"}'
```

Tiga alasannya:

- Artefak data tidak bisa dibangun di sisi host. `python -m bangun` membaca
  `../data/`, yang bukan bagian repo `api/` ([ADR-0016](../docs/adr/0016-empat-repo-proyek-github-akar-lokal.md)),
  jadi folder itu tidak pernah ada di lingkungan build mana pun. Yang dipakai
  `data-salinan.tar.gz` (16 MB terkompresi dari 125 MB) yang ikut ter-commit —
  keputusannya di [ADR-0011](../docs/adr/0011-artefak-data-api-tarball-ter-commit.md).
- Tidak bergantung izin GitHub App di organisasi, dan tidak peduli repo privat
  atau publik.
- Riwayat commit folder ini padat dokumen. Auto-deploy on push berarti tiap
  commit `docs:` membangun ulang dan me-restart service — mengosongkan state
  pembatas laju in-memory dan membunuh pekerjaan penyegaran yang sedang
  berjalan, demi commit yang tidak menyentuh satu baris kode.

Yang ditukar: tidak ada auto-deploy, dan versi yang hidup bisa berbeda dari
isi git tanpa jejak. Produksi hanya bergerak kalau `railway up` dijalankan.

## Sekali saja, per mesin

```bash
brew install railway          # atau: npm i -g @railway/cli
railway login                 # membuka browser; sesi CLI terpisah dari login web
railway setup agent -y        # opsional: pasang MCP + skill Railway
```

`railway setup agent` menulis entri MCP ke `~/.claude.json` dan tidak menyentuh
`.mcp.json` proyek. Butuh CLI ≥5.44.0.

## Deploy

```bash
cd api/
railway up --detach -m "<ringkasan perubahan>"
```

`--detach` mengembalikan prompt setelah unggahan selesai. **Status `SUCCESS`
wajib diamati sebelum menyebut deploy berhasil** — keluar dengan kode 0 hanya
berarti unggahannya sampai:

```bash
railway deployment list --json | head -40
```

Yang diunggah dibatasi `.gitignore`, jadi `.venv/`, `data-salinan/` mentah
125 MB, cache alat, dan `.env` tidak ikut. `data-salinan.tar.gz` ikut karena
pola `data-salinan/` bergaris miring ekor hanya cocok dengan direktori.

## Menyegarkan data

Data di produksi hanya berubah lewat tarball baru. Menjalankan
`python -m bangun` di mesin sendiri tidak mengubah apa pun yang sudah hidup.

```bash
../.venv/bin/python -m bangun          # bangun ulang data-salinan/
rm -f data-salinan.tar.gz
tar --no-xattrs --no-mac-metadata --numeric-owner --uid 0 --gid 0 \
    -czf data-salinan.tar.gz data-salinan
# Linux (GNU tar): tar --numeric-owner --owner=0 --group=0 -czf data-salinan.tar.gz data-salinan
tar tzf data-salinan.tar.gz | wc -l   # 380 entri
railway up --detach -m "segarkan artefak data"
```

`--no-xattrs --no-mac-metadata` bukan hiasan: tanpa keduanya arsip dari macOS
membawa atribut `com.apple.provenance`, dan `tar` di dalam image Linux
memuntahkan satu baris `Ignoring unknown extended header keyword` per berkas —
364 baris peringatan di setiap log build.

Verifikasi tarball benar-benar naik: `/health` menyajikan `versi_data` (hash
manifest) dan `tanggal_data`. Bandingkan dengan `data-salinan/manifest.json`
lokal. `versi_data` kosong berarti arsipnya tidak sampai ke image.

## Variabel environment

21 variabel, tersimpan di Railway. Sumber lokalnya `.env.deploy` (gitignored,
izin 600) — bukan berkas yang dibaca aplikasi, hanya bahan untuk menyetel.

```bash
railway variable list --service simpul-desa-api --json
railway variable set KUNCI=nilai --service simpul-desa-api --skip-deploys
```

**Pakai `--skip-deploys`** saat menyetel banyak variabel sekaligus. Tanpanya
setiap `set` memicu satu deploy — 21 variabel jadi 21 deploy.

Tiga nilai yang berbeda dari `.env.example` bawaan pengembangan:

| Variabel | Produksi | Kenapa |
|---|---|---|
| `LINGKUNGAN` | `produksi` | menyalakan validator boot: ORIGIN_APP wajib https, kredensial Supabase wajib terisi, `WEB_CONCURRENCY` wajib 1 |
| `MAKS_CACHE_KARTU/JALUR/CITRA/KEMBAR` | `4` / `1` / `4` / `8` | bawaan 16/4/16/16 menembus 700 MB; lihat Anggaran memori |
| `ORIGIN_APP` | domain dasbor | lihat Menyambungkan dasbor |

## Verifikasi

```bash
BASIS=https://simpul-desa-api-production.up.railway.app

curl -s $BASIS/health
curl -s $BASIS/api/wilayah/ringkasan
curl -s -D - -o /dev/null $BASIS/api/model/kartu/1801040001 | grep -iE 'etag|cache-control'
curl -s -o /dev/null -w '%{http_code}\n' $BASIS/api/model/peta-peran
```

Hasil yang benar, terukur pada deploy 8 September 2026:

| Cek | Harapan |
|---|---|
| `/health` | 200 · `versi_data` `c5cbcb06e251…` · `tanggal_data` `2026-09-07` |
| `/api/wilayah/ringkasan` | 200 · 5 provinsi, 97 kabupaten, 17.467 desa |
| kartu | 200 · `etag` = hash build · `cache-control: public, max-age=3600` |
| kartu + `If-None-Match` | 304 |
| `/api/model/peta-peran` tanpa token | **401**, bukan 503 |
| amplop galat (`iddesa` ngawur) | 404 · `{"sukses":false,…"kode":"DESA_TIDAK_ADA"…}` |
| `DELETE /health` | 405 |
| header rate limit | `x-ratelimit-limit: 120`, `remaining` menurun |
| CORS `GET` publik | `access-control-allow-origin: *` |
| `/openapi.json`, `HEAD /health` | 200 |

**401 pada rute bertoken adalah cek terpenting.** Itu bukti kredensial
Supabase terbaca dan gerbang peran hidup. **503** di situ berarti `SUPABASE_URL`
atau `SUPABASE_SERVICE_ROLE_KEY` tidak sampai.

## Anggaran memori dan biaya

Railway menagih pemakaian nyata, bukan alokasi — jadi tuning cache LRU
langsung jadi penghematan uang. Tarifnya RAM $10/GB/bulan, CPU
$20/vCPU/bulan, egress $0,05/GB.

| Komponen | Terukur | Biaya/bulan |
|---|---|---|
| Muat `Simpanan` saat start | 164 MB | — |
| RAM idle setelah rute anonim | 171 MiB = 0,167 GB | $1,67 |
| RAM puncak dengan `MAKS_CACHE_*` produksi | ±330 MB = 0,322 GB | $3,22 |
| CPU, API baca-saja | ±0,03 vCPU | $0,60 |
| Egress, misal 1 GB JSON | | $0,05 |

Rentang realistis **$2,30–$3,90 per bulan**.

Perbandingannya tidak linear terhadap ukuran berkas: `hasil_komoditas.json`
15,6 MB di disk menjadi ±103 MB objek Python — tujuh kali. Satu entri kartu
kabupaten 1,9 MB menjadi ±13 MB. Itu sebabnya `MAKS_CACHE_JALUR` diturunkan
ke 1. Nol dan negatif ditolak saat boot: `lru_cache` membaca keduanya sebagai
"tanpa cache", yang membuat setiap permintaan mem-parse ulang berkas 15,6 MB.

**Trial $5 berlaku 30 hari, sekali.** Sesudahnya Free plan memberi $1 kredit
per bulan — sekitar sepuluh hari layanan ini. Kalau kredit habis, Railway
menghentikan seluruh workload. Pantau tab Usage; kalau lebih cepat dari
perkiraan, turunkan `MAKS_CACHE_*` ke 2/1/2/4 (puncak ±250 MB).

## Menyambungkan dasbor `app/`

Dasbor Next.js dideploy terpisah (Vercel). Dua kabel yang harus disambung,
keduanya tanpa build ulang di sisi API:

```bash
# 1. di app/ — basis URL API
NEXT_PUBLIC_API_BASE=https://simpul-desa-api-production.up.railway.app

# 2. di api/ — origin yang diizinkan untuk non-GET dan rute bertoken
railway variable set ORIGIN_APP=https://<domain-dasbor> --service simpul-desa-api
```

`ORIGIN_APP` sekarang masih menunjuk domain API sendiri — nilai sementara
supaya boot lolos dan verifikasi curl jalan (CORS hanya berlaku untuk browser).

Lewatkan langkah 2 dan dasbornya **setengah jalan**: wilayah, cari desa,
kartu, dan geo tampil normal karena `GET` pada prefiks publik dibuka ke semua
origin (`*`), sementara chat, laporan, admin, dan seluruh rute bertoken
diblokir CORS. Gejalanya menyesatkan — sebagian halaman hidup, sebagian mati,
dan penyebabnya satu variabel di sisi API.

## Jebakan

- **`--proxy-headers` di `CMD` Dockerfile wajib.** Di belakang proxy Railway,
  tanpa `--proxy-headers --forwarded-allow-ips='*'` nilai
  `request.client.host` selalu IP proxy, dan `get_remote_address` slowapi
  menaruh SELURUH pemanggil dalam satu bucket `LAJU_BAWAAN` — satu pengunjung
  ramai membuat semua orang kena 429. Konsekuensi yang diterima:
  `X-Forwarded-For` bisa dipalsukan, jadi ambang per-IP adalah pertahanan
  terbaik-usaha. Jangan mengisi field Custom Start Command di dashboard; itu
  menimpa `CMD` dan membuang kedua bendera ini.
- **`WEB_CONCURRENCY` harus tetap 1.** Gerbang "satu pekerjaan penyegaran pada
  satu waktu" menyimpan state di memori proses; lebih dari satu worker
  mengubahnya diam-diam menjadi satu pekerjaan per worker, dan tiap worker
  bisa memanen sampai 50 desa sekaligus
  ([ADR-0010](../docs/adr/0010-api-satu-proses-bukan-lock-bersama.md)). Boot
  gagal bila nilainya lebih dari 1 di luar `dev`.
- **CORS menerima SATU origin, cocok persis.** `_origin_diizinkan` di
  `src/middleware/cors.py` membandingkan `origin == pengaturan.origin_app` —
  tanpa daftar, tanpa pola. Preview deployment Vercel mendapat URL unik tiap
  deploy, jadi rute bertoken selalu ditolak di preview. Uji autentikasi hanya
  di domain produksi, atau ubah middleware untuk menerima daftar origin —
  yang kedua mengubah jaminan CORS PRD §3 dan perlu diketok dulu.
- **Penyegaran berita adalah pekerjaan berjam-jam.** `POST
  /api/admin/berita/segarkan` untuk satu desa berisi 10 artikel terukur 3
  menit 37 detik; batasnya 50 desa per permintaan. Rutenya membalas 202 dan
  bekerja di latar. Deploy baru me-restart proses dan membunuh pekerjaan yang
  sedang berjalan.
- **Restart mengosongkan state rate limit dan pekerjaan latar.** Keduanya
  in-memory; tiap `railway up` mengosongkannya. Disengaja untuk MVP.
- **`.env` tidak pernah ikut terunggah** karena diabaikan `.gitignore`. Semua
  konfigurasi produksi datang dari variabel Railway. Catatan sebaliknya: kalau
  `.env` dikeluarkan dari `.gitignore`, ia akan ikut masuk konteks build.
- **Versi dependensi terpatok** di `requirements.txt`. Jangan melepasnya:
  proyek ini sudah pernah kehilangan seluruh rate limit tanpa satu galat pun
  gara-gara FastAPI naik ke 0.141 (CLAUDE.md §12). Seluruh versi terpatok
  sudah diverifikasi punya wheel cp314 manylinux x86_64, jadi image tidak
  butuh compiler; menaikkan satu versi berarti memeriksa ulang hal itu:
  `pip download --only-binary=:all: --platform manylinux2014_x86_64
  --python-version 3.14 --abi cp314 --implementation cp -r requirements.txt`.

## Yang sengaja tidak dipakai

- **Service tersambung repo GitHub.** Alasannya di bagian pertama. Bisa
  disambungkan belakangan (Service → Settings → Source → Connect Repo) tanpa
  membuang apa pun; sejak itu `railway up` tidak lagi diperlukan.
- **Build data di sisi host.** `../data/` tidak ada di lingkungan build.
- **Registry image (GHCR/Docker Hub).** `railway up` membangun langsung dari
  konteks lokal; registry menambah satu langkah push manual tiap kali data
  berubah.
- **Persistent disk.** Layanan tidak pernah menulis ke disk saat runtime — PDF
  dirakit di `io.BytesIO`.
- **Redis / Key Value untuk rate limit dan lock pekerjaan.** Butuh keputusan
  skema tersendiri; ADR-0010 menetapkan satu proses untuk MVP.
