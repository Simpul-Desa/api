-- Tabel Berita Desa (PRD api/ §4, diperluas fase 6: rangkuman + kategori
-- + perangkum). iddesa TIDAK ber-FK — data desa hidup di berkas salinan
-- build, bukan di basis data; validasi iddesa dilakukan aplikasi saat panen
-- terhadap indeks kartu. RLS menutup tabel dari klien anon/authenticated
-- (tanpa policy sama sekali); baca-tulis hanya lewat service role sisi
-- server api/.

create table public.berita_desa (
  id bigint generated always as identity primary key,
  iddesa text not null check (iddesa ~ '^\d{10}$'),
  judul text not null,
  url text not null,
  sumber text not null default '',
  terbit_pada timestamptz,
  dipanen_pada timestamptz not null default now(),
  rangkuman text,
  kategori text[] not null default '{}',
  perangkum text not null default '',
  unique (iddesa, url)
);

create index berita_desa_iddesa_idx on public.berita_desa (iddesa);

alter table public.berita_desa enable row level security;
alter table public.berita_desa force row level security;
