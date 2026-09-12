"""Logika Laporan Desa: merakit isi laporan dari kartu ekonomi + peta peran.

Fungsi murni — tanpa FastAPI, tanpa I/O. Merender `RingkasanLaporan`
(`src/laporan/schemas.py`) dari satu objek `kartu` (kartu-ekonomi/kartu/
<idkab>.json) dan satu baris penuh `pp` (peta-peran/peta_peran.json);
`pdf.py` yang merender model ini jadi byte PDF.
"""

import math
from typing import Any

from src.citra_potensi.service import baca_sel_citra
from src.laporan.constants import JUDUL_SEKSI, KOORDINAT_PLACEHOLDER, NILAI_KOSONG
from src.laporan.schemas import BarisNilai, RingkasanLaporan, SeksiRingkas, SeksiTabel


def _teks(nilai: Any) -> str:
    """Ubah nilai mentah JSON jadi teks tampilan.

    Tidak memformat angka (koma desimal, titik ribuan) - PRD §6
    menyerahkan konvensi tampilan itu sepenuhnya ke `app/`, jadi angka
    lewat apa adanya lewat `str()`. `bool` dicek SEBELUM `int` karena
    `bool` adalah subkelas `int` di Python.
    """
    if isinstance(nilai, bool):
        return "ya" if nilai else "tidak"
    if nilai is None or nilai == "":
        return NILAI_KOSONG
    if isinstance(nilai, list):
        if not nilai:
            return NILAI_KOSONG
        return ", ".join(str(butir) for butir in nilai)
    return str(nilai)


def _koordinat(identitas: dict[str, Any]) -> str:
    """Render `lat`/`lon` identitas, saring placeholder Kemenparekraf.

    Penyaringan pakai `math.isclose`, bukan `==`: kesetaraan float persis
    cuma cocok kalau nilai upstream serialize byte-identik dengan literal
    di `constants.py`. Placeholder ini sudah tiga kali menyesatkan proyek
    lewat kode wilayah klaim sumber eksternal (`../CLAUDE.md`) — pengerasan
    ini, bukan bug yang sudah terjadi (data saat ini nol kecocokan).
    """
    lat = identitas.get("lat")
    lon = identitas.get("lon")
    if lat is None or lon is None:
        return NILAI_KOSONG
    lat_placeholder, lon_placeholder = KOORDINAT_PLACEHOLDER
    if math.isclose(lat, lat_placeholder, abs_tol=1e-6) and math.isclose(
        lon, lon_placeholder, abs_tol=1e-6
    ):
        return "tidak tersedia"
    return f"{_teks(lat)}, {_teks(lon)}"


def _gabung(sumber: dict[str, Any], kunci_menit: str, kunci_tempat: str) -> str:
    menit = sumber.get(kunci_menit)
    tempat = sumber.get(kunci_tempat)
    if menit is None and tempat is None:
        return NILAI_KOSONG
    if tempat:
        return f"{_teks(menit)} ({_teks(tempat)})"
    return _teks(menit)


def _seksi_detail_peta_peran(kartu: dict[str, Any], pp: dict[str, Any]) -> SeksiRingkas:
    """`pp` = baris penuh `peta_peran.json`; `kartu['peta_peran']` cuma
    dipakai untuk peringkat kabupaten."""
    peringkat = kartu.get("peta_peran") or {}
    return SeksiRingkas(
        judul=JUDUL_SEKSI[0],
        baris=[
            BarisNilai(label="Zona", nilai=_teks(pp.get("zona"))),
            BarisNilai(label="Nomor zona", nilai=_teks(pp.get("nomor_zona"))),
            BarisNilai(label="Keyakinan", nilai=_teks(pp.get("keyakinan"))),
            BarisNilai(
                label="Alasan Belum Terpetakan",
                nilai=_teks(pp.get("alasan_belum_terpetakan")),
            ),
            BarisNilai(label="Skor Potensi (SP)", nilai=_teks(pp.get("SP"))),
            BarisNilai(label="Skor Kesiapan (SK)", nilai=_teks(pp.get("SK"))),
            BarisNilai(
                label="Desil SP/SK",
                nilai=f"{_teks(pp.get('desil_sp'))} / {_teks(pp.get('desil_sk'))}",
            ),
            BarisNilai(
                label="Peringkat dalam kabupaten",
                nilai=(
                    f"{_teks(peringkat.get('peringkat_sp_kab'))} / "
                    f"{_teks(peringkat.get('peringkat_sk_kab'))}"
                ),
            ),
            BarisNilai(
                label="Ambang SP/SK",
                nilai=f"{_teks(pp.get('ambang_sp'))} / {_teks(pp.get('ambang_sk'))}",
            ),
            BarisNilai(label="Jarak ke ambang", nilai=_teks(pp.get("jarak_ke_ambang"))),
            BarisNilai(label="Kelengkapan bukti SK", nilai=_teks(pp.get("kelengkapan_sk"))),
        ],
    )



def _seksi_potensi(kartu: dict[str, Any]) -> tuple[SeksiRingkas, SeksiTabel | None]:
    potensi = kartu.get("potensi") or {}
    ringkas = SeksiRingkas(
        judul=JUDUL_SEKSI[2],
        baris=[
            BarisNilai(label="Dominan", nilai=_teks(potensi.get("dominan"))),
            BarisNilai(
                label="Sumber Potensi Dominan",
                nilai=_teks(potensi.get("sumber_dominan")),
            ),
            BarisNilai(label="Detail", nilai=_teks(potensi.get("detail_dominan"))),
        ],
    )
    sub_skor = potensi.get("sub_skor") or {}
    if not sub_skor:
        return ringkas, None
    # Kolom "Keterangan" membawa kode kosong (`TIDAK-BERLAKU`,
    # `TIDAK-DINILAI`, dsb.) apa adanya. PRD bagian 8 menyebut kode kosong
    # sebagai kolom mutu yang TIDAK PERNAH boleh disaring: tanpa kolom ini
    # subsektor tanpa skor cuma tampil "-" dan pembaca tidak tahu apakah
    # datanya hilang atau memang tidak berlaku untuk desa itu.
    tabel = SeksiTabel(
        judul=JUDUL_SEKSI[1],
        kepala=["Subsektor", "Skor", "Keterangan"],
        baris=[
            [
                _teks((butir or {}).get("label")),
                _teks((butir or {}).get("persentil")),
                _teks((butir or {}).get("kosong")),
            ]
            for butir in sub_skor.values()
        ],
    )
    return ringkas, tabel


def _seksi_kartu_ekonomi_profil(
    kartu: dict[str, Any], pp: dict[str, Any]
) -> SeksiRingkas:
    identitas = kartu.get("identitas") or {}
    logistik = kartu.get("logistik") or {}
    return SeksiRingkas(
        judul=JUDUL_SEKSI[1],
        baris=[
            BarisNilai(label="Tipe", nilai=_teks(identitas.get("tipe"))),
            BarisNilai(label="Kode desa", nilai=_teks(identitas.get("iddesa"))),
            BarisNilai(label="Kode Dagri", nilai=_teks(identitas.get("kode_dagri"))),
            BarisNilai(label="Luas (km2)", nilai=_teks(identitas.get("luas_km2"))),
            BarisNilai(label="Koordinat", nilai=_koordinat(identitas)),
            BarisNilai(
                label="IDM",
                nilai=f"{_teks(pp.get('idm'))} ({_teks(pp.get('idm_status'))})",
            ),
            BarisNilai(
                label="Menit ke pusat kota",
                nilai=_gabung(logistik, "menit_ke_pusat_kota", "pusat_kota"),
            ),
            BarisNilai(
                label="Menit ke bandara",
                nilai=_gabung(logistik, "menit_ke_bandara", "bandara"),
            ),
            BarisNilai(
                label="Menit ke pelabuhan",
                nilai=_gabung(logistik, "menit_ke_pelabuhan", "pelabuhan"),
            ),
            BarisNilai(
                label="Sentralitas (menit)", nilai=_teks(pp.get("sentralitas_menit"))
            ),
        ],
    )


def _seksi_kartu_ekonomi_subsektor(kartu: dict[str, Any]) -> SeksiTabel | None:
    potensi = kartu.get("potensi") or {}
    sub_skor = potensi.get("sub_skor") or {}
    if not sub_skor:
        return None
    return SeksiTabel(
        judul=JUDUL_SEKSI[1],
        kepala=["Subsektor", "Skor", "Keterangan"],
        baris=[
            [
                _teks((butir or {}).get("label")),
                _teks((butir or {}).get("persentil")),
                _teks((butir or {}).get("kosong")),
            ]
            for butir in sub_skor.values()
        ],
    )


def _seksi_rekomendasi(kartu: dict[str, Any]) -> SeksiRingkas:
    return SeksiRingkas(
        judul=JUDUL_SEKSI[1],
        baris=[
            BarisNilai(label="Rekomendasi", nilai=_teks(kartu.get("rekomendasi_aksi")))
        ],
    )


def cari_citra_unggulan(
    iddesa: str,
    idkab: str,
    dir_data_str: str | None = None,
    citra_indeks: dict[str, Any] | None = None,
    potensi: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Cari komoditas citra potensi paling unggul untuk desa ini."""
    if potensi and potensi.get("detail_dominan") and potensi.get("sumber_dominan") == "citra":
        dd = dict(potensi["detail_dominan"])
        dominan_teks = str(potensi.get("dominan") or "")
        subsektor = dominan_teks.split("—")[0].strip() if "—" in dominan_teks else ""
        dd.setdefault("subsektor", subsektor)
        return dd

    if not citra_indeks or not dir_data_str:
        if potensi and potensi.get("detail_dominan"):
            return dict(potensi["detail_dominan"])
        return None

    prov = iddesa[:2]
    kandidat: list[dict[str, Any]] = []
    for s in citra_indeks.get("sel", []):
        if s.get("prov") != prov:
            continue
        isi = baca_sel_citra(dir_data_str, s.get("berkas", ""))
        if not isi or "skor" not in isi or iddesa not in isi["skor"]:
            continue
        fmt = isi.get("format_skor", [])
        if "skor100_dlm_kab" not in fmt:
            continue
        idx_skor = fmt.index("skor100_dlm_kab")
        idx_rank = fmt.index("peringkat_dlm_kab") if "peringkat_dlm_kab" in fmt else -1
        idx_n = fmt.index("n_desa_kab") if "n_desa_kab" in fmt else -1
        val = isi["skor"][iddesa]
        skor100 = val[idx_skor]
        rank = val[idx_rank] if idx_rank != -1 else 0
        n_desa = val[idx_n] if idx_n != -1 else 0
        kandidat.append(
            {
                "komoditas": s.get("nama", "").strip(),
                "subsektor": s.get("subsektor", ""),
                "skor100": skor100,
                "peringkat_dlm_kab": rank,
                "n_desa_kab": n_desa,
                "ap_sel": s.get("ap_uji_tertahan"),
                "sumber": "Citra Potensi Desa v5 (analisis spasial satelit & AI)",
            }
        )

    if not kandidat:
        if potensi and potensi.get("detail_dominan"):
            return dict(potensi["detail_dominan"])
        return None

    kandidat.sort(key=lambda x: (-x["skor100"], x["peringkat_dlm_kab"]))
    return kandidat[0]


def _seksi_citra_potensi(
    kartu: dict[str, Any], citra_unggulan: dict[str, Any] | None
) -> SeksiRingkas:
    potensi = kartu.get("potensi") or {}
    citra = citra_unggulan or potensi.get("detail_dominan")
    if not citra:
        return SeksiRingkas(
            judul=JUDUL_SEKSI[2],
            baris=[
                BarisNilai(label="Komoditas Unggulan", nilai="tidak ada"),
                BarisNilai(
                    label="Sumber Model",
                    nilai=_teks(potensi.get("sumber_dominan")),
                ),
            ],
        )

    peringkat_teks = (
        f"Peringkat {_teks(citra.get('peringkat_dlm_kab'))} dari {_teks(citra.get('n_desa_kab'))} desa"
        if citra.get("peringkat_dlm_kab") is not None
        else NILAI_KOSONG
    )
    skor_teks = (
        f"{_teks(citra.get('skor100'))} / 100"
        if citra.get("skor100") is not None
        else NILAI_KOSONG
    )
    sumber = citra.get("sumber") or potensi.get("sumber_dominan")

    return SeksiRingkas(
        judul=JUDUL_SEKSI[2],
        baris=[
            BarisNilai(label="Komoditas Unggulan", nilai=_teks(citra.get("komoditas"))),
            BarisNilai(label="Subsektor", nilai=_teks(citra.get("subsektor"))),
            BarisNilai(label="Skor Citra Potensi", nilai=skor_teks),
            BarisNilai(label="Peringkat dalam kabupaten", nilai=peringkat_teks),
            BarisNilai(label="Akurasi Model (AP)", nilai=_teks(citra.get("ap_sel"))),
            BarisNilai(label="Sumber Model", nilai=_teks(sumber)),
        ],
    )


def _seksi_desa_kembar(kartu: dict[str, Any]) -> SeksiTabel | SeksiRingkas:
    desa_kembar = kartu.get("desa_kembar") or []
    if not desa_kembar:
        return SeksiRingkas(
            judul=JUDUL_SEKSI[3],
            baris=[BarisNilai(label="Desa Kembar", nilai="tidak ada")],
        )
    return SeksiTabel(
        judul=JUDUL_SEKSI[3],
        kepala=["Kode desa", "Nama", "Kecamatan", "Kemiripan", "Zona"],
        baris=[
            [
                _teks((entri or {}).get("iddesa")),
                _teks((entri or {}).get("nmdesa")),
                _teks((entri or {}).get("nmkec")),
                _teks((entri or {}).get("kemiripan")),
                _teks((entri or {}).get("zona")),
            ]
            for entri in desa_kembar
        ],
    )


def rakit_ringkasan(
    kartu: dict[str, Any],
    pp: dict[str, Any],
    manifest: dict[str, Any] | None,
    nama_provinsi: str | None = None,
    citra_unggulan: dict[str, Any] | None = None,
) -> RingkasanLaporan:
    """Rakit Laporan Desa komprehensif: Detail Peta Peran, Kartu Ekonomi Desa,
    Citra Potensi Unggulan, dan Desa Kembar."""
    identitas = kartu.get("identitas") or {}
    judul = f"LAPORAN DESA — {_teks(identitas.get('nama'))}"
    provinsi = nama_provinsi or identitas.get("provinsi")
    subjudul = (
        f"{_teks(identitas.get('kecamatan'))}, {_teks(identitas.get('kabupaten'))}, "
        f"{_teks(provinsi)} · {_teks(identitas.get('iddesa'))}"
    )

    if citra_unggulan is None:
        citra_unggulan = cari_citra_unggulan(
            str(identitas.get("iddesa") or ""),
            str(identitas.get("iddesa") or "")[:4],
            potensi=kartu.get("potensi"),
        )

    seksi: list[SeksiRingkas | SeksiTabel] = [
        _seksi_detail_peta_peran(kartu, pp),
        _seksi_kartu_ekonomi_profil(kartu, pp),
    ]
    tabel_subsektor = _seksi_kartu_ekonomi_subsektor(kartu)
    if tabel_subsektor is not None:
        seksi.append(tabel_subsektor)
    seksi.append(_seksi_rekomendasi(kartu))
    seksi.append(_seksi_citra_potensi(kartu, citra_unggulan))
    seksi.append(_seksi_desa_kembar(kartu))

    if manifest is None:
        info_build = "data build tidak diketahui"
    else:
        hash_singkat = _teks(manifest.get("hash"))[:12]
        tanggal = _teks(manifest.get("tanggal"))
        info_build = f"data build {hash_singkat} ({tanggal})"
    catatan_kaki = (
        f"SIMPUL DESA — {info_build}. Analisis spasial & ekonomi pedesaan terpadu."
    )

    return RingkasanLaporan(
        judul=judul,
        subjudul=subjudul,
        seksi=seksi,
        catatan_kaki=catatan_kaki,
        identitas=identitas,
        peta_peran=pp,
        potensi=kartu.get("potensi") or {},
        citra_unggulan=citra_unggulan,
        desa_kembar=kartu.get("desa_kembar") or [],
        rekomendasi_aksi=_teks(kartu.get("rekomendasi_aksi")),
    )

