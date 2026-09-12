import json

data = [
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
]

# Ensure it's safe for postgres string literal
print(json.dumps(data, ensure_ascii=False))
