"""Modul Berita Desa: rute baca + pipeline panen.

`router.py` menyajikan `GET /api/berita/{iddesa}` dari Supabase lewat
`service.py`. Pipeline panennya ada di sub-paket `harvest/`
(RSS -> decode -> content -> filter -> store), diorkestrasi oleh
`harvest/orchestrator.py` (`panen_desa`) — seluruh sub-paket itu sinkron
dan dipanggil endpoint admin penyegaran fase 7 lewat threadpool.
"""
