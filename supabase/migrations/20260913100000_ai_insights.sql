-- Tabel untuk menyimpan hasil generate AI Insight
CREATE TABLE IF NOT EXISTS public.ai_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    iddesa TEXT NOT NULL UNIQUE,
    kondisi_ekonomi TEXT NOT NULL,
    rekomendasi_aktor JSONB NOT NULL,
    teks_lengkap TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Mengamankan tabel menggunakan RLS (Row Level Security)
ALTER TABLE public.ai_insights ENABLE ROW LEVEL SECURITY;

-- Karena ini akan dibaca via PostgREST oleh API (yang memakai service_role key),
-- service_role selalu bypass RLS. Tapi mari kita buat policy untuk anon/authenticated 
-- jika suatu saat mereka ingin membacanya secara langsung.
CREATE POLICY "AI Insights dapat dibaca oleh semua pengguna" 
    ON public.ai_insights FOR SELECT 
    USING (true);

-- Indeks pada iddesa untuk pencarian cepat
CREATE INDEX IF NOT EXISTS ai_insights_iddesa_idx ON public.ai_insights(iddesa);
