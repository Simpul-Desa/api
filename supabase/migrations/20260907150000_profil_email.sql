-- Kolom email pada profil: cermin auth.users.email supaya
-- GET /api/admin/pengguna?q= bisa mencari lewat PostgREST tanpa
-- membuka skema auth. PostgREST hanya mengekspos skema public, dan
-- view di atas auth.users memicu temuan advisor Supabase; kolom +
-- trigger sinkron dipilih supaya seluruh akses admin tetap satu
-- permukaan (PostgREST/public) dan nol grant baru ke skema auth.

alter table public.profil add column email text;

update public.profil p
   set email = u.email
  from auth.users u
 where u.id = p.id;

create index profil_email_idx on public.profil (email);

-- CREATE OR REPLACE mempertahankan hak akses yang sudah dicabut di
-- 20260907120500; revoke-nya tetap ditulis ulang di bawah, eksplisit.
create or replace function public.buat_profil_baru()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profil (id, email) values (new.id, new.email);
  return new;
end;
$$;

create function public.sinkron_email_profil()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.profil
     set email = new.email, diubah_pada = now()
   where id = new.id;
  return new;
end;
$$;

create trigger saat_email_pengguna_berubah
  after update of email on auth.users
  for each row
  when (new.email is distinct from old.email)
  execute function public.sinkron_email_profil();

revoke execute on function public.buat_profil_baru()
  from public, anon, authenticated;
revoke execute on function public.sinkron_email_profil()
  from public, anon, authenticated;
