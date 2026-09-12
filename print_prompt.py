from pathlib import Path
from src.config import ambil_pengaturan
from src.datastore import muat_simpanan

pengaturan = ambil_pengaturan()
simpanan = muat_simpanan(Path("data-salinan"))
iddesa = "1801040001"
desa_peran = simpanan.peta_peran_per_desa.get(iddesa)

nmdesa = desa_peran.get("nmdesa", "Tidak diketahui")
zona = desa_peran.get("zona", "Tidak diketahui")
potensi_dominan = desa_peran.get("potensi_dominan", "Tidak diketahui")
idm_status = desa_peran.get("idm_status", "Tidak diketahui")
jadesta = desa_peran.get("jadesta_kategori", "")

subsektor = []
for k, v in desa_peran.items():
    if k.startswith("pSUB_") and v and v > 0:
        nama_sub = k.replace("pSUB_", "").upper()
        subsektor.append(f"- {nama_sub}: {v}%")
potensi_teks = "\n".join(subsektor) if subsektor else "Data subsektor tidak tersedia"

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

prompt_template = (Path("src/ai_insight/prompt.md")).read_text(encoding="utf-8")
prompt = prompt_template.replace("{{NAMA_DESA}}", nmdesa)
prompt = prompt.replace("{{ZONA}}", zona)
prompt = prompt.replace("{{POTENSI_DOMINAN}}", potensi_dominan)
prompt = prompt.replace("{{IDM_STATUS}}", str(idm_status))
prompt = prompt.replace("{{JADESTA}}", str(jadesta))
prompt = prompt.replace("{{POTENSI_SUBSEKTOR}}", potensi_teks)
prompt = prompt.replace("{{PROGRAM_REKOMENDASI}}", program_teks)

print(prompt)
