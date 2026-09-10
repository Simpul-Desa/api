"""Alat (function calling) Asisten Desa: jembatan Gemini ke service internal.

Setiap alat memanggil SERVICE INTERNAL langsung (`src/<domain>/service.py`),
BUKAN HTTP ke diri sendiri. Konsekuensinya: perilaku yang biasanya datang
gratis dari rute HTTP harus ditiru sendiri di sini — cek `iddesa` dikenal
(setara 404), tangkap artefak hilang (setara 503), dan POTONG hasil (rute
punya paginasi, service tidak).

Galat SELALU dikembalikan sebagai DATA (`{"galat": "KODE"}`), tidak pernah
dilempar sebagai exception ke pemanggil `jalankan_alat`. Alasannya: model
harus bisa menjawab jujur "datanya tidak ada" dan melanjutkan percakapan —
satu alat gagal tidak boleh menjatuhkan seluruh giliran chat.
"""

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from google.genai import types
from starlette.concurrency import run_in_threadpool

from src.berita.service import baris_berita
from src.chat.constants import (
    ALAT_TIDAK_DIKENAL,
    ARGUMEN_TIDAK_SAH,
    MAKS_BARIS_ALAT,
    MAKS_BARIS_BERITA,
)
from src.citra_potensi.service import baca_sel_citra
from src.datastore import Simpanan, wajib
from src.desa.service import kunci_urutan
from src.desa_kembar.constants import KETERANGAN_TANPA_VEKTOR
from src.desa_kembar.service import baca_kembar_kab, tetangga_terjoin
from src.exceptions import DATA_BELUM_SIAP, DESA_TIDAK_ADA, TIDAK_DITEMUKAN, GalatAPI
from src.jalur_ekonomi.service import baca_jalur, ratakan
from src.kartu.service import baca_kartu_kab

logger = logging.getLogger(__name__)

# Bentuk iddesa: kode BPS desa, selalu 10 digit.
# \A..\Z (bukan ^..$): "$" cocok sebelum newline penutup, jadi "1801040001\n"
# lolos "^..$" lalu meledak di hilir sebagai path/URL cacat. [0-9] eksplisit:
# \d menerima digit Unicode (١٨٠١...).
_POLA_IDDESA = re.compile(r"\A[0-9]{10}\Z")
_POLA_IDKAB = re.compile(r"\A[0-9]{4}\Z")
_POLA_IDPROV = re.compile(r"\A[0-9]{2}\Z")
_VARIAN_JALUR = frozenset({"komoditas", "gudang-kopdes", "cold-storage", "wisata"})

# Awalan administratif yang sering disertakan pengguna padahal `wilayah.json`
# menyimpan nama kabupaten TANPA awalan ini (mis. "TANGGAMUS", bukan
# "Kabupaten Tanggamus"). Urutan tidak penting untuk kebenaran ("kabupaten "
# dan "kab " tidak pernah sama-sama cocok pada string yang sama), tapi
# ditulis dari yang paling panjang ke pendek untuk keterbacaan.
_PREFIKS_ADMINISTRATIF = ("kabupaten ", "kab. ", "kab ", "kota ")


@dataclass(frozen=True)
class KonteksAlat:
    """Yang dibutuhkan alat untuk mengambil data.

    Sengaja BUKAN `Request`: alat harus bisa diuji tanpa membangun aplikasi
    FastAPI sama sekali.
    """

    simpanan: Simpanan
    klien_supabase: httpx.AsyncClient


def _potong(baris: list[Any], maks: int) -> dict[str, Any]:
    """Potong daftar hasil alat dan LAPORKAN cacah sebenarnya.

    Service internal tidak berpaginasi seperti rutenya. Tanpa ini satu
    pemanggilan `jalur_ekonomi` mengirim seluruh jalur 97 kabupaten ke
    konteks model. `total` disertakan supaya model bisa menjawab jujur
    "ditampilkan 20 dari 1.248", bukan mengira 20 itu seluruhnya.
    """
    return {
        "data": baris[:maks],
        "total": len(baris),
        "terpotong": len(baris) > maks,
    }


# --- Deklarasi Gemini -------------------------------------------------------

_SKEMA_IDDESA = {
    "type": "object",
    "properties": {
        "iddesa": {
            "type": "string",
            "description": "Kode BPS desa 10 digit, dari cari_desa",
        }
    },
    "required": ["iddesa"],
}

DEKLARASI_ALAT = [
    types.FunctionDeclaration(
        name="cari_desa",
        description=(
            "Cari desa berdasarkan nama (minimal 2 huruf). Mengembalikan daftar kandidat "
            "berisi iddesa, nama desa, kecamatan, kabupaten, provinsi. Panggil ini dulu "
            "bila iddesa belum diketahui."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "nama": {"type": "string", "description": "Nama desa yang dicari"}
            },
            "required": ["nama"],
        },
    ),
    types.FunctionDeclaration(
        name="kartu_ekonomi",
        description=(
            "Ambil Kartu Ekonomi Desa utuh (identitas, Peta Peran, potensi, kesiapan, "
            "biofisik, logistik, Jalur Ekonomi, Desa Kembar, fakta program, mutu data) "
            "untuk satu desa."
        ),
        parameters_json_schema=_SKEMA_IDDESA,
    ),
    types.FunctionDeclaration(
        name="peta_peran",
        description=(
            "Ambil hasil Peta Peran satu desa: Skor Potensi, Skor Kesiapan, zona "
            "penanganan, keyakinan, Potensi Dominan beserta Sumber Potensi Dominan."
        ),
        parameters_json_schema=_SKEMA_IDDESA,
    ),
    types.FunctionDeclaration(
        name="desa_kembar",
        description="Ambil daftar Desa Kembar (desa dengan profil paling mirip) untuk satu desa.",
        parameters_json_schema=_SKEMA_IDDESA,
    ),
    types.FunctionDeclaration(
        name="jalur_ekonomi",
        description=(
            "Ambil hasil Jalur Ekonomi satu varian (komoditas, gudang-kopdes, "
            "cold-storage, atau wisata): daftar Desa Poros dan cacah Desa Sejalur "
            "yang dilayaninya, difilter opsional per kabupaten."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "varian": {
                    "type": "string",
                    "enum": ["komoditas", "gudang-kopdes", "cold-storage", "wisata"],
                    "description": "Varian Jalur Ekonomi",
                },
                "kab": {
                    "type": "string",
                    "description": "Filter kode kabupaten 4 digit (opsional)",
                },
            },
            "required": ["varian"],
        },
    ),
    types.FunctionDeclaration(
        name="berita_desa",
        description=(
            "Ambil Berita Desa (rangkuman artikel yang sudah dipanen) untuk satu desa. "
            "Terbaru dulu."
        ),
        parameters_json_schema=_SKEMA_IDDESA,
    ),
    types.FunctionDeclaration(
        name="citra_potensi",
        description=(
            "Ambil skor mentah Citra Potensi Desa satu sel (kombinasi provinsi + target "
            "komoditas/tema) hasil pembacaan citra satelit, urut skor tertinggi."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "prov": {"type": "string", "description": "Kode provinsi 2 digit"},
                "target": {
                    "type": "string",
                    "description": "Kode target sel Citra Potensi Desa, dari daftar sel",
                },
            },
            "required": ["prov", "target"],
        },
    ),
    types.FunctionDeclaration(
        name="wilayah_ringkasan",
        description="Ambil ringkasan nasional: cacah provinsi, kabupaten, dan desa.",
        parameters_json_schema={"type": "object", "properties": {}},
    ),
    types.FunctionDeclaration(
        name="cek_cakupan_wilayah",
        description=(
            "Cek apakah nama provinsi atau kabupaten yang disebut pengguna ada dalam "
            "cakupan data SIMPUL DESA. Mengembalikan provinsi dan/atau kabupaten yang "
            "cocok beserta kodenya; bila tidak ada yang cocok, mengembalikan daftar "
            "provinsi yang memang tercakup. Panggil ini sebelum menjawab pertanyaan "
            "yang menyebut nama wilayah, sebelum mengasumsikan wilayahnya ada di "
            "cakupan."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "nama": {
                    "type": "string",
                    "description": "Nama provinsi atau kabupaten yang disebut pengguna",
                }
            },
            "required": ["nama"],
        },
    ),
]


def alat_gemini() -> types.Tool:
    """Bungkus `DEKLARASI_ALAT` jadi satu `types.Tool` untuk diserahkan ke Gemini."""
    return types.Tool(function_declarations=DEKLARASI_ALAT)


def _argumen_sah(nama: str, argumen: dict[str, Any]) -> bool:
    """Validasi bentuk argumen per alat SEBELUM menyentuh data.

    Deklarasi `parameters_json_schema` ke Gemini BUKAN penegakan — model bisa
    mengirim argumen apa pun (tipe salah, kunci hilang, nilai liar), jadi
    diperiksa ulang di sini sebelum diteruskan ke lapis data.
    """
    if nama in {"cari_desa", "cek_cakupan_wilayah"}:
        nilai = argumen.get("nama")
        return isinstance(nilai, str) and 2 <= len(nilai) <= 100
    if nama in {"kartu_ekonomi", "peta_peran", "desa_kembar", "berita_desa"}:
        nilai = argumen.get("iddesa")
        return isinstance(nilai, str) and bool(_POLA_IDDESA.match(nilai))
    if nama == "jalur_ekonomi":
        varian = argumen.get("varian")
        if not (isinstance(varian, str) and varian in _VARIAN_JALUR):
            return False
        kab = argumen.get("kab")
        return kab is None or (isinstance(kab, str) and bool(_POLA_IDKAB.match(kab)))
    if nama == "citra_potensi":
        prov = argumen.get("prov")
        target = argumen.get("target")
        return (
            isinstance(prov, str)
            and bool(_POLA_IDPROV.match(prov))
            and isinstance(target, str)
            and 1 <= len(target) <= 100
        )
    if nama == "wilayah_ringkasan":
        return True
    return True


# --- Implementasi alat -------------------------------------------------------


async def cari_desa(konteks: KonteksAlat, nama: str) -> dict[str, Any]:
    """Cari desa lewat substring nama (tak peka kapital), tiru `src/desa/router.py`.

    Dipotong ke `MAKS_BARIS_ALAT` — tanpa paginasi rute HTTP, satu pemanggilan
    bisa mengembalikan seluruh 17.467 desa.
    """
    indeks_kartu = wajib(konteks.simpanan.indeks_kartu, "indeks kartu ekonomi")

    q_casefold = nama.casefold()
    kandidat = [b for b in indeks_kartu if q_casefold in b["nmdesa"].casefold()]
    kandidat_terurut = sorted(kandidat, key=lambda b: kunci_urutan(b, q_casefold))

    return _potong(kandidat_terurut, MAKS_BARIS_ALAT)


async def kartu_ekonomi(konteks: KonteksAlat, iddesa: str) -> dict[str, Any]:
    """Kartu Ekonomi Desa utuh, tiru `src/kartu/router.py`.

    `iddesa` dicari lebih dulu di `indeks_per_desa` untuk menentukan
    `idkab`-nya; tak dikenal di sana atau tak ada di berkas kartu
    kabupatennya sama-sama `DESA_TIDAK_ADA`. Kartu dikembalikan UTUH, tidak
    dipotong.
    """
    indeks_per_desa = wajib(konteks.simpanan.indeks_per_desa, "indeks kartu ekonomi")
    baris = indeks_per_desa.get(iddesa)
    if baris is None:
        return {"galat": DESA_TIDAK_ADA}

    kartu_kab = wajib(
        await run_in_threadpool(
            baca_kartu_kab, str(konteks.simpanan.dir_data), baris["idkab"]
        ),
        f"kartu ekonomi kab {baris['idkab']}",
    )
    kartu = kartu_kab.get(iddesa)
    if kartu is None:
        return {"galat": DESA_TIDAK_ADA}

    return kartu


async def peta_peran(konteks: KonteksAlat, iddesa: str) -> dict[str, Any]:
    """Baris penuh Peta Peran Desa, apa adanya dari `simpanan.peta_peran_per_desa`.

    Kolom mutu (`keyakinan`, `sumber_dominan`, `alasan_belum_terpetakan`) TIDAK
    boleh disaring — PRD §8 mewajibkannya tetap terlihat sebagai penjaga mutu.
    """
    peta_peran_per_desa = wajib(konteks.simpanan.peta_peran_per_desa, "peta peran")
    baris = peta_peran_per_desa.get(iddesa)
    if baris is None:
        return {"galat": DESA_TIDAK_ADA}
    return baris


async def desa_kembar(konteks: KonteksAlat, iddesa: str) -> dict[str, Any]:
    """Desa Kembar satu desa, tiru `src/desa_kembar/router.py` PERSIS.

    `iddesa` tak dikenal → `DESA_TIDAK_ADA`. Berkas kembar hilang, tanpa
    kunci `desa`, atau desa tanpa vektor fitur BUKAN galat — jalur anggun
    dengan `tetangga` kosong + `keterangan` (keputusan desain fase 3, butir
    6), sama seperti rutenya.
    """
    indeks_per_desa = wajib(konteks.simpanan.indeks_per_desa, "indeks kartu ekonomi")
    baris = indeks_per_desa.get(iddesa)
    if baris is None:
        return {"galat": DESA_TIDAK_ADA}

    idkab = baris["idkab"]
    kembar_kab = await run_in_threadpool(
        baca_kembar_kab, str(konteks.simpanan.dir_data), idkab
    )
    peta_kembar = (kembar_kab or {}).get("desa") or {}
    baris_tetangga = peta_kembar.get(iddesa)

    if baris_tetangga is None:
        return {"iddesa": iddesa, "tetangga": [], "keterangan": KETERANGAN_TANPA_VEKTOR}

    # `.model_dump()`: hasil alat harus JSON-serializable untuk dikirim ke
    # Gemini, `TetanggaKembar` adalah objek Pydantic.
    tetangga = [
        t.model_dump() for t in tetangga_terjoin(baris_tetangga, indeks_per_desa)
    ]
    return {"iddesa": iddesa, "tetangga": tetangga}


async def jalur_ekonomi(
    konteks: KonteksAlat, varian: str, kab: str | None = None
) -> dict[str, Any]:
    """Baris ringkas Jalur Ekonomi satu varian, tiru `ratakan()` + filter `kab`.

    Sertakan `hasil.get("parameter")` di keluaran — rutenya mengisi
    `meta.parameter` dari situ. Dipotong ke `MAKS_BARIS_ALAT`.
    """
    hasil = wajib(
        await run_in_threadpool(baca_jalur, str(konteks.simpanan.dir_data), varian),
        f"jalur ekonomi varian {varian}",
    )
    baris = ratakan(hasil, varian)
    if kab is not None:
        baris = [b for b in baris if b["idkab"] == kab]

    hasil_potong = _potong(baris, MAKS_BARIS_ALAT)
    hasil_potong["parameter"] = hasil.get("parameter")
    return hasil_potong


async def berita_desa(konteks: KonteksAlat, iddesa: str) -> dict[str, Any]:
    """Berita Desa satu desa, dipotong ke `MAKS_BARIS_BERITA`.

    Tiap baris diproyeksikan ke HANYA `{judul, sumber, terbit_pada,
    rangkuman}` — kolom `url` SENGAJA DIBUANG. Rangkuman berita berasal dari
    situs luar (konten tak tepercaya, vektor indirect prompt injection);
    model tidak butuh URL untuk menjawab, dan URL di dalam konteks adalah
    umpan eksfiltrasi paling murah.
    """
    indeks_per_desa = wajib(konteks.simpanan.indeks_per_desa, "indeks kartu ekonomi")
    if iddesa not in indeks_per_desa:
        return {"galat": DESA_TIDAK_ADA}

    try:
        baris = await baris_berita(konteks.klien_supabase, iddesa)
    except GalatAPI as exc:
        return {"galat": exc.kode}

    proyeksi = [
        {
            "judul": b.judul,
            "sumber": b.sumber,
            "terbit_pada": b.terbit_pada.isoformat() if b.terbit_pada else None,
            "rangkuman": b.rangkuman,
        }
        for b in baris
    ]
    return _potong(proyeksi, MAKS_BARIS_BERITA)


async def citra_potensi(konteks: KonteksAlat, prov: str, target: str) -> dict[str, Any]:
    """Detail satu sel Citra Potensi Desa, tiru `src/citra_potensi/router.py::detail_sel`.

    `sel["berkas"]` DARI INDEKS (bukan `target` mentah dari model) dipakai
    untuk membaca berkas produksi — itu yang menutup path traversal, karena
    `target` cuma dipakai mencari sel di indeks, tidak pernah menyusun path
    berkas secara langsung. `ValueError` dari `baca_sel_citra` tetap ditangkap
    sebagai penjaga berlapis, meski jalur utamanya tidak pernah mencapainya.

    `skor` pada data nyata berisi ribuan baris untuk satu sel — dipotong ke
    `MAKS_BARIS_ALAT` teratas berdasar `skor100_dlm_kab` menurun, dengan
    posisi kolomnya DICARI di `format_skor` (bukan diasumsikan indeks tetap
    `1`) — produksi v5 memang seragam, tapi varian ML wisata di
    `data/arsip/` memakai urutan kolom lain, dan `indeks.json` menerbitkan
    `format_skor` justru supaya konsumen tidak menebak urutannya. `nmdesa`
    hasil join dari `simpanan.indeks_per_desa` supaya model tidak perlu
    memanggil `cari_desa` berkali-kali untuk membuat jawabannya terbaca
    manusia.
    """
    citra_indeks = wajib(konteks.simpanan.citra_indeks, "indeks citra potensi")

    sel = next(
        (
            s
            for s in citra_indeks.get("sel", [])
            if s.get("prov") == prov and s.get("target") == target
        ),
        None,
    )
    if sel is None:
        return {"galat": TIDAK_DITEMUKAN}

    try:
        isi = await run_in_threadpool(
            baca_sel_citra, str(konteks.simpanan.dir_data), sel["berkas"]
        )
    except ValueError:
        return {"galat": ARGUMEN_TIDAK_SAH}

    isi = wajib(isi, f"sel citra potensi {sel['berkas']}")
    format_skor = wajib(
        isi.get("format_skor"), f"format skor sel citra potensi {sel['berkas']}"
    )
    skor: dict[str, list[Any]] = wajib(
        isi.get("skor"), f"skor sel citra potensi {sel['berkas']}"
    )

    # `GalatAPI(DATA_BELUM_SIAP, ..., 503)`, bukan `wajib()` langsung -- yang
    # hilang di sini bukan kunci top-level (`wajib()` sudah menjaga itu di
    # atas), tapi satu KOLOM di dalam `format_skor`. Sikapnya tetap sama
    # dengan `wajib()`: artefak cacat = 503, bukan 200 dengan urutan diam-diam
    # salah (lihat docstring fungsi soal varian arsip ML wisata).
    if "skor100_dlm_kab" not in format_skor:
        raise GalatAPI(
            DATA_BELUM_SIAP, f"format skor sel citra potensi {sel['berkas']}", 503
        )
    idx_skor100 = format_skor.index("skor100_dlm_kab")

    indeks_per_desa = konteks.simpanan.indeks_per_desa or {}

    def _nmdesa(iddesa: str) -> str | None:
        identitas = indeks_per_desa.get(iddesa)
        return identitas.get("nmdesa") if identitas else None

    teratas = sorted(skor, key=lambda iddesa: skor[iddesa][idx_skor100], reverse=True)[
        :MAKS_BARIS_ALAT
    ]
    skor_terpotong = {
        iddesa: {"skor": skor[iddesa], "nmdesa": _nmdesa(iddesa)} for iddesa in teratas
    }

    return {
        **sel,
        "format_skor": format_skor,
        "skor": skor_terpotong,
        "total": len(skor),
        "terpotong": len(skor) > MAKS_BARIS_ALAT,
    }


async def wilayah_ringkasan(konteks: KonteksAlat) -> dict[str, Any]:
    """Ringkasan nasional apa adanya dari `simpanan.ringkasan_wilayah`."""
    return wajib(konteks.simpanan.ringkasan_wilayah, "ringkasan wilayah")


def _normalisasi_nama_wilayah(nama: str) -> str:
    """Normalisasi ringan nama wilayah untuk pencocokan substring toleran.

    Menangani variasi penulisan wajar: huruf besar-kecil, spasi berlebih, dan
    awalan administratif "Kabupaten"/"Kab."/"Kota" (`_PREFIKS_ADMINISTRATIF`).
    BUKAN fuzzy matching berat -- typo atau ejaan yang jauh berbeda tidak akan
    cocok. Cukup untuk cakupan lima provinsi MVP, tidak menutup seluruh
    variasi penulisan wilayah Indonesia.
    """
    dinormalisasi = re.sub(r"\s+", " ", nama.strip()).casefold()
    for prefiks in _PREFIKS_ADMINISTRATIF:
        if dinormalisasi.startswith(prefiks):
            return dinormalisasi[len(prefiks) :]
    return dinormalisasi


async def cek_cakupan_wilayah(konteks: KonteksAlat, nama: str) -> dict[str, Any]:
    """Cek keberadaan nama provinsi/kabupaten di `wilayah.json`.

    Pencocokan substring atas nama yang dinormalisasi
    (`_normalisasi_nama_wilayah`) di KEDUA sisi -- query dan kandidat --
    supaya "Kab. Tanggamus", "kab tanggamus", dan "TANGGAMUS" sama-sama
    cocok walau `wilayah.json` menyimpan nama TANPA awalan administratif.

    Tidak ada yang cocok BUKAN galat: `ditemukan: False` disertai daftar
    provinsi yang memang tercakup (dibaca dari `wilayah.json`, bukan
    ditulis literal), supaya model bisa menjawab jujur soal cakupan tanpa
    mengarang nama provinsi.

    Dipotong ke `MAKS_BARIS_ALAT` sekadar jaring pengaman -- `wilayah.json`
    MVP hanya memuat lima provinsi dan puluhan kabupaten, jadi pemotongan
    praktis tidak pernah terjadi kecuali query sangat generik (mis. satu
    kata yang kebetulan cocok di banyak nama kabupaten).
    """
    wilayah = wajib(konteks.simpanan.wilayah, "wilayah")
    kunci = _normalisasi_nama_wilayah(nama)

    provinsi_cocok = [
        {"idprov": p["idprov"], "nama": p["nama"]}
        for p in wilayah["provinsi"]
        if kunci in _normalisasi_nama_wilayah(p["nama"])
    ][:MAKS_BARIS_ALAT]

    peta_nama_provinsi = {p["idprov"]: p["nama"] for p in wilayah["provinsi"]}
    kabupaten_cocok = [
        {
            "idkab": k["idkab"],
            "nmkab": k["nmkab"],
            "idprov": k["idprov"],
            "nmprov": peta_nama_provinsi.get(k["idprov"]),
        }
        for k in wilayah["kabupaten"]
        if kunci in _normalisasi_nama_wilayah(k["nmkab"])
    ][:MAKS_BARIS_ALAT]

    ditemukan = bool(provinsi_cocok or kabupaten_cocok)
    hasil: dict[str, Any] = {
        "ditemukan": ditemukan,
        "provinsi": provinsi_cocok,
        "kabupaten": kabupaten_cocok,
    }
    if not ditemukan:
        hasil["provinsi_tercakup"] = [
            {"idprov": p["idprov"], "nama": p["nama"]} for p in wilayah["provinsi"]
        ]
    return hasil


_ALAT: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "cari_desa": cari_desa,
    "kartu_ekonomi": kartu_ekonomi,
    "peta_peran": peta_peran,
    "desa_kembar": desa_kembar,
    "jalur_ekonomi": jalur_ekonomi,
    "berita_desa": berita_desa,
    "citra_potensi": citra_potensi,
    "wilayah_ringkasan": wilayah_ringkasan,
    "cek_cakupan_wilayah": cek_cakupan_wilayah,
}


async def jalankan_alat(
    nama: str, argumen: dict[str, Any], konteks: KonteksAlat
) -> dict[str, Any]:
    """Eksekusi satu tool call Gemini; galat apa pun kembali sebagai data.

    Nama alat tak dikenal atau argumen tidak sah menolak SEBELUM menyentuh
    `konteks.simpanan`/`konteks.klien_supabase` sama sekali.
    """
    fungsi = _ALAT.get(nama)
    if fungsi is None:
        return {"galat": ALAT_TIDAK_DIKENAL}
    if not _argumen_sah(nama, argumen):
        return {"galat": ARGUMEN_TIDAK_SAH}
    try:
        return await fungsi(konteks, **argumen)
    except GalatAPI as exc:
        return {"galat": exc.kode}
    except (KeyError, IndexError):
        # Artefak ADA tapi kehilangan kunci internal (`baris["idkab"]`,
        # `b["nmdesa"]`, `sel["berkas"]`, `skor[iddesa][1]`) -- sikap yang
        # sama dengan `wajib()` untuk artefak yang cacat, tapi di sini ia
        # jadi DATA (bukan exception yang merambat) karena satu alat gagal
        # tidak boleh menjatuhkan seluruh giliran chat.
        logger.warning("alat %s: kunci artefak hilang", nama, exc_info=True)
        return {"galat": DATA_BELUM_SIAP}
    except (TypeError, ValueError):
        return {"galat": ARGUMEN_TIDAK_SAH}
