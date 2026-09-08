# `tests/` — suite pytest

702 uji, 55 berkas, berjalan sekitar 7 detik tanpa menyentuh jaringan sama
sekali. Struktur folder mencerminkan `../src/`: satu folder uji per domain.
Peta operasional folder `api/` ada di [../README.md](../README.md); aturan
uji sebagai kebijakan ada di `../CLAUDE.md` §6 (lokal saja) dan
`.claude/rules/ecc/python/testing.md`.

## Menjalankan

```bash
cd api/
../.venv/bin/python -m pytest                      # seluruh suite + laporan cakupan
../.venv/bin/python -m pytest tests/chat -q        # satu domain
../.venv/bin/python -m pytest -k nama_uji          # satu uji
../.venv/bin/python -m pytest --no-cov -q          # tanpa laporan cakupan (lebih cepat)
```

`pyproject.toml` sudah menyalakan `--cov=src --cov=bangun
--cov-report=term-missing`, jadi `pytest` polos langsung mencetak cakupan.
`testpaths = ["tests"]` juga dikunci di sana — jangan dilebarkan, lihat
bagian Kuota di bawah.

Cakupan sekarang 99% (target PRD §10 ≥80%).

## Tata letak

| Folder | Uji | Isi |
|---|---|---|
| `tests/` (akar) | 53 | `test_config.py`, `test_datastore.py`, `test_exceptions.py`, `test_models.py`, `test_pagination.py` — berkas lintas domain |
| `chat/` | 150 | guardrail, LLM, alat, router, batas laju per pengguna, penilai harness |
| `auth/` | 112 | verifikasi token, baca peran, matriks akses tiap sel PRD |
| `admin/` | 78 | penyegaran, hapus berita, kelola peran, status, pekerjaan latar |
| `berita/` + `berita/harvest/` | 8 + 48 | rute baca plus enam modul pemanen |
| `middleware/` | 46 | CORS, cache HTTP, pembatas laju |
| `laporan/` | 46 | perakit ringkasan, PDF, rute, skema |
| `jalur_ekonomi/` | 38 | empat varian, paginasi, filter |
| `bangun/` | 30 | lima modul build plus orkestrasi CLI |
| `peta_peran/` | 22 | daftar, detail, ringkasan kabupaten |
| `wilayah/` · `desa_kembar/` · `citra_potensi/` · `kartu/` · `desa/` · `health/` · `geo/` | 15 · 14 · 14 · 11 · 9 · 4 · 4 | endpoint baca per domain |

## Fixture bersama

Semuanya di `conftest.py` akar kecuali yang disebut lain.

| Fixture | Isi |
|---|---|
| `buat_klien` | pabrik `httpx.AsyncClient` ber-`ASGITransport`; parameter `lifespan` dan `lempar_galat_app` menggantikan perilaku `TestClient` |
| `aplikasi` | `create_app()` dengan `wajib_tamu` di-override menjadi tamu. Dipisah dari `klien` supaya uji bisa menyentuh `app.state` |
| `klien` | klien atas `aplikasi` dengan lifespan aktif |
| `dir_data_manifest` | `DIR_DATA` menunjuk `tmp_path` berisi `manifest.json` saja |
| `dir_data_lengkap` | `data-salinan/` sintetis mini: 1 provinsi, 2 kabupaten, 6 desa, seluruh jenis artefak yang dipakai router baca |
| `kunci_es256` | pasangan kunci ES256 khusus uji (scope sesi) |
| `buat_token` | pabrik JWT ES256 uji dengan klaim yang bisa diatur |
| `env_admin` | (di `admin/conftest.py`) isi env Supabase + Gemini uji, lalu bersihkan cache pengaturan |

Fungsi pembantu yang bukan fixture tinggal di `bantu.py` per folder
(`admin/bantu.py`, `auth/bantu.py`). Pemisahan itu disengaja: fixture yang
diimpor dari modul biasa hanya dikenali pytest bila namanya ikut terimpor ke
berkas uji, dan impor itu terbaca sebagai impor tak terpakai oleh ruff.

## Konvensi yang mengikat

**Urutan fixture penting.** `dir_data_manifest` dan `dir_data_lengkap`
harus dicantumkan SEBELUM `klien` pada signature uji. `create_app()`
membaca `DIR_DATA` saat dipanggil, jadi urutan terbalik membuat aplikasi
memuat `Simpanan` dari direktori yang salah.

**Jangan kembali ke `TestClient`.** Starlette 1.6 mendeprekasi jalur
`httpx` di `starlette.testclient` ("Using `httpx` with
`starlette.testclient` is deprecated; install `httpx2` instead"), sementara
`../src/` memakai httpx 0.28 untuk PostgREST dan panen berita. Fixture
`buat_klien` menghindari jalur terdeprekasi itu tanpa memasukkan mayor
httpx kedua ke venv bersama. Catatan: `ASGITransport` TIDAK memotong badan
respons `HEAD` seperti h11 di balik uvicorn — jangan menegaskan badan
kosong dari uji.

**Override `dependency_overrides` harus lengkap.** `wajib_peran`
mengembalikan `Identitas` (`id` + `peran`), bukan `str`, dan override untuk
`wajib_di_atas_tamu` juga harus menulis `request.state.identitas` — tanpa
itu `kunci_pengguna` jatuh ke sentinel dan bucket rate limit dua pengguna
berbeda menyatu tanpa gejala.

**Uji `maxsize` LRU harus lewat proses terpisah.** `maxsize` keempat cache
pembaca dibaca dari `Pengaturan` saat modul service diimpor. Di dalam proses
pytest, modulnya sudah lama terimpor sebelum `monkeypatch.setenv` berjalan,
jadi uji yang menyetel env lalu memeriksa `cache_info().maxsize` akan LOLOS
tanpa membuktikan apa pun. `test_maks_cache_env_sampai_ke_lru_cache_di_proses_baru`
karena itu memakai `subprocess`.

**Kartu sintetis `dir_data_lengkap` tidak lengkap seperti data nyata** — ia
hanya memuat `identitas`, `peta_peran`, dan `mutu_data`, tanpa `potensi`,
`kesiapan`, `logistik`, `desa_kembar`, `fakta_program`, `rekomendasi_aksi`,
dan tanpa `lon`/`lat`/`luas_km2`/`kode_dagri`. Kode yang mengonsumsi kartu
wajib memakai rantai `.get(...)`, bukan indeks langsung; kalau tidak, uji
integrasi hijau sementara data nyata jalan lewat cabang yang tak pernah
diuji.

## Kuota: jangan sampai suite membakar kredit

Suite ini tidak boleh menyentuh Gemini, Supabase, atau situs berita
sungguhan. Tiga hal yang menahannya, dan ketiganya pernah bocor:

- **`testpaths = ["tests"]`** adalah satu-satunya yang menahan `pytest`
  polos dari menjalankan `../harness/`, yang memanggil Gemini sungguhan.
  Penjaganya `chat/test_harness_terpisah.py`.
- **`_lifespan` tidak boleh menugaskan `app.state.layanan_ai` tanpa
  syarat.** Penugasan tanpa syarat membuang `LayananPalsu` yang dipasang
  uji, dan suite diam-diam memanggil Gemini sungguhan — terjadi 8 September
  2026, menabrak 429 RESOURCE_EXHAUSTED, dengan satu-satunya gejala suite
  berjalan 136 detik alih-alih di bawah 1 detik. Kalau suite tiba-tiba
  lambat, curigai tiruan yang terlepas, bukan mesinnya.
- **`POST /api/admin/berita/segarkan` dengan body sah memicu panen
  NYATA** — Google News RSS, pengambilan halaman penerbit, dan panggilan
  Gemini; terukur 3 menit 37 detik untuk satu desa berisi 10 artikel.
  Kirim tanpa body (422 sudah membuktikan gerbang peran) atau tambal
  `src.admin.jobs.panen_desa` lebih dulu.

## Uji penjaga

Uji berikut ada bukan untuk menguji fitur, melainkan untuk menahan satu
kesalahan spesifik yang sudah pernah terjadi dan tidak menghasilkan gejala
apa pun. Menghapus atau melemahkannya berarti membuka lagi cacat yang
sudah dibayar. Alasan tiap-tiapnya di `../CLAUDE.md` §12 (lokal saja).

| Uji | Menahan |
|---|---|
| `auth/test_dependencies.py::test_dependensi_memanggil_service_lewat_objek_modul` | seam monkeypatch auth patah, uji hijau sambil memanggil JWKS + PostgREST sungguhan |
| `health/test_router.py::test_head_tidak_menyentuh_kontrak_openapi` | `operationId` ganda di `/openapi.json` saat satu rute mengaku dua metode |
| `chat/test_harness_terpisah.py` | `harness/` masuk `testpaths` dan `pytest` polos membakar kuota |
| `chat/test_llm.py::test_jawaban_kosong_*` (tiga uji) | teks Gemini kosong menjadi jawaban kosong berstatus 200 tanpa satu baris log |
| `chat/test_llm.py::test_galat_non_vendor_naik_apa_adanya_tanpa_retry` | bug lokal deterministik diulang di tiga model dengan `sleep`, lalu salah dilaporkan 502 |
| `chat/test_tools.py::test_kunci_artefak_hilang_dikembalikan_sebagai_galat_data` | kunci artefak cacat meledak sebagai galat server alih-alih galat data |
| `middleware/test_rate_limit.py::test_api_privat_slowapi_masih_ada` | tiga API privat slowapi yang dipakai sengaja hilang di versi berikutnya |
| `middleware/test_rate_limit.py::test_nama_header_limit_diambil_dari_mapping_limiter` | nama header rate limit ditulis sebagai literal, bukan dibaca dari mapping |
| `admin/test_service.py::test_jendela_sampel_penyegaran_cukup_untuk_sepuluh_desa_teratas` | `MAKS_ITEM` naik tanpa jendela sampelnya, sepuluh desa teratas jadi salah tanpa galat |
| `laporan/test_pdf.py::test_satu_halaman_tidak_dianggap_dua` | `pdf.count(b"/Type /Page")` ikut menghitung `/Type /Pages`, sehingga assert pemenggalan lolos tanpa membuktikan apa pun |
| `test_config.py::test_maks_cache_env_sampai_ke_lru_cache_di_proses_baru` | rantai `MAKS_CACHE_*` -> `Pengaturan` -> `maxsize` putus, dan instance 512 MB kehabisan memori tanpa satu baris log |
| `{kartu,jalur_ekonomi,citra_potensi,desa_kembar}/test_service.py::test_maxsize_cache_mengikuti_pengaturan` | `maxsize` dipatok mati kembali, membuat tombol memori `MAKS_CACHE_*` di produksi tidak berpengaruh |

## Menambah uji

Uji dulu, implementasi sesudahnya (TDD wajib, CLAUDE.md §6): tulis ujinya,
pastikan ia GAGAL, baru tulis kode yang membuatnya hijau. Untuk domain
baru, buat `tests/<nama>/` dengan `__init__.py` dan berkas `test_*.py`
sesuai slot yang diuji (`test_router.py`, `test_service.py`). Struktur
folder uji mencerminkan `../src/` — kalau satu domain punya folder di
`src/`, ia punya folder dengan nama sama di sini.
