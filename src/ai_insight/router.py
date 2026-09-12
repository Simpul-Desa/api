from fastapi import APIRouter, Depends, Request

from src.ai_insight.schemas import AIInsightResponse, PermintaanAIInsight
from src.ai_insight.service import dapatkan_atau_buat_insight
from src.auth.dependencies import wajib_di_atas_tamu
from src.config import Pengaturan, ambil_pengaturan
from src.datastore import Simpanan, ambil_simpanan
from src.models import Amplop, sukses

router = APIRouter(tags=["AI Insight"])

@router.post(
    "/api/ai-insight",
    response_model=Amplop[AIInsightResponse],
    summary="Dapatkan AI Insight Desa",
    dependencies=[Depends(wajib_di_atas_tamu)]
)
async def ai_insight(
    request: Request,
    body: PermintaanAIInsight,
    simpanan: Simpanan = Depends(ambil_simpanan),
    pengaturan: Pengaturan = Depends(ambil_pengaturan)
) -> Amplop[AIInsightResponse]:
    klien_supabase = request.app.state.klien_supabase
    layanan_ai = request.app.state.layanan_ai
    
    hasil = await dapatkan_atau_buat_insight(
        klien_supabase,
        layanan_ai,
        simpanan,
        pengaturan,
        body.iddesa,
        body.generate_ulang
    )
    
    return sukses(hasil)
