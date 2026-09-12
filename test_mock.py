import asyncio
import httpx
from pathlib import Path
from unittest.mock import AsyncMock
from src.config import ambil_pengaturan
from src.datastore import muat_simpanan
from src.chat.llm import LayananAI, HasilLayanan
from src.ai_insight.service import dapatkan_atau_buat_insight

class LayananMock(LayananAI):
    async def jawab(self, messages, system_prompt, temperature, konteks):
        import json
        dummy = {
            "kondisi_ekonomi": "Desa KUBU PERAHU merupakan desa dengan status IDM Mandiri yang berada di Zona Mitra...",
            "rekomendasi_aktor": [
                {"aktor": "Pemerintah Desa", "aksi": "Menggunakan Dana Desa untuk peningkatan BUMDes"},
                {"aktor": "Swasta", "aksi": "Membangun gudang dan cold storage mengingat komoditas Ikan yang sangat kuat"}
            ],
            "teks_lengkap": "Desa KUBU PERAHU, sebagai desa Mandiri di Zona Mitra, menunjukkan potensi luar biasa sebagai Simpul Logistik..."
        }
        return HasilLayanan(
            teks=json.dumps(dummy),
            jejak=[],
            hasil_mentah=[],
            putaran=1,
            model="mock",
            peringatan=[]
        )

async def main():
    pengaturan = ambil_pengaturan()
    simpanan = muat_simpanan(Path("data-salinan"))
    layanan_ai = LayananMock()
    
    klien_mock = AsyncMock(spec=httpx.AsyncClient)
    klien_mock.get.return_value.json.return_value = []
    klien_mock.post.return_value.raise_for_status = lambda: None
    
    hasil = await dapatkan_atau_buat_insight(
        klien_mock, layanan_ai, simpanan, pengaturan, "1801040001", True
    )
    
    print("\n--- TEST END-TO-END BERHASIL ---")
    print(f"ID Desa: {hasil.iddesa}")
    print(f"Teks Lengkap:\n{hasil.teks_lengkap}")

if __name__ == "__main__":
    asyncio.run(main())
