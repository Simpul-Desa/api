"""Model global: base model bersama + amplop respons seragam.

`ModelDasar` adalah satu-satunya titik warisan seluruh model Pydantic di
`src/` — praktik "custom base model" panduan fastapi-best-practices.
`model_config` sengaja dibiarkan kosong-tapi-eksplisit: keberadaannya yang
penting, bukan isinya. Titik ini menjadi tempat menyetel perilaku serialisasi
seragam bila nanti diperlukan, tanpa harus menyentuh belasan berkas
`schemas.py`.

Yang TIDAK dilakukan di sini, sengaja: menyeragamkan format datetime ke
UTC-Z. Itu akan mengubah bentuk `terbit_pada` dan `dipanen_pada` pada respons
`GET /api/berita/{iddesa}`, yang berarti mengubah kontrak PRD §6 — keputusan
terpisah, bukan efek samping restrukturisasi.
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ModelDasar(BaseModel):
    """Induk seluruh model Pydantic `src/`. Konfigurasi bawaan, eksplisit."""

    model_config = ConfigDict()


class Meta(ModelDasar):
    total: int
    hal: int
    batas: int
    parameter: dict[str, Any] | None = None


class Galat(ModelDasar):
    kode: str
    pesan: str


class Amplop(ModelDasar, Generic[T]):
    sukses: bool
    data: T | None = None
    galat: Galat | None = None
    meta: Meta | None = None


# Deskripsi bawaan FastAPI untuk respons 422 berbunyi "Validation Error", dan
# situs dokumentasi menampilkannya apa adanya di halaman rujukan yang
# selebihnya berbahasa Indonesia. Rute yang punya parameter atau badan
# permintaan memakai konstanta ini lewat `responses=`.
RESPONS_VALIDASI: dict[int | str, dict[str, Any]] = {
    422: {"description": "Parameter atau badan permintaan tidak lolos validasi"}
}


def sukses(data: T, meta: Meta | None = None) -> Amplop[T]:
    return Amplop[T](sukses=True, data=data, galat=None, meta=meta)


def gagal(kode: str, pesan: str) -> Amplop[None]:
    return Amplop[None](sukses=False, data=None, galat=Galat(kode=kode, pesan=pesan))
