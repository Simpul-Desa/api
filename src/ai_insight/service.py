import json
import logging
import httpx
from pathlib import Path
from pydantic import ValidationError

from src.ai_insight.schemas import AIInsightResponse
from src.config import Pengaturan
from src.datastore import Simpanan
from src.exceptions import GalatAPI

logger = logging.getLogger(__name__)
_DIR_PROMPT = Path(__file__).parent

async def dapatkan_atau_buat_insight(
    klien_supabase: httpx.AsyncClient,
    layanan_ai,
    simpanan: Simpanan,
    pengaturan: Pengaturan,
    iddesa: str,
    generate_ulang: bool
) -> AIInsightResponse:
    kunci = pengaturan.supabase_service_role_key.get_secret_value()
    headers = {"apikey": kunci, "Authorization": f"Bearer {kunci}"}
    
    # 1. Cek di Supabase jika tidak generate_ulang
    if not generate_ulang:
        try:
            resp = await klien_supabase.get(
                f"{pengaturan.supabase_url}/rest/v1/ai_insights?on_conflict=iddesa",
                params={"iddesa": f"eq.{iddesa}", "select": "*"},
                headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
            if data and isinstance(data, list) and len(data) > 0:
                return AIInsightResponse(**data[0])
        except Exception as exc:
            logger.warning(f"Gagal membaca dari ai_insights: {exc}")
            # Lanjut ke generate jika gagal baca
    
    # 2. Kumpulkan Data dari Simpanan
    desa_peran = None
    if simpanan.peta_peran_per_desa:
        desa_peran = simpanan.peta_peran_per_desa.get(iddesa)
        
    if not desa_peran:
        raise GalatAPI("DESA_TIDAK_DITEMUKAN", f"Desa {iddesa} tidak ditemukan di data peran", 404)
        
    nmdesa = desa_peran.get("nmdesa", "Tidak diketahui")
    zona = desa_peran.get("zona", "Tidak diketahui")
    potensi_dominan = desa_peran.get("potensi_dominan", "Tidak diketahui")
    idm_status = desa_peran.get("idm_status", "Tidak diketahui")
    jadesta = desa_peran.get("jadesta_kategori", "")
    
    # Komoditas
    subsektor = []
    for k, v in desa_peran.items():
        if k.startswith("pSUB_") and v and v > 0:
            nama_sub = k.replace("pSUB_", "").upper()
            subsektor.append(f"- {nama_sub}: {v}%")
    potensi_teks = "\n".join(subsektor) if subsektor else "Data subsektor tidak tersedia"
    
    # Program Pemerintah (Rules)
    rekomendasi_program = []
    if idm_status in ["TERTINGGAL", "SANGAT TERTINGGAL"]:
        rekomendasi_program.append("- **Dana Desa**: Fokuskan untuk pembangunan infrastruktur dasar untuk mengejar ketertinggalan IDM.")
    else:
        rekomendasi_program.append("- **Dana Desa**: Fokuskan untuk pemberdayaan ekonomi dan BUMDes karena status IDM sudah cukup baik.")
        
    if desa_peran.get("pSUB_tp", 0) > 30 or desa_peran.get("pSUB_horti", 0) > 30:
        rekomendasi_program.append("- **KDMP (Kawasan Desa Mandiri Pangan)**: Potensi pertanian tinggi, sangat cocok untuk program ketahanan pangan.")
        
    if zona in ["Zona Tumbuh", "Zona Mitra"]:
        rekomendasi_program.append("- **Desa BISA**: Desa ini berada di zona strategis yang cocok untuk program pemberdayaan berkesinambungan.")
        
    if desa_peran.get("SP", 0) > 80 and (desa_peran.get("pSUB_kebun", 0) > 20 or desa_peran.get("pSUB_ikan", 0) > 20):
        rekomendasi_program.append("- **Ekspor**: Skor Potensi (SP) sangat tinggi dengan basis komoditas kuat. Layak didorong untuk program Desa Ekspor.")
        
    if desa_peran.get("potensi_dominan") == "Simpul Logistik":
        rekomendasi_program.append("- **Kemitraan Swasta (Logistik)**: Karena merupakan Simpul Logistik, sangat direkomendasikan untuk menggandeng swasta dalam pembangunan gudang atau pusat distribusi.")

    if jadesta:
        rekomendasi_program.append(f"- **Jadesta**: Sudah tercatat dengan kategori {jadesta}, kembangkan infrastruktur pariwisata lebih lanjut.")
        
    program_teks = "\n".join(rekomendasi_program) if rekomendasi_program else "Belum ada program spesifik yang memenuhi kriteria kuat, perlu asesmen lokal."
    
    # 3. Rakit Prompt
    prompt_template = (_DIR_PROMPT / "prompt.md").read_text(encoding="utf-8")
    prompt = prompt_template.replace("{{NAMA_DESA}}", nmdesa)
    prompt = prompt.replace("{{ZONA}}", zona)
    prompt = prompt.replace("{{POTENSI_DOMINAN}}", potensi_dominan)
    prompt = prompt.replace("{{IDM_STATUS}}", str(idm_status))
    prompt = prompt.replace("{{JADESTA}}", str(jadesta))
    prompt = prompt.replace("{{POTENSI_SUBSEKTOR}}", potensi_teks)
    prompt = prompt.replace("{{PROGRAM_REKOMENDASI}}", program_teks)
    
    # 4. Panggil AI
    from src.chat.schemas import PermintaanChat, Pesan
    from src.chat.tools import KonteksAlat
    
    pesan_klien = [Pesan(role="user", isi="Buatkan AI Insight berdasarkan data tersebut.")]
    
    konteks = KonteksAlat(simpanan=simpanan, klien_supabase=klien_supabase)
    
    # Panggil model dengan temperatur rendah agar lebih faktual
    hasil = await layanan_ai.jawab(
        pesan_klien, prompt, 0.2, konteks
    )
    
    # Parse JSON dari hasil.teks
    import re
    teks = hasil.teks
    
    # Bersihkan markdown json jika ada
    teks = re.sub(r'```json\n?', '', teks)
    teks = re.sub(r'```\n?', '', teks)
    
    try:
        data_ai = json.loads(teks)
    except json.JSONDecodeError as exc:
        logger.error(f"Gagal parse JSON dari LLM: {teks}")
        raise GalatAPI("LLM_GALAT_FORMAT", "Balasan AI tidak sesuai format JSON", 500) from exc
        
    hasil_insight = AIInsightResponse(
        iddesa=iddesa,
        kondisi_ekonomi=data_ai.get("kondisi_ekonomi", ""),
        rekomendasi_aktor=data_ai.get("rekomendasi_aktor", []),
        teks_lengkap=data_ai.get("teks_lengkap", "")
    )
    
    # 5. Simpan ke Supabase (Upsert)
    payload = {
        "iddesa": iddesa,
        "kondisi_ekonomi": hasil_insight.kondisi_ekonomi,
        "rekomendasi_aktor": hasil_insight.rekomendasi_aktor,
        "teks_lengkap": hasil_insight.teks_lengkap
    }
    
    try:
        resp = await klien_supabase.post(
            f"{pengaturan.supabase_url}/rest/v1/ai_insights?on_conflict=iddesa",
            headers={**headers, "Prefer": "resolution=merge-duplicates"},
            json=payload
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning(f"Gagal menyimpan ke ai_insights (non-fatal): {exc}")
        
    return hasil_insight
