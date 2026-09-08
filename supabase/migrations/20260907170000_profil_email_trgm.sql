-- Indeks trigram untuk pencarian pengguna di halaman /admin.
--
-- GET /api/admin/pengguna?q= menyaring email dengan `ilike.*{q}*`
-- (src/admin/service.py::daftar_pengguna). Wildcard di AWAL pola membuat
-- btree tidak terpakai sama sekali -- btree hanya melayani pola berawalan
-- tetap (`foo%`), termasuk bila dibuat dengan text_pattern_ops. Akibatnya
-- setiap pencarian memindai seluruh tabel profil lalu menyaring.
--
-- profil_email_idx dari 20260907150000_profil_email.sql SENGAJA dibiarkan:
-- ia masih melayani `order=email.asc.nullslast` pada permintaan yang sama.
-- Indeks GIN di bawah menutup sisi penyaringnya, bukan sisi pengurutannya.

-- Extension dipasang ke skema `extensions`, BUKAN `public`: itu konvensi
-- Supabase, dan extension di `public` memicu temuan advisor keamanan
-- (extension_in_public). Kelas operatornya karena itu ikut diberi awalan
-- skema — `extensions` memang ada di search_path bawaan Supabase, tapi
-- migrasi tidak boleh bergantung pada search_path yang bisa berubah.
create extension if not exists pg_trgm with schema extensions;

create index profil_email_trgm_idx
  on public.profil using gin (email extensions.gin_trgm_ops);
