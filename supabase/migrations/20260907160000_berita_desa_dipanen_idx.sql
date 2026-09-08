-- Indeks penyokong kueri "penyegaran terakhir" dashboard admin.
--
-- src/admin/service.py::penyegaran_terakhir menjalankan
-- order=dipanen_pada.desc&limit=500 atas berita_desa untuk menurunkan
-- max(dipanen_pada) per desa (status penyegaran PRD §4). Satu-satunya
-- indeks yang ada sebelum ini adalah berita_desa_iddesa_idx (iddesa) dan
-- unique (iddesa, url) — tidak ada yang menyokong scan terurut atas
-- dipanen_pada. 20260907130000_berita_desa.sql menyatakan retensi tabel ini
-- tanpa batas, jadi tanpa indeks ini biaya full scan + sort-nya tumbuh
-- tanpa henti seiring tabel membesar, padahal rute admin hanya butuh 500
-- baris teratas.

create index berita_desa_dipanen_pada_idx on public.berita_desa (dipanen_pada desc);
