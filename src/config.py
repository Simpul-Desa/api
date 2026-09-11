"""Pengaturan aplikasi dibaca dari environment variable / berkas .env."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Pengaturan(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    lingkungan: str = "dev"
    dir_data: Path = Path("data-salinan")
    origin_app: str = "http://localhost:3000"
    cache_max_age: int = 3600
    supabase_url: str = ""
    supabase_service_role_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    # Kunci Gemini terpisah untuk Asisten Desa: panen Berita Desa dan chat
    # berbagi kuota MENIT Gemini yang sama kalau memakai satu kunci. Satu
    # penyegaran 50 desa (`POST /api/admin/berita/segarkan`) bisa menghabiskan
    # kuota itu tepat saat pengguna sedang memakai chat. Kosong = 503 pada
    # endpoint chat, TIDAK PERNAH jatuh ke `gemini_api_key`.
    gemini_api_key_chat: SecretStr = SecretStr("")
    model_chat: str = "gemini-flash-latest"
    model_chat_cadangan: str = "gemini-flash-lite-latest"
    chat_maks_pesan: int = 20
    chat_maks_karakter: int = 4000
    chat_maks_putaran_alat: int = 5
    laju_chat: str = "10/minute;200/day"
    jwt_audience: str = "authenticated"
    laju_bawaan: str = "120/minute"
    # Ambang `maxsize` empat cache LRU pembaca berkas. Ini tombol MEMORI,
    # bukan tombol kecepatan: satu entri `hasil_komoditas.json` terukur
    # ±103 MB RAM (berkasnya 15,6 MB di disk) dan satu entri kartu
    # kabupaten ±13 MB, sementara muat `Simpanan` saat start sudah memakan
    # ±164 MB. Nilai bawaan di bawah aman untuk mesin pengembangan; host
    # 512 MB WAJIB menurunkannya (lihat DEPLOY.md dan `render.yaml`).
    # `ge=1` menutup 0 dan negatif — `lru_cache` membaca keduanya sebagai
    # "tanpa cache", yang berarti tiap permintaan mem-parse ulang berkas
    # 15,6 MB tanpa satu pun galat yang menunjukkannya.
    maks_cache_kartu: int = Field(default=16, ge=1)
    maks_cache_jalur: int = Field(default=4, ge=1)
    maks_cache_citra: int = Field(default=16, ge=1)
    maks_cache_kembar: int = Field(default=16, ge=1)
    # Konvensi host (Render/gunicorn) untuk jumlah worker. Dibaca di sini
    # BUKAN untuk dipakai kode aplikasi, tapi supaya asumsi proses-tunggal
    # yang dipegang gerbang penyegaran bisa ditegakkan saat boot — lihat
    # `_validasi_luar_dev`.
    web_concurrency: int = 1

    @field_validator("origin_app")
    @classmethod
    def _validasi_origin_app(cls, nilai: str) -> str:
        """Garis miring ekor dibuang agar cocok dengan Origin peramban."""
        return nilai.rstrip("/")

    @field_validator("supabase_url")
    @classmethod
    def _validasi_supabase_url(cls, nilai: str) -> str:
        """Wajib https bila terisi; garis miring ekor dibuang.

        Skema http membuat JWKS bisa disusupi penyerang jaringan (kunci
        penandatangan palsu = bypass auth total) dan mengirim kunci service
        role dalam teks polos. Garis miring ekor merusak path JWKS/REST yang
        dirakit dengan f-string.
        """
        nilai = nilai.rstrip("/")
        if nilai and not nilai.startswith("https://"):
            raise ValueError("SUPABASE_URL harus memakai skema https://")
        return nilai

    @model_validator(mode="after")
    def _validasi_luar_dev(self) -> "Pengaturan":
        """Di luar `dev`, konfigurasi rawan salah harus gagal saat start.

        Origin non-https atau kredensial Supabase kosong pada proses produksi
        berarti CORS mempercayai localhost siapa pun dan seluruh endpoint
        bertoken mati 503 — lebih baik gagal boot daripada jalan pincang.

        `WEB_CONCURRENCY > 1` ditolak dengan alasan yang sama: gerbang "satu
        pekerjaan penyegaran pada satu waktu" (`src/admin/jobs.py`) menyimpan
        state di `app.state`, yang atomik HANYA di dalam satu proses. Dengan
        beberapa worker, invarian ber-409 itu diam-diam berubah menjadi "satu
        pekerjaan per worker" dan tiap worker bisa memanen sampai
        `MAKS_DESA_SEGARKAN` desa sekaligus. Lock bersama (baris DB atau
        Redis) butuh state skema baru — keputusan terpisah, lihat ADR-0010.
        """
        if self.lingkungan == "dev":
            return self
        if self.web_concurrency > 1:
            raise ValueError(
                "WEB_CONCURRENCY harus 1 di luar lingkungan dev — gerbang "
                "satu pekerjaan penyegaran hidup di memori proses"
            )
        if not self.origin_app.startswith("https://"):
            raise ValueError("ORIGIN_APP wajib https:// di luar lingkungan dev")
        if (
            not self.supabase_url
            or not self.supabase_service_role_key.get_secret_value()
        ):
            raise ValueError("konfigurasi Supabase wajib terisi di luar lingkungan dev")
        return self


@lru_cache
def ambil_pengaturan() -> Pengaturan:
    return Pengaturan()
