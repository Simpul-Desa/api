-- Temuan advisor Supabase (WARN): fungsi security definer terekspos sebagai
-- RPC PostgREST untuk anon/authenticated. Trigger tidak butuh grant EXECUTE
-- peran-peran itu — cabut supaya fungsi hanya berjalan lewat trigger.

revoke execute on function public.buat_profil_baru() from public, anon, authenticated;
