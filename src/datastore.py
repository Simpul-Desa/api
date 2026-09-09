"""Lapis data `api/`: manifest, `Simpanan` startup, pembaca LRU, dan dependensinya.

Tidak ada basis data di sini — sumbernya berkas JSON beku hasil build di
`data-salinan/`, jadi berkas ini menempati slot `database.py` panduan
fastapi-best-practices tanpa memakai namanya (lihat ADR-0008). Supabase
diakses lewat HTTP PostgREST dari dalam `src/auth/` dan `src/berita/`, bukan
dari sini.

Dua dependensi rute ikut di berkas ini karena keduanya adalah pintu masuk ke
lapis data: `ambil_simpanan` mengambil `Simpanan` dari state aplikasi, dan
`wajib()` menegakkan ketersediaan artefak — artefak yang belum dimuat
(`data-salinan/` belum dibangun) menghasilkan 503 `DATA_BELUM_SIAP`, bukan
galat server tak terduga.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Request

from src.exceptions import DATA_BELUM_SIAP, GalatAPI

logger = logging.getLogger(__name__)


def muat_manifest(dir_data: Path) -> dict[str, Any] | None:
    """Baca `<dir_data>/manifest.json` dan kembalikan isinya sebagai dict.

    Mengembalikan None bila berkas tidak ada. Bila berkas ada tapi JSON-nya
    korup atau bukan objek JSON, catat peringatan lalu kembalikan None. Fungsi
    ini tidak memvalidasi kunci di dalam manifest — itu tanggung jawab
    pemanggil.
    """
    berkas_manifest = dir_data / "manifest.json"

    if not berkas_manifest.is_file():
        return None

    teks = berkas_manifest.read_text(encoding="utf-8")

    try:
        isi = json.loads(teks)
    except json.JSONDecodeError:
        logger.warning("manifest.json korup, tidak bisa di-parse: %s", berkas_manifest)
        return None

    if not isinstance(isi, dict):
        logger.warning("manifest.json bukan objek JSON: %s", berkas_manifest)
        return None

    return isi


def muat_json_atau_none(path: Path, deskripsi: str) -> Any | None:
    """Baca berkas JSON di `path`; None + peringatan bila hilang atau korup.

    Helper bersama untuk seluruh pemuatan artefak `Simpanan` — startup tidak
    boleh gagal walau satu artefak hilang atau isinya korup.
    """
    if not path.is_file():
        logger.warning("artefak %s tidak ditemukan: %s", deskripsi, path)
        return None

    teks = path.read_text(encoding="utf-8")

    try:
        return json.loads(teks)
    except json.JSONDecodeError:
        logger.warning("artefak %s korup, tidak bisa di-parse: %s", deskripsi, path)
        return None


@dataclass(frozen=True)
class Simpanan:
    """Kumpulan data-salinan/ yang dimuat sekali saat startup aplikasi.

    Setiap field artefak boleh `None` bila berkas sumbernya hilang atau
    korup — lihat `muat_json_atau_none`. `dir_data` selalu terisi (dipakai
    pembaca LRU untuk menyusun path berkas per permintaan).
    """

    wilayah: dict[str, Any] | None
    indeks_kartu: list[dict[str, Any]] | None
    indeks_per_desa: dict[str, dict[str, Any]] | None
    desa_per_kab: dict[str, list[dict[str, Any]]] | None
    peta_peran: list[dict[str, Any]] | None
    peta_peran_per_desa: dict[str, dict[str, Any]] | None
    ringkasan_kab: dict[str, Any] | None
    citra_indeks: dict[str, Any] | None
    ringkasan_wilayah: dict[str, Any] | None
    pusat_wilayah: dict[str, Any] | None
    dir_data: Path


def _indeks_per_desa_dari_baris(
    baris: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Indeks list baris (berkunci `iddesa`) jadi dict, referensi tanpa salin."""
    return {b["iddesa"]: b for b in baris}


def _kelompok_per_kab_dari_baris(
    baris: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Kelompokkan list baris indeks kartu per `idkab`, referensi tanpa salin."""
    hasil: dict[str, list[dict[str, Any]]] = {}
    for b in baris:
        hasil.setdefault(b["idkab"], []).append(b)
    return hasil


def _hitung_ringkasan_wilayah(
    wilayah: dict[str, Any] | None,
    indeks_kartu: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Hitung ringkasan wilayah dari `wilayah.json` + indeks kartu.

    `idprov` tiap baris indeks diturunkan dari `idkab[:2]` (indeks kartu
    tidak punya kolom `idprov` sendiri). None bila salah satu sumber hilang.
    """
    if wilayah is None or indeks_kartu is None:
        return None

    provinsi = wilayah["provinsi"]
    kabupaten = wilayah["kabupaten"]

    per_provinsi = []
    for prov in provinsi:
        idprov = prov["idprov"]
        n_kabupaten = sum(1 for k in kabupaten if k["idprov"] == idprov)
        n_desa = sum(1 for b in indeks_kartu if b["idkab"][:2] == idprov)
        per_provinsi.append(
            {
                "idprov": idprov,
                "nama": prov["nama"],
                "n_kabupaten": n_kabupaten,
                "n_desa": n_desa,
            }
        )

    return {
        "n_provinsi": len(provinsi),
        "n_kabupaten": len(kabupaten),
        "n_desa": len(indeks_kartu),
        "per_provinsi": per_provinsi,
    }


def _hitung_pusat_wilayah(
    pusat_mentah: dict[str, Any] | None,
    wilayah: dict[str, Any] | None,
    desa_per_kab: dict[str, list[dict[str, Any]]] | None,
) -> dict[str, Any] | None:
    """Gabung pusat kabupaten mentah (`pusat_wilayah.json`) dengan `wilayah.json`.

    Tiap kabupaten di `pusat_mentah` digenapi `nmkab`/`idprov` dari
    `wilayah.json` dan `n_desa` dari `desa_per_kab`. Pusat provinsi = rerata
    pusat kabupatennya, `n_desa`/`n_kabupaten` dijumlah dari kabupaten yang
    sama. None bila salah satu sumber belum dimuat, bila `pusat_mentah`
    kehilangan kunci `kabupaten`, atau bila daftar kabupaten hasil rakitan
    (setelah dicocokkan ke `wilayah.json`) kosong — ketiganya berarti tidak
    ada satu pusat pun yang bisa disajikan, jadi rute harus menjawab 503
    `DATA_BELUM_SIAP` lewat `wajib()` (CLAUDE.md api §12), bukan 200 dengan
    `{"provinsi": [], "kabupaten": []}`.

    Kabupaten di `pusat_mentah` yang idkab-nya tak dikenal di `wilayah.json`
    (mis. `pusat_wilayah.json` lebih tua dari `wilayah.json`, build selektif)
    dilewati dengan log peringatan, bukan melempar — data build lama masih
    harus bisa boot. Arah sebaliknya — kabupaten di `wilayah.json` yang TIDAK
    punya entri di `pusat_mentah` — juga dicatat `logger.warning` (selisih
    idkab), bukan dibuang senyap. Provinsi yang seluruh kabupatennya
    dilewati (belum satu pun berpusat, mis. build pertama sebelum langkah
    geo) ikut dilewati dengan log peringatan — tidak ada pusat yang bisa
    dihitung tanpa satu pun kabupaten.
    """
    if pusat_mentah is None or wilayah is None or desa_per_kab is None:
        return None

    kabupaten_wilayah = {k["idkab"]: k for k in wilayah["kabupaten"]}
    baris_pusat = pusat_mentah.get("kabupaten", [])

    idkab_tanpa_pusat = kabupaten_wilayah.keys() - {b["idkab"] for b in baris_pusat}
    if idkab_tanpa_pusat:
        logger.warning(
            "pusat_wilayah.json: %d kabupaten di wilayah.json tanpa entri pusat: %s",
            len(idkab_tanpa_pusat),
            sorted(idkab_tanpa_pusat),
        )

    kabupaten: list[dict[str, Any]] = []
    for baris in baris_pusat:
        idkab = baris["idkab"]
        info_kab = kabupaten_wilayah.get(idkab)
        if info_kab is None:
            logger.warning(
                "pusat_wilayah.json: kabupaten %s tak dikenal di wilayah.json, dilewati",
                idkab,
            )
            continue
        kabupaten.append(
            {
                "idkab": idkab,
                "nmkab": info_kab["nmkab"],
                "idprov": info_kab["idprov"],
                "pusat": baris["pusat"],
                "n_desa": len(desa_per_kab.get(idkab, [])),
            }
        )

    if not kabupaten:
        return None

    provinsi: list[dict[str, Any]] = []
    for prov in wilayah["provinsi"]:
        idprov = prov["idprov"]
        kab_prov = [k for k in kabupaten if k["idprov"] == idprov]
        if not kab_prov:
            logger.warning(
                "pusat wilayah: provinsi %s tanpa satu pun kabupaten berpusat, dilewati",
                idprov,
            )
            continue
        n_kabupaten = len(kab_prov)
        provinsi.append(
            {
                "idprov": idprov,
                "nama": prov["nama"],
                "pusat": [
                    sum(k["pusat"][0] for k in kab_prov) / n_kabupaten,
                    sum(k["pusat"][1] for k in kab_prov) / n_kabupaten,
                ],
                "n_desa": sum(k["n_desa"] for k in kab_prov),
                "n_kabupaten": n_kabupaten,
            }
        )

    return {"provinsi": provinsi, "kabupaten": kabupaten}


def muat_simpanan(dir_data: Path) -> Simpanan:
    """Muat seluruh artefak `Simpanan` dari `dir_data` sekali saat startup.

    Tiap artefak dimuat lewat `muat_json_atau_none` — hilang/korup jadi
    `None`, bukan exception, supaya startup layanan tidak pernah gagal
    karena data-salinan/ belum lengkap.
    """
    wilayah: dict[str, Any] | None = muat_json_atau_none(
        dir_data / "wilayah.json", "wilayah"
    )
    indeks_kartu: list[dict[str, Any]] | None = muat_json_atau_none(
        dir_data / "kartu-ekonomi" / "indeks.json", "indeks kartu ekonomi"
    )
    peta_peran: list[dict[str, Any]] | None = muat_json_atau_none(
        dir_data / "peta-peran" / "peta_peran.json", "peta peran"
    )
    ringkasan_kab: dict[str, Any] | None = muat_json_atau_none(
        dir_data / "peta-peran" / "ringkasan_kab.json", "ringkasan kab peta peran"
    )
    citra_indeks: dict[str, Any] | None = muat_json_atau_none(
        dir_data / "citra-potensi" / "indeks.json", "indeks citra potensi"
    )
    pusat_mentah: dict[str, Any] | None = muat_json_atau_none(
        dir_data / "pusat_wilayah.json", "pusat wilayah"
    )

    indeks_per_desa = (
        _indeks_per_desa_dari_baris(indeks_kartu) if indeks_kartu is not None else None
    )
    desa_per_kab = (
        _kelompok_per_kab_dari_baris(indeks_kartu) if indeks_kartu is not None else None
    )
    peta_peran_per_desa = (
        _indeks_per_desa_dari_baris(peta_peran) if peta_peran is not None else None
    )
    ringkasan_wilayah = _hitung_ringkasan_wilayah(wilayah, indeks_kartu)
    pusat_wilayah = _hitung_pusat_wilayah(pusat_mentah, wilayah, desa_per_kab)

    return Simpanan(
        wilayah=wilayah,
        indeks_kartu=indeks_kartu,
        indeks_per_desa=indeks_per_desa,
        desa_per_kab=desa_per_kab,
        peta_peran=peta_peran,
        peta_peran_per_desa=peta_peran_per_desa,
        ringkasan_kab=ringkasan_kab,
        citra_indeks=citra_indeks,
        ringkasan_wilayah=ringkasan_wilayah,
        pusat_wilayah=pusat_wilayah,
        dir_data=dir_data,
    )


async def ambil_simpanan(request: Request) -> Simpanan:
    """Ambil `Simpanan` yang dimuat lifespan dari `app.state.simpanan`.

    `async` disengaja (praktik 8 panduan): dependensi sinkron dilempar
    FastAPI ke threadpool pada SETIAP permintaan data, padahal fungsi ini
    hanya membaca satu atribut dari state aplikasi.
    """
    simpanan: Simpanan = request.app.state.simpanan
    return simpanan


def wajib[T](nilai: T | None, nama: str) -> T:
    """Kembalikan `nilai` bila terisi; bila None lempar 503 `DATA_BELUM_SIAP`.

    `nama` menyebut artefak yang hilang supaya pesan galat menunjuk akar
    masalah (data-salinan/ belum dibangun) tanpa membocorkan path internal.
    """
    if nilai is None:
        raise GalatAPI(DATA_BELUM_SIAP, f"data {nama} belum dimuat di server", 503)
    return nilai
