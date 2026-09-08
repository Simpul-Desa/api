"""Salin artefak kontrak dan bahan metodologi ke direktori keluaran build.

Modul ini menyalin berkas-berkas sumber (dari `data/` dan akar proyek) ke
`data-salinan/` sesuai kontrak yang didefinisikan di `bangun/konstanta.py`.
Setiap berkas yang disalin dicatat sebagai entri manifest (path, sumber,
sha256, bytes) yang siap dipakai `bangun/manifest.py`.
"""

import logging
import shutil
from pathlib import Path

from bangun.konstanta import AKAR_DATA, ARTEFAK_KONTRAK, BERKAS_METODOLOGI, DIR_KELUARAN

try:
    from bangun.manifest import sha256_berkas
except ImportError:  # pragma: no cover - fallback bila bangun/manifest.py belum ada
    import hashlib

    UKURAN_POTONGAN = 65536

    def sha256_berkas(path: Path) -> str:
        """Hitung digest sha256 heksadesimal dari isi berkas (fallback lokal)."""
        hasher = hashlib.sha256()
        with path.open("rb") as sumber:
            for potongan in iter(lambda: sumber.read(UKURAN_POTONGAN), b""):
                hasher.update(potongan)
        return hasher.hexdigest()


logger = logging.getLogger(__name__)


def _salin_satu(
    sumber: Path, tujuan: Path, dir_keluaran: Path
) -> tuple[dict[str, object], int]:
    """Salin satu berkas dan kembalikan (entri manifest, ukuran bytes)."""
    tujuan.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sumber, tujuan)
    ukuran = tujuan.stat().st_size
    item: dict[str, object] = {
        "path": tujuan.relative_to(dir_keluaran).as_posix(),
        "sumber": sumber.as_posix(),
        "sha256": sha256_berkas(tujuan),
        "bytes": ukuran,
    }
    return item, ukuran


def salin_kontrak(
    akar_data: Path = AKAR_DATA, dir_keluaran: Path = DIR_KELUARAN
) -> list[dict[str, object]]:
    """Salin seluruh artefak `ARTEFAK_KONTRAK` dari `akar_data` ke `dir_keluaran`.

    Entri direktori (mis. folder "kartu") disalin per berkas `*.json` di
    dalamnya; entri berkas tunggal disalin langsung. Sumber yang hilang
    membuat build gagal keras (`ValueError`) karena berarti kontrak README
    akar `data/` tidak lengkap. Mengembalikan daftar entri manifest untuk
    tiap berkas yang disalin.
    """
    entri: list[dict[str, object]] = []
    total_bytes = 0

    for sumber_rel, tujuan_rel in ARTEFAK_KONTRAK:
        sumber = akar_data / sumber_rel
        if not sumber.exists():
            raise ValueError(f"Sumber artefak kontrak tidak ditemukan: {sumber}")

        if sumber.is_dir():
            for berkas_json in sorted(sumber.glob("*.json")):
                item, ukuran = _salin_satu(
                    berkas_json,
                    dir_keluaran / tujuan_rel / berkas_json.name,
                    dir_keluaran,
                )
                entri.append(item)
                total_bytes += ukuran
        else:
            item, ukuran = _salin_satu(sumber, dir_keluaran / tujuan_rel, dir_keluaran)
            entri.append(item)
            total_bytes += ukuran

    logger.info("salin_kontrak: %d berkas, %d bytes", len(entri), total_bytes)
    return entri


def salin_metodologi(
    akar_proyek: Path | None = None, dir_keluaran: Path = DIR_KELUARAN
) -> list[dict[str, object]]:
    """Salin bahan metodologi `BERKAS_METODOLOGI` yang tersedia ke `dir_keluaran/metodologi`.

    Berbeda dari `salin_kontrak`, sumber yang hilang tidak menggagalkan
    build: hanya dicatat sebagai warning lalu dilewati, karena bahan
    metodologi bersifat grounding pelengkap Asisten Desa, bukan kontrak
    data wajib.
    """
    akar = akar_proyek if akar_proyek is not None else AKAR_DATA.parent
    entri: list[dict[str, object]] = []
    total_bytes = 0

    for sumber_rel, tujuan_nama in BERKAS_METODOLOGI:
        sumber = akar / sumber_rel
        if not sumber.exists():
            logger.warning("Bahan metodologi tidak ditemukan, dilewati: %s", sumber)
            continue

        item, ukuran = _salin_satu(
            sumber, dir_keluaran / "metodologi" / tujuan_nama, dir_keluaran
        )
        entri.append(item)
        total_bytes += ukuran

    logger.info("salin_metodologi: %d berkas, %d bytes", len(entri), total_bytes)
    return entri
