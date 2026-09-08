-- Samakan pengerasan berita_desa dengan public.profil.
--
-- 20260907130000_berita_desa.sql sudah menyalakan RLS + force row level
-- security, sehingga tidak ada baris yang bisa dibaca atau ditulis anon /
-- authenticated. Tetapi grant SELECT bawaan Supabase masih terpasang, jadi
-- PostgREST membalas 200 dengan daftar kosong alih-alih menolak: nama tabel
-- dan kolomnya tetap dapat dienumerasi dari luar. profil sudah dicabut
-- grantnya di 20260907121000_profil_force_rls.sql; berkas ini menutup
-- selisih itu.
--
-- Rute /api/berita/{iddesa} tidak terpengaruh: src/berita/service.py
-- memanggil PostgREST dengan kunci service role, yang melewati RLS maupun
-- grant tabel.

revoke all on table public.berita_desa from anon, authenticated;
