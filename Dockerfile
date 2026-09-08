# Image runtime layanan backend SIMPUL DESA.
#
# Artefak data TIDAK dibangun di sini. `python -m bangun` membaca `../data/`,
# yang bukan bagian repo ini (ADR-0009: `api/` repo sendiri), jadi folder itu
# tidak pernah ada di lingkungan build host mana pun. Yang dipakai adalah
# `data-salinan.tar.gz` — hasil build lokal yang ikut ter-commit. Cara
# menyegarkannya ada di DEPLOY.md.

# --- Tahap 1: bongkar arsip data ---------------------------------------
# Dipisah sebagai tahap sendiri supaya tarball 16 MB TIDAK ikut ke image
# jadi. `COPY` dan `RUN rm` adalah dua layer berbeda: menghapus berkas di
# layer berikutnya tidak mengeluarkannya dari layer COPY, jadi tanpa
# multi-stage arsipnya tetap terbawa.
FROM python:3.14-slim AS data
WORKDIR /bongkar
COPY data-salinan.tar.gz ./
RUN tar xzf data-salinan.tar.gz && rm data-salinan.tar.gz

# --- Tahap 2: image layanan -------------------------------------------
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependensi lebih dulu, terpisah dari kode: layer ini hanya dibangun ulang
# saat requirements.txt berubah. Seluruh dependensi terpatok punya wheel
# cp314 manylinux x86_64, jadi tidak ada compiler yang perlu dipasang.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=data /bongkar/data-salinan ./data-salinan
COPY src ./src

# Jalan sebagai non-root. TIDAK ada `chown -R`: layanan tidak pernah menulis
# ke disk (PRD bagian 7 — PDF dirakit di `io.BytesIO`, tidak ada tulis ke
# `data-salinan/`), dan berkas milik root tetap terbaca pengguna ini.
# `chown -R` atas /app menulis ulang metadata tiap berkas dan menambah satu
# layer 132 MB penuh tanpa satu manfaat pun.
RUN useradd --create-home --uid 10001 layanan
USER layanan

EXPOSE 8000

# `--proxy-headers` + `--forwarded-allow-ips` WAJIB di belakang proxy hosting.
# Tanpa keduanya `request.client.host` selalu berisi IP proxy, dan
# `get_remote_address` slowapi menaruh SELURUH pemanggil dalam satu bucket
# `LAJU_BAWAAN` — satu pengunjung ramai membuat semua orang kena 429.
# `${PORT:-8000}`: host menyuntikkan PORT, pengembangan lokal tidak.
CMD ["sh", "-c", "exec uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
