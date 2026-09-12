import asyncio
import httpx
from src.config import ambil_pengaturan
import json

async def main():
    pengaturan = ambil_pengaturan()
    kunci = pengaturan.supabase_service_role_key.get_secret_value()
    headers = {"apikey": kunci, "Authorization": f"Bearer {kunci}", "Prefer": "resolution=merge-duplicates"}
    
    payload = {
        "iddesa": "1801040001",
        "kondisi_ekonomi": "Desa Kubu Perahu saat ini berada dalam Zona Mitra dengan status IDM Mandiri...",
        "rekomendasi_aktor": [
            {"aktor": "Pemerintah Desa", "aksi": "Menggunakan Dana Desa untuk infrastruktur..."}
        ],
        "teks_lengkap": "Teks lengkap..."
    }
    
    async with httpx.AsyncClient() as klien:
        resp = await klien.post(
            f"{pengaturan.supabase_url}/rest/v1/ai_insights",
            headers=headers,
            json=payload
        )
        print("Status Code:", resp.status_code)
        if resp.status_code >= 400:
            print("Response:", resp.text)
            
if __name__ == "__main__":
    asyncio.run(main())
