# `src/` — paket aplikasi

Satu folder per domain, tiap folder memuat berkas bernama slot tetap. Tata
letaknya diputuskan [ADR-0008](../../docs/adr/0008-struktur-api-modular.md);
berkas ini hanya inventaris dan aturan kerjanya. Peta operasional folder
`api/` ada di [../README.md](../README.md); kontrak produknya di
`../PRD.md` (lokal saja).

## Berkas lintas domain

Berkas di akar paket dipakai lebih dari satu domain. Tidak ada logika
fitur di sini.

| Berkas | Isi |
|---|---|
| `main.py` | instansiasi FastAPI, lifespan, pemasangan middleware, `include_router` beserta gerbang perannya. Satu-satunya berkas yang disunting saat domain baru ditambahkan |
| `config.py` | `Pengaturan` (pydantic-settings) + validator yang menggagalkan boot pada konfigurasi rawan salah di luar `dev` |
| `models.py` | `ModelDasar` (induk seluruh model Pydantic), `Amplop`, `Meta`, `Galat`, plus pabrik `sukses()` / `gagal()` |
| `exceptions.py` | katalog kode galat, `GalatAPI`, dan `daftarkan_handler()` yang memasang seluruh exception handler |
| `datastore.py` | lapis data: `muat_manifest`, `Simpanan` startup, pembaca ber-LRU, dependensi `ambil_simpanan`, penjaga `wajib()` |
| `pagination.py` | `BATAS_BAWAAN` 50, `BATAS_MAKS` 500, `HAL_MAKS` 10.000, alias `ParamHal`/`ParamBatas`, dan `potong()` |
| `params.py` | pola regex kode wilayah (`POLA_IDPROV`, `POLA_IDKAB`, `POLA_IDDESA`) plus alias `ParamIddesa` |

`datastore.py` menempati slot `database.py` panduan fastapi-best-practices
tanpa memakai namanya, dan itu disengaja: tidak ada basis data di lapis ini.
Nama `database.py` akan menjanjikan koneksi atau ORM yang tidak pernah ada,
dan mengundang sesi berikutnya mencarinya di dalam sana.

Katalog kode galat tetap global di `exceptions.py` alih-alih dipecah ke
`<domain>/constants.py` — handler global memetakan status HTTP ke kode, dan
memecahnya akan melingkar dengan `auth/constants.py`.

## Domain

| Folder | Prefiks rute | Isi |
|---|---|---|
| `health/` | `/health` | liveness + versi build data. Satu-satunya rute yang mendaftarkan `HEAD` |
| `wilayah/` | `/api/wilayah` | provinsi, kabupaten, desa, ringkasan cakupan. `service.py`-nya juga penjaga wilayah yang dipakai tiga domain lain |
| `desa/` | `/api/desa/cari` | pencarian nama desa pada indeks kartu |
| `kartu/` | `/api/model/kartu` | satu Kartu Ekonomi Desa penuh, dibaca per kabupaten |
| `peta_peran/` | `/api/model/peta-peran` | baris zona + skor, detail per desa, agregat per kabupaten |
| `citra_potensi/` | `/api/model/citra-potensi` | metadata sel LAYAK dan skor per desa di satu sel |
| `jalur_ekonomi/` | `/api/model/jalur-ekonomi` | empat varian jalur (`komoditas`, `gudang-kopdes`, `cold-storage`, `wisata`) plus Desa Sejalur |
| `desa_kembar/` | `/api/model/desa-kembar` | tetangga precompute hasil `bangun/kembar.py` |
| `geo/` | `/api/geo` | GeoJSON batas desa per kabupaten, ter-gzip. Hanya `router.py` — tidak ada logika untuk dipisah |
| `berita/` | `/api/berita` | baca Berita Desa dari Supabase; `harvest/` memuat pemanennya |
| `chat/` | `/api/chat` | Asisten Desa: Gemini + pemanggilan fungsi, guardrail, delapan alat |
| `laporan/` | `/api/laporan` | Laporan Desa PDF (reportlab) |
| `admin/` | `/api/admin` | penyegaran berita, hapus berita, kelola peran, status sistem |
| `auth/` | — | verifikasi JWT Supabase, baca peran, dependensi gerbang peran |
| `middleware/` | — | CORS, pembatas laju, cache HTTP |

Nama folder domain fitur sama dengan segmen URL-nya, dan keduanya tidak
boleh diterjemahkan — istilahnya didefinisikan di
[../../GLOSSARY.md](../../GLOSSARY.md).

### Subfolder yang punya isi sendiri

`berita/harvest/` — pemanen RSS, enam berkas: `rss.py` (Google News RSS),
`decode.py` (buka URL pengalih Google), `content.py` (ambil isi halaman
penerbit), `filter.py` (saring topik ekonomi + rangkum), `store.py`
(tulis ke Supabase), `orchestrator.py` (`panen_desa`, penjaga anti-downgrade
rangkuman).

`chat/prompt/` — dua berkas Markdown, bukan Python: `asisten.md` (prompt
sistem) dan `metodologi.md` (bahan grounding jawaban metodologi). Nama
berkas prompt yang dipakai hidup di `app.state.nama_prompt_chat` supaya
`harness/` bisa membandingkan varian tanpa menyunting kode.

## Slot berkas

| Slot | Isi |
|---|---|
| `router.py` | definisi rute, validasi parameter di batas, susun amplop. Tidak memuat logika domain |
| `service.py` | logika domain: baca artefak, filter, agregasi, potong hasil |
| `schemas.py` | model respons Pydantic, semuanya turunan `ModelDasar` |
| `constants.py` | konstanta yang dipakai lebih dari satu berkas di domain itu |
| `dependencies.py` | dependensi FastAPI milik domain (hanya `auth/` yang punya) |

Slot yang tidak diperlukan tidak dibuat. `geo/` cukup `router.py`;
`kartu/` tidak punya `schemas.py` karena responsnya kartu apa adanya.

## Menambah satu domain

1. Buat folder `src/<nama>/` dengan `__init__.py` kosong, lalu `router.py`,
   `service.py`, dan `schemas.py` sesuai kebutuhan. Nama folder mengikuti
   aturan tiga tingkat ADR-0008.
2. Tulis ujinya lebih dulu di `tests/<nama>/` (TDD wajib, CLAUDE.md §6).
3. Tambahkan satu `include_router` di `src/main.py`, beserta
   `dependencies=[Depends(wajib_*)]` bila rutenya butuh peran. Penegakan
   peran ada di titik itu, bukan di dalam handler.
4. Kalau rutenya berotorisasi, tambahkan prefiksnya ke
   `PREFIKS_TANPA_CACHE` di `middleware/http_cache.py`. Prefiks yang lupa
   didaftarkan mewarisi `Cache-Control: public` dan jawaban 304 —
   membocorkan body berotorisasi ke shared cache.
5. Perbarui daftar rute PRD §5 dan tabel domain di berkas ini.

## Jebakan yang sudah terbukti di paket ini

Daftar lengkap beserta uji penjaganya ada di `../CLAUDE.md` (lokal saja)
§12. Yang paling mudah dilanggar saat menyunting `src/`:

- `auth/dependencies.py` memanggil service lewat objek modul, bukan
  `from ... import`. Diubah menjadi from-import, `monkeypatch.setattr`
  tidak lagi mengenainya dan seluruh uji auth tetap hijau sambil
  benar-benar memanggil JWKS serta PostgREST Supabase sungguhan.
- Dekorator `@limiter.limit` WAJIB di bawah `@router.post`, dan endpoint
  berdekorator itu wajib punya parameter `request: Request` DAN
  `response: Response`. Urutan terbalik mematikan ambang tanpa galat apa
  pun; `response` yang hilang meledakkan permintaan sukses pertama.
- Jangan `sed` buta atas kata "layanan". Kata itu muncul 206 kali di berkas
  `.py` dan hanya 134 di antaranya impor; sisanya kunci join
  `desa_layanan`/`n_desa_layanan` dan pesan galat publik.
- Pekerjaan latar admin memakai `asyncio.create_task` dengan objek `Task`
  disimpan di `app.state.tugas_penyegaran`, bukan `BackgroundTasks`. Tanpa
  referensi kuat, task yang sedang berjalan boleh dikumpulkan dan
  pekerjaannya hilang tanpa jejak.
