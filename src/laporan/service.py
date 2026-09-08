"""Logika Laporan Desa: merakit isi laporan dari kartu ekonomi + peta peran.

Fungsi murni — tanpa FastAPI, tanpa I/O. Merender `RingkasanLaporan`
(`src/laporan/schemas.py`) dari satu objek `kartu` (kartu-ekonomi/kartu/
<idkab>.json) dan satu baris penuh `pp` (peta-peran/peta_peran.json);
`pdf.py` yang merender model ini jadi byte PDF.
"""

import math
from typing import Any

from src.laporan.constants import JUDUL_SEKSI, KOORDINAT_PLACEHOLDER, NILAI_KOSONG
from src.laporan.schemas import BarisNilai, RingkasanLaporan, SeksiRingkas, SeksiTabel

# Urutan dan kunci baris seksi Fakta Program — "apa adanya", label = nama
# kunci mentah `kartu.fakta_program` (tabel "Isi laporan" rencana fase 8).
_KUNCI_FAKTA_PROGRAM: tuple[str, ...] = (
    "jadesta",
    "desa_wisata_sisparnas",
    "n_daya_tarik_wisata",
    "kampung_budidaya",
    "kampung_nelayan",
    "cold_storage_eksisting",
    "cold_storage_terlayani",
    "belum_tersentuh",
    "catatan",
)


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


def _seksi_identitas(kartu: dict[str, Any]) -> SeksiRingkas:
    identitas = kartu.get("identitas") or {}
    return SeksiRingkas(
        judul=JUDUL_SEKSI[0],
        baris=[
            BarisNilai(label="Kode desa", nilai=_teks(identitas.get("iddesa"))),
            BarisNilai(label="Kode Dagri", nilai=_teks(identitas.get("kode_dagri"))),
            BarisNilai(label="Tipe", nilai=_teks(identitas.get("tipe"))),
            BarisNilai(label="Luas (km2)", nilai=_teks(identitas.get("luas_km2"))),
            BarisNilai(label="Koordinat", nilai=_koordinat(identitas)),
        ],
    )


def _seksi_peta_peran(kartu: dict[str, Any], pp: dict[str, Any]) -> SeksiRingkas:
    """`pp` = baris penuh `peta_peran.json`; `kartu["peta_peran"]` cuma
    dipakai untuk peringkat kabupaten — dua bentuk BEDA, jangan tertukar."""
    peringkat = kartu.get("peta_peran") or {}
    return SeksiRingkas(
        judul=JUDUL_SEKSI[1],
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
        judul=JUDUL_SEKSI[2],
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


def _seksi_kesiapan(kartu: dict[str, Any], pp: dict[str, Any]) -> SeksiRingkas:
    kesiapan = kartu.get("kesiapan") or {}
    return SeksiRingkas(
        judul=JUDUL_SEKSI[3],
        baris=[
            BarisNilai(
                label="Kelengkapan bukti SK", nilai=_teks(pp.get("kelengkapan_sk"))
            ),
            BarisNilai(
                label="Komponen hilang", nilai=_teks(pp.get("komponen_sk_hilang"))
            ),
            BarisNilai(
                label="IDM",
                nilai=f"{_teks(pp.get('idm'))} ({_teks(pp.get('idm_status'))})",
            ),
            BarisNilai(label="Kelembagaan", nilai=_teks(kesiapan.get("kelembagaan"))),
            BarisNilai(
                label="Amenitas (POI)", nilai=_teks(kesiapan.get("amenitas_poi"))
            ),
            BarisNilai(
                label="Infrastruktur per 1000 ruta",
                nilai=_teks(pp.get("infra_per_1000_ruta")),
            ),
        ],
    )


def _seksi_logistik(kartu: dict[str, Any], pp: dict[str, Any]) -> SeksiRingkas:
    logistik = kartu.get("logistik") or {}

    def _gabung(kunci_menit: str, kunci_tempat: str) -> str:
        return (
            f"{_teks(logistik.get(kunci_menit))} "
            f"({_teks(logistik.get(kunci_tempat))})"
        )

    return SeksiRingkas(
        judul=JUDUL_SEKSI[4],
        baris=[
            BarisNilai(
                label="Menit ke pusat kota",
                nilai=_gabung("menit_ke_pusat_kota", "pusat_kota"),
            ),
            BarisNilai(
                label="Menit ke bandara",
                nilai=_gabung("menit_ke_bandara", "bandara"),
            ),
            BarisNilai(
                label="Menit ke pelabuhan",
                nilai=_gabung("menit_ke_pelabuhan", "pelabuhan"),
            ),
            BarisNilai(
                label="Sentralitas (menit)", nilai=_teks(pp.get("sentralitas_menit"))
            ),
        ],
    )


def _seksi_desa_kembar(kartu: dict[str, Any]) -> SeksiTabel | SeksiRingkas:
    desa_kembar = kartu.get("desa_kembar") or []
    if not desa_kembar:
        return SeksiRingkas(
            judul=JUDUL_SEKSI[5],
            baris=[BarisNilai(label="Desa Kembar", nilai="tidak ada")],
        )
    return SeksiTabel(
        judul=JUDUL_SEKSI[5],
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


def _seksi_fakta_program(kartu: dict[str, Any]) -> SeksiRingkas:
    fakta = kartu.get("fakta_program") or {}
    return SeksiRingkas(
        judul=JUDUL_SEKSI[6],
        baris=[
            BarisNilai(label=kunci, nilai=_teks(fakta.get(kunci)))
            for kunci in _KUNCI_FAKTA_PROGRAM
        ],
    )


def _seksi_rekomendasi(kartu: dict[str, Any]) -> SeksiRingkas:
    return SeksiRingkas(
        judul=JUDUL_SEKSI[7],
        baris=[
            BarisNilai(label="Rekomendasi", nilai=_teks(kartu.get("rekomendasi_aksi")))
        ],
    )


def _seksi_mutu(kartu: dict[str, Any]) -> SeksiRingkas:
    mutu = kartu.get("mutu_data") or {}
    return SeksiRingkas(
        judul=JUDUL_SEKSI[8],
        baris=[
            BarisNilai(label="Punya geometri", nilai=_teks(mutu.get("punya_geometri"))),
            BarisNilai(label="Punya ST2023", nilai=_teks(mutu.get("punya_st2023"))),
            BarisNilai(label="Punya IDM", nilai=_teks(mutu.get("punya_idm"))),
            BarisNilai(
                label="Kelengkapan bukti SK",
                nilai=_teks(mutu.get("kelengkapan_bukti_sk")),
            ),
        ],
    )


def rakit_ringkasan(
    kartu: dict[str, Any],
    pp: dict[str, Any],
    manifest: dict[str, Any] | None,
    nama_provinsi: str | None = None,
) -> RingkasanLaporan:
    """Rakit kesembilan seksi Laporan Desa dari satu `kartu` + satu baris
    penuh `pp`. Sumber tiap label mengikuti tabel "Isi laporan" di rencana
    fase 8 persis - tidak menebak. Seksi "Potensi Dominan" bisa terdiri
    dari dua entri berurutan (ringkas lalu tabel sub-skor) berbagi judul
    yang sama, karena satu `Seksi` cuma bisa satu jenis."""
    identitas = kartu.get("identitas") or {}
    judul = f"LAPORAN DESA — {_teks(identitas.get('nama'))}"
    # `identitas.provinsi` di kartu berisi KODE provinsi (mis. "33"), bukan
    # namanya. Kode telanjang tidak terbaca di dokumen yang dibawa ke rapat
    # dinas, jadi pemanggil boleh menyuplai nama dari `wilayah.json`; tanpa
    # itu kode aslinya tetap dicetak apa adanya, tidak pernah dibuang.
    provinsi = nama_provinsi or identitas.get("provinsi")
    subjudul = (
        f"{_teks(identitas.get('kecamatan'))}, {_teks(identitas.get('kabupaten'))}, "
        f"{_teks(provinsi)} · {_teks(identitas.get('iddesa'))}"
    )

    seksi: list[SeksiRingkas | SeksiTabel] = [
        _seksi_identitas(kartu),
        _seksi_peta_peran(kartu, pp),
    ]
    ringkas_potensi, tabel_potensi = _seksi_potensi(kartu)
    seksi.append(ringkas_potensi)
    if tabel_potensi is not None:
        seksi.append(tabel_potensi)
    seksi.extend(
        [
            _seksi_kesiapan(kartu, pp),
            _seksi_logistik(kartu, pp),
            _seksi_desa_kembar(kartu),
            _seksi_fakta_program(kartu),
            _seksi_rekomendasi(kartu),
            _seksi_mutu(kartu),
        ]
    )

    if manifest is None:
        info_build = "data build tidak diketahui"
    else:
        # `muat_manifest` (`src/datastore.py`) sengaja tidak memvalidasi isi
        # manifest - tanggung jawab pemanggil. Ini cuma catatan kaki, jadi
        # kunci yang hilang (build parsial/hand-edit/skew versi penulis)
        # degradasi ke NILAI_KOSONG, bukan KeyError -> 500.
        hash_singkat = _teks(manifest.get("hash"))[:12]
        tanggal = _teks(manifest.get("tanggal"))
        info_build = f"data build {hash_singkat} ({tanggal})"
    catatan_kaki = (
        f"SIMPUL DESA — {info_build}. Angka disajikan apa adanya dari keluaran data/."
    )

    return RingkasanLaporan(
        judul=judul, subjudul=subjudul, seksi=seksi, catatan_kaki=catatan_kaki
    )
