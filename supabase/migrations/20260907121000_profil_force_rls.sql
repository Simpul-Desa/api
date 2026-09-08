-- Pertahanan berlapis (temuan tinjauan keamanan fase 4): paksa RLS juga
-- untuk pemilik tabel, dan cabut grant bawaan Supabase pada anon/
-- authenticated supaya penambahan satu policy select di masa depan tidak
-- diam-diam menghidupkan grant insert/update/delete yang masih terpasang.

alter table public.profil force row level security;

revoke all on table public.profil from anon, authenticated;
