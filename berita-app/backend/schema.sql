-- ============================================================
-- Skema database untuk aplikasi Berita
-- ============================================================
-- Catatan rekonsiliasi spesifikasi:
--   Spesifikasi awal menyebut dua "bentuk" data:
--     - tampil  : tanggal, kalimat (VARCHAR 250)
--     - input   : id (autonumber), berita (text)
--   Keduanya digabung menjadi SATU tabel agar konsisten:
--     - id      : autonumber (SERIAL / primary key)
--     - tanggal : kapan berita dibuat (otomatis)
--     - kalimat : isi berita, dibatasi 250 karakter (VARCHAR 250)
--     - status  : pending / approved / rejected (untuk fitur approve-reject)
--     - alasan  : catatan moderasi (kenapa di-reject, dsb)
-- ============================================================

CREATE TABLE IF NOT EXISTS berita (
    id        SERIAL PRIMARY KEY,
    tanggal   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    kalimat   VARCHAR(250) NOT NULL,
    status    VARCHAR(20)  NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'approved', 'rejected')),
    alasan    TEXT
);

-- Index supaya filter per-status cepat (dipakai banyak di frontend)
CREATE INDEX IF NOT EXISTS idx_berita_status  ON berita (status);
CREATE INDEX IF NOT EXISTS idx_berita_tanggal ON berita (tanggal DESC);

-- Contoh data awal (opsional, boleh dihapus)
INSERT INTO berita (kalimat, status) VALUES
    ('Pemerintah daerah meresmikan jembatan baru di pusat kota.', 'approved'),
    ('Tim sepak bola lokal lolos ke babak final kejuaraan provinsi.', 'pending'),
    ('GRATIS PULSA KLIK SEKARANG MENANGKAN HADIAH UANG TUNAI!!!', 'rejected')
ON CONFLICT DO NOTHING;
