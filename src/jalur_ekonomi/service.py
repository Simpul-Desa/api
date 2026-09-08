"""Perataan grup Jalur Ekonomi lintas 4 varian + pencarian grup per `id_jalur`.

Fungsi murni (tanpa FastAPI, tanpa I/O) yang mengubah struktur
`jalur-ekonomi/hasil_*.json` (beda bentuk per varian — lihat bagian "Bentuk
artefak data-salinan/" di rencana `fase-3-endpoint-baca.plan.md`) menjadi:

- `ratakan`: baris ringkas seragam untuk daftar (lintas seluruh kabupaten).
- `cari_grup`: grup utuh (apa adanya + `id_jalur`) untuk detail.
- `anggota_iddesa`: kumpulan `iddesa` satu grup (poros + anggota), dipakai
  router untuk filter `?iddesa=`.

Skema `id_jalur` deterministik dari urutan berkas beku — lihat Keputusan
Desain 3 rencana fase 3. `n` dalam skema mulai dari 1 dan diberi ulang per
konteks (per target komoditas, atau per kabupaten untuk varian lain).
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.config import ambil_pengaturan
from src.datastore import muat_json_atau_none
from src.jalur_ekonomi.constants import (
    BERKAS_JALUR_PER_VARIAN,
    KUNCI_ANGGOTA_PER_VARIAN,
)

logger = logging.getLogger(__name__)


def _lewati(id_jalur: str, exc: Exception) -> None:
    """Catat satu grup yang dilewati karena kunci artefak tidak lengkap.

    Satu grup cacat TIDAK boleh menjatuhkan seluruh daftar varian jadi 500 —
    tapi juga tidak boleh hilang tanpa jejak, karena selisih cacah antara
    berkas dan respons adalah satu-satunya petunjuk bahwa build datanya
    cacat.
    """
    logger.warning(
        "grup jalur ekonomi %s dilewati, kunci artefak tidak lengkap: %r",
        id_jalur,
        exc,
    )


def _poros_dari(identitas: dict[str, Any]) -> dict[str, Any]:
    """Susun blok `poros` ringkas: `iddesa`+`nmdesa` wajib, `nmkec` bila ada."""
    poros: dict[str, Any] = {
        "iddesa": identitas["iddesa"],
        "nmdesa": identitas["nmdesa"],
    }
    if "nmkec" in identitas:
        poros["nmkec"] = identitas["nmkec"]
    return poros


def _baris_ringkas(
    idkab: str,
    nmkab: str,
    id_jalur: str,
    *,
    poros: dict[str, Any],
    n_anggota: int,
    bobot: float,
    label: str,
) -> dict[str, Any]:
    """Susun satu baris ringkas seragam `{id_jalur, idkab, nmkab, poros, ...}`."""
    return {
        "id_jalur": id_jalur,
        "idkab": idkab,
        "nmkab": nmkab,
        "poros": _poros_dari(poros),
        "n_anggota": n_anggota,
        "bobot": bobot,
        "label": label,
    }


_Grup = tuple[
    str, dict[str, Any], dict[str, Any]
]  # (id_jalur, baris_ringkas, grup_mentah)


def _grup_komoditas(idkab: str, nmkab: str, kab_isi: dict[str, Any]) -> list[_Grup]:
    """Grup varian komoditas: `id_jalur = {idkab}-{target}-{n}`, `n` per target."""
    keluar: list[_Grup] = []
    for target, isi_target in kab_isi.get("komoditas", {}).items():
        for n, grup in enumerate(isi_target.get("sejalur", []), start=1):
            id_jalur = f"{idkab}-{target}-{n}"
            try:
                baris = _baris_ringkas(
                    idkab,
                    nmkab,
                    id_jalur,
                    poros=grup["poros"],
                    n_anggota=grup["n_anggota"],
                    bobot=grup["volume"],
                    label=isi_target["nama"],
                )
            except (KeyError, TypeError) as exc:
                _lewati(id_jalur, exc)
                continue
            keluar.append((id_jalur, baris, grup))
    return keluar


def _grup_gudang(idkab: str, nmkab: str, kab_isi: dict[str, Any]) -> list[_Grup]:
    """Grup varian gudang-kopdes: `id_jalur = {idkab}-gudang-{n}`."""
    keluar: list[_Grup] = []
    for n, grup in enumerate(kab_isi.get("gudang", []), start=1):
        id_jalur = f"{idkab}-gudang-{n}"
        try:
            baris = _baris_ringkas(
                idkab,
                nmkab,
                id_jalur,
                poros=grup["lokasi"],
                n_anggota=grup["n_desa_layanan"],
                bobot=grup["volume"],
                label="gudang",
            )
        except (KeyError, TypeError) as exc:
            _lewati(id_jalur, exc)
            continue
        keluar.append((id_jalur, baris, grup))
    return keluar


def _grup_cold_storage(idkab: str, nmkab: str, kab_isi: dict[str, Any]) -> list[_Grup]:
    """Grup varian cold-storage: `cs_baru` lalu `cs_eksisting`, id per kabupaten."""
    keluar: list[_Grup] = []

    for n, grup in enumerate(kab_isi.get("cs_baru", []), start=1):
        id_jalur = f"{idkab}-cs-baru-{n}"
        try:
            baris = _baris_ringkas(
                idkab,
                nmkab,
                id_jalur,
                poros=grup["lokasi"],
                n_anggota=grup["n_desa_layanan"],
                bobot=grup["volume"],
                label="cs-baru",
            )
        except (KeyError, TypeError) as exc:
            _lewati(id_jalur, exc)
            continue
        keluar.append((id_jalur, baris, grup))

    for n, grup in enumerate(kab_isi.get("cs_eksisting", []), start=1):
        id_jalur = f"{idkab}-cs-eksisting-{n}"
        try:
            baris = _baris_ringkas(
                idkab,
                nmkab,
                id_jalur,
                poros=grup,
                n_anggota=grup["n_desa_layanan"],
                bobot=grup["kapasitas_ton"],
                label="cs-eksisting",
            )
        except (KeyError, TypeError) as exc:
            _lewati(id_jalur, exc)
            continue
        keluar.append((id_jalur, baris, grup))

    return keluar


def _grup_wisata(idkab: str, nmkab: str, kab_isi: dict[str, Any]) -> list[_Grup]:
    """Grup varian wisata: `id_jalur = {idkab}-kawasan-{n}`, label = kategori basis."""
    keluar: list[_Grup] = []
    for n, grup in enumerate(kab_isi.get("kawasan", []), start=1):
        id_jalur = f"{idkab}-kawasan-{n}"
        try:
            basis = grup["basis"]
            baris = _baris_ringkas(
                idkab,
                nmkab,
                id_jalur,
                poros=basis,
                n_anggota=grup["n_desa"],
                bobot=grup["bobot"],
                label=basis["kategori"],
            )
        except (KeyError, TypeError) as exc:
            _lewati(id_jalur, exc)
            continue
        keluar.append((id_jalur, baris, grup))
    return keluar


_PEMBANGUN_PER_VARIAN = {
    "komoditas": _grup_komoditas,
    "gudang-kopdes": _grup_gudang,
    "cold-storage": _grup_cold_storage,
    "wisata": _grup_wisata,
}


def _iterasi_grup(hasil: dict[str, Any], varian: str) -> list[_Grup]:
    """Iterasi seluruh grup varian `varian`, urut `idkab` lalu urutan berkas."""
    pembangun = _PEMBANGUN_PER_VARIAN[varian]
    kabupaten: dict[str, Any] = hasil.get("kabupaten", {})

    keluar: list[_Grup] = []
    for idkab in sorted(kabupaten):
        kab_isi = kabupaten[idkab]
        if not isinstance(kab_isi, dict):
            # Nilai kabupaten yang bukan objek tidak punya grup apa pun untuk
            # dibaca; melewatinya menjaga kabupaten lain tetap tersaji.
            logger.warning(
                "isi kabupaten %s pada varian %s bukan objek, dilewati", idkab, varian
            )
            continue
        nmkab = kab_isi.get("nmkab", "")
        keluar.extend(pembangun(idkab, nmkab, kab_isi))
    return keluar


def ratakan(hasil: dict[str, Any], varian: str) -> list[dict[str, Any]]:
    """Ratakan `hasil` jadi baris ringkas seragam, lintas seluruh kabupaten.

    Baris: `{id_jalur, idkab, nmkab, poros, n_anggota, bobot, label}`, urut
    `idkab` lalu urutan list dalam berkas. Kabupaten `TAK_LAYAK` (list kosong,
    mis. cold-storage) tidak menyumbang baris apa pun — bukan galat.
    """
    return [baris for _, baris, _ in _iterasi_grup(hasil, varian)]


def cari_grup(
    hasil: dict[str, Any], varian: str, id_jalur: str
) -> dict[str, Any] | None:
    """Cari satu grup utuh berdasar `id_jalur`; None bila tak ditemukan.

    Grup dikembalikan apa adanya (salinan dangkal — objek sumber tidak
    dimutasi) plus kunci tambahan `id_jalur`.
    """
    for id_grup, _, grup_mentah in _iterasi_grup(hasil, varian):
        if id_grup == id_jalur:
            return {**grup_mentah, "id_jalur": id_jalur}
    return None


def anggota_iddesa(grup: dict[str, Any], varian: str) -> set[str]:
    """Kumpulan `iddesa` satu grup: poros/lokasi/basis/diri-sendiri + anggota.

    Kunci poros dideteksi dari bentuk `grup` sendiri (`poros`/`lokasi`/
    `basis`, atau `grup` itu sendiri untuk baris `cs_eksisting`) karena
    varian cold-storage punya dua bentuk grup berbeda. Kunci daftar anggota
    (`anggota`/`desa_layanan`/`desa`) ditentukan oleh `varian`.
    """
    anggota: set[str] = set()

    # `.get` berantai: blok poros tanpa `iddesa` tidak menyumbang anggota,
    # bukan melempar KeyError yang membuat filter `?iddesa=` jadi 500.
    if "poros" in grup:
        poros_id = (grup.get("poros") or {}).get("iddesa")
    elif "lokasi" in grup:
        poros_id = (grup.get("lokasi") or {}).get("iddesa")
    elif "basis" in grup:
        poros_id = (grup.get("basis") or {}).get("iddesa")
    else:
        poros_id = grup.get("iddesa")
    if poros_id is not None:
        anggota.add(poros_id)

    kunci_anggota = KUNCI_ANGGOTA_PER_VARIAN[varian]
    for anggota_item in grup.get(kunci_anggota, []):
        anggota_id = (anggota_item or {}).get("iddesa")
        if anggota_id is not None:
            anggota.add(anggota_id)

    return anggota


@lru_cache(maxsize=ambil_pengaturan().maks_cache_jalur)
def baca_jalur(dir_data_str: str, varian: str) -> dict[str, Any] | None:
    """Baca `jalur-ekonomi/hasil_<varian>.json` sesuai peta varian→berkas.

    Hasil di-cache LRU (`MAKS_CACHE_JALUR`, bawaan 4 = jumlah varian).
    None bila `varian` tak
    dikenal atau berkasnya hilang/korup.
    """
    nama_berkas = BERKAS_JALUR_PER_VARIAN.get(varian)
    if nama_berkas is None:
        logger.warning("varian jalur ekonomi tak dikenal: %s", varian)
        return None

    path = Path(dir_data_str) / "jalur-ekonomi" / nama_berkas
    return muat_json_atau_none(path, f"jalur ekonomi varian {varian}")
