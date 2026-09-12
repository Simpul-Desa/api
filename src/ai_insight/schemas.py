from pydantic import BaseModel, Field

class PermintaanAIInsight(BaseModel):
    iddesa: str = Field(..., description="Kode desa (10 digit)")
    generate_ulang: bool = Field(False, description="Paksa generate ulang meskipun sudah ada di database")

class AIInsightResponse(BaseModel):
    iddesa: str
    kondisi_ekonomi: str
    rekomendasi_aktor: list[dict[str, str]]
    teks_lengkap: str
