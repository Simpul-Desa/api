import asyncio
import httpx
from pathlib import Path
from unittest.mock import AsyncMock

from src.config import ambil_pengaturan
from src.datastore import muat_simpanan
from src.chat.llm import LayananGemini
from src.ai_insight.service import dapatkan_atau_buat_insight

async def main():
    pengaturan = ambil_pengaturan()
    simpanan = muat_simpanan(Path("data-salinan"))
    layanan_ai = LayananGemini(pengaturan)
    
    # Bikin mock klien supabase untuk bypass cache
    klien_supabase_mock = AsyncMock(spec=httpx.AsyncClient)
    
    # Mock GET untuk kembalikan data kosong
    mock_get_resp = AsyncMock()
    mock_get_resp.json.return_value = []
    mock_get_resp.raise_for_status = lambda: None
    klien_supabase_mock.get.return_value = mock_get_resp
    
    # Mock POST untuk tidak melakukan apa-apa
    mock_post_resp = AsyncMock()
    mock_post_resp.raise_for_status = lambda: None
    klien_supabase_mock.post.return_value = mock_post_resp
    
    print("Memanggil AI Insight untuk desa 1801040001...")
    hasil = await dapatkan_atau_buat_insight(
        klien_supabase=klien_supabase_mock,
        layanan_ai=layanan_ai,
        simpanan=simpanan,
        pengaturan=pengaturan,
        iddesa="1801040001",
        generate_ulang=True
    )
    
    print("\n--- HASIL AI INSIGHT ---")
    print(f"ID Desa: {hasil.iddesa}")
    print(f"Kondisi Ekonomi: {hasil.kondisi_ekonomi}")
    print("Rekomendasi Aktor:")
    for r in hasil.rekomendasi_aktor:
        print(f" - {r.get('aktor')}: {r.get('aksi')}")
    print("\nTeks Lengkap:")
    print(hasil.teks_lengkap)

if __name__ == "__main__":
    asyncio.run(main())
