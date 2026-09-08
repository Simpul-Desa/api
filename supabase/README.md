# Skema Supabase `api/`

Skema Supabase adalah milik `api/` (PRD bagian 4): tabel peran, tabel berita, dan
migrasinya didefinisikan dan dirawat di folder ini. `app/` memakai Supabase hanya
untuk autentikasi dan tunduk pada skema yang ditetapkan di sini.

## Isi

`migrations/` — delapan berkas SQL, dijalankan urut nama berkas. Berkas-berkas ini
adalah SUMBER KEBENARAN: menjalankan kedelapannya berurutan pada basis data kosong
menghasilkan skema yang persis sama dengan yang terpasang sekarang.

| # | Berkas | Isi |
|---|---|---|
| 1 | `20260907120000_profil.sql` | enum `peran_pengguna`, tabel `profil`, RLS, trigger `buat_profil_baru` |
| 2 | `20260907120500_profil_revoke_execute.sql` | cabut EXECUTE fungsi definer dari anon/authenticated |
| 3 | `20260907121000_profil_force_rls.sql` | `force row level security` + cabut grant tabel |
| 4 | `20260907130000_berita_desa.sql` | tabel `berita_desa`, RLS + force |
| 5 | `20260907140000_berita_desa_revoke.sql` | cabut grant tabel `berita_desa` |
| 6 | `20260907150000_profil_email.sql` | kolom `profil.email` + trigger sinkron |
| 7 | `20260907160000_berita_desa_dipanen_idx.sql` | indeks `dipanen_pada desc` |
| 8 | `20260907170000_profil_email_trgm.sql` | `pg_trgm` + indeks GIN trigram `profil.email` |

## Prinsip

**Berkas di sini harus selalu sama persis dengan yang terpasang di basis data.**
Migrasi yang ditulis tetapi sengaja tidak diterapkan TIDAK boleh tinggal di
`migrations/` — begitu ia ada di sana, replikasi ke proyek baru menghasilkan
skema yang berbeda dari produksi, dan itu justru cacat yang paling sulit
dilacak. Keputusan untuk tidak menerapkan sesuatu dicatat di `TRACK.md`, bukan
disimpan sebagai berkas menganggur.

## Menyiapkan CLI (sekali saja, per mesin)

CLI belum terpasang di mesin pengembangan mana pun sejauh ini; enam migrasi
pertama dipasang lewat MCP Supabase. Riwayat migrasi di server SUDAH
diselaraskan sehingga versinya cocok satu-satu dengan nama berkas di sini —
tidak ada `supabase migration repair` yang perlu dijalankan.

```bash
brew install supabase/tap/supabase     # atau lihat docs.supabase.com/guides/cli
cd api/
supabase init                          # membuat supabase/config.toml; JANGAN timpa migrations/
supabase link --project-ref <project-ref>
supabase migration list                # verifikasi: 8 lokal, 8 remote, semua sejajar
```

`supabase migration list` harus menampilkan kedelapan versi berpasangan di kolom
Local dan Remote. Bila ada yang hanya muncul di satu sisi, BERHENTI — jangan
`db push` sebelum selisihnya dipahami.

## Menambah migrasi baru

```bash
supabase migration new <nama_snake_case>
# tulis SQL-nya, lalu:
supabase db push
```

Bila memakai MCP `apply_migration` (bukan CLI), perhatikan: MCP menstempel versi
dengan waktu saat itu, BUKAN nama berkas lokal. Kalau jalur itu dipakai, samakan
lagi kolom `version` di `supabase_migrations.schema_migrations` dengan nama
berkasnya, kalau tidak `db push` berikutnya akan mengira migrasi itu belum
terpasang dan mencoba mengulangnya.

## Replikasi ke proyek Supabase baru

```bash
supabase link --project-ref <ref-proyek-baru>
supabase db push
```

Kedelapan berkas dijalankan berurutan pada riwayat yang masih kosong. Semuanya
sudah diperiksa aman untuk basis data kosong. Setelah itu, dua hal yang TIDAK
dibawa migrasi dan harus disetel manual di dashboard proyek baru:

1. **Leaked Password Protection** (Authentication -> Policies) — pengaturan Auth,
   di luar jangkauan SQL.
2. **Isi `.env`** `api/`: `SUPABASE_URL` dan `SUPABASE_SERVICE_ROLE_KEY` proyek
   baru. Lihat `.env.example`.

## Yang sengaja tidak ada

- **Tidak ada policy RLS.** Kedua tabel menyalakan RLS + `force` tanpa satu pun
  policy: itu berarti tolak-semua untuk anon/authenticated, dan service role
  melewati RLS. Advisor Supabase melaporkannya sebagai INFO
  `rls_enabled_no_policy` — itu memang yang diinginkan, bukan temuan.
- **Tidak ada migrasi turun (down migration).** Belum diperlukan di MVP.
- **`extensions` bukan `public`** untuk `pg_trgm`. Extension di `public` memicu
  temuan advisor `extension_in_public`.
