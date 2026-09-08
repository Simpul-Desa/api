-- Migrasi pertama skema Supabase milik api/ (PRD api/ §4).
-- Tabel profil peran: baris dibuat otomatis saat registrasi (selalu 'tamu'),
-- berubah hanya lewat endpoint admin (service role). RLS menutup tabel dari
-- klien anon/authenticated — tanpa policy sama sekali; service role melewati RLS.

create type public.peran_pengguna as enum ('tamu', 'pemerintah', 'swasta', 'admin');

create table public.profil (
  id uuid primary key references auth.users (id) on delete cascade,
  peran public.peran_pengguna not null default 'tamu',
  dibuat_pada timestamptz not null default now(),
  diubah_pada timestamptz not null default now()
);

alter table public.profil enable row level security;

-- security definer + search_path kosong: insert berjalan dengan hak pemilik
-- fungsi saat alur registrasi Supabase Auth menyisipkan baris auth.users.
create function public.buat_profil_baru()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profil (id) values (new.id);
  return new;
end;
$$;

create trigger saat_pengguna_baru
  after insert on auth.users
  for each row execute function public.buat_profil_baru();
