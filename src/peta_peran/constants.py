"""Konstanta modul Peta Peran Desa."""

# 12 kolom ringkas kontrak `GET /api/model/peta-peran` — kolom mutu data
# lain (mis. `alasan_belum_terpetakan`) hanya ikut di rute detail.
KOLOM_RINGKAS: tuple[str, ...] = (
    "iddesa",
    "nmdesa",
    "nmkec",
    "idkab",
    "nmkab",
    "idprov",
    "zona",
    "keyakinan",
    "desil_sp",
    "desil_sk",
    "potensi_dominan",
    "sumber_dominan",
)
