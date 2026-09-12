import asyncio
import httpx
from pathlib import Path
from src.config import ambil_pengaturan
from src.datastore import muat_simpanan
from src.chat.llm import LayananGemini
from src.ai_insight.service import dapatkan_atau_buat_insight

async def main():
    pengaturan = ambil_pengaturan()
    simpanan = muat_simpanan(Path("data-salinan"))
    layanan_ai = LayananGemini(pengaturan)
    
    klien = httpx.AsyncClient(timeout=30.0)
    
    iddesa = "1801040002"
    print(f"Mulai generate AI Insight untuk desa {iddesa}...")
    
    try:
        hasil = await dapatkan_atau_buat_insight(
            klien_supabase=klien,
            layanan_ai=layanan_ai,
            simpanan=simpanan,
            pengaturan=pengaturan,
            iddesa=iddesa,
            generate_ulang=True
        )
        print("\n--- BERHASIL GENERATE & SIMPAN ---")
        print(f"ID Desa: {hasil.iddesa}")
        print("Teks Lengkap:")
        print(hasil.teks_lengkap)
    except Exception as e:
        print(f"Gagal: {e}")
    finally:
        await klien.aclose()

if __name__ == "__main__":
    asyncio.run(main())
