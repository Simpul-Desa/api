-- 1. Buat Tabel ai_insights
CREATE TABLE IF NOT EXISTS public.ai_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    iddesa TEXT NOT NULL UNIQUE,
    kondisi_ekonomi TEXT NOT NULL,
    rekomendasi_aktor JSONB NOT NULL,
    teks_lengkap TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.ai_insights ENABLE ROW LEVEL SECURITY;

CREATE POLICY "AI Insights dapat dibaca oleh pengguna login" 
    ON public.ai_insights FOR SELECT 
    TO authenticated 
    USING (true);

CREATE INDEX IF NOT EXISTS ai_insights_iddesa_idx ON public.ai_insights(iddesa);

-- 2. Input Hasil LLM untuk Desa Kubu Perahu (1801040001)
INSERT INTO public.ai_insights (iddesa, kondisi_ekonomi, rekomendasi_aktor, teks_lengkap)
VALUES (
    '1801040001',
    'Desa Kubu Perahu saat ini berada dalam Zona Mitra dengan status IDM Mandiri, menunjukkan kemandirian tata kelola yang matang dan kapasitas fiskal yang memadai. Berdasarkan struktur ekonominya, desa ini didominasi oleh peran sebagai Simpul Logistik dengan skor mencapai 97,78%, serta ditopang secara kuat oleh sektor perikanan (94,44%) dan kehutanan (91,85%). Kombinasi antara fungsi simpul logistik yang strategis dan komoditas unggulan berbasis perikanan serta hutan menjadikan Kubu Perahu sebagai pusat distribusi dan agregasi ekonomi yang sangat potensial di kawasan regionalnya.',
    '[
      {
        "aktor": "Pemerintah Desa",
        "aksi": "Menggunakan Dana Desa untuk memperkuat pemberdayaan ekonomi masyarakat dan BUMDes agar roda perekonomian lokal semakin mandiri dan produktif."
      },
      {
        "aktor": "Pemerintah Pusat dan Daerah",
        "aksi": "Memasukkan desa ini ke dalam program Desa Ekspor dan Desa BISA, memanfaatkan skor potensi yang sangat tinggi untuk memperluas jangkauan pasar komoditas unggulan."
      },
      {
        "aktor": "Swasta",
        "aksi": "Mengambil peran melalui skema Kemitraan Swasta (Logistik) untuk berinvestasi dalam pembangunan gudang, fasilitas penyimpanan, atau pusat distribusi guna mengoptimalkan posisi strategis desa sebagai simpul logistik utama."
      }
    ]'::jsonb,
    E'Desa Kubu Perahu saat ini berada dalam Zona Mitra dengan status IDM Mandiri, menunjukkan kemandirian tata kelola yang matang dan kapasitas fiskal yang memadai. Berdasarkan struktur ekonominya, desa ini didominasi oleh peran sebagai Simpul Logistik dengan skor mencapai 97,78%, serta ditopang secara kuat oleh sektor perikanan (94,44%) dan kehutanan (91,85%). Kombinasi antara fungsi simpul logistik yang strategis dan komoditas unggulan berbasis perikanan serta hutan menjadikan Kubu Perahu sebagai pusat distribusi dan agregasi ekonomi yang sangat potensial di kawasan regionalnya.\n\nBerikut adalah rekomendasi aksi spesifik untuk para aktor terkait:\n- **Pemerintah Desa** dapat menggunakan **Dana Desa** untuk memperkuat pemberdayaan ekonomi masyarakat dan BUMDes agar roda perekonomian lokal semakin mandiri dan produktif.\n- **Pemerintah Pusat dan Daerah** didorong untuk memasukkan desa ini ke dalam program **Desa Ekspor** dan **Desa BISA**, memanfaatkan skor potensi yang sangat tinggi untuk memperluas jangkauan pasar komoditas unggulan.\n- **Swasta** dapat mengambil peran melalui skema **Kemitraan Swasta (Logistik)** untuk berinvestasi dalam pembangunan gudang, fasilitas penyimpanan, atau pusat distribusi guna mengoptimalkan posisi strategis desa sebagai simpul logistik utama.'
);
