"""
API Berita sederhana (Flask + PostgreSQL).

Endpoint:
    GET    /api/health                 -> cek koneksi
    GET    /api/news?status=approved   -> tampilkan berita (filter status opsional)
    POST   /api/news                   -> input berita baru  {"berita": "..."}
    PATCH  /api/news/<id>/approve       -> setujui berita
    PATCH  /api/news/<id>/reject        -> tolak berita      {"alasan": "..."} (opsional)

Konfigurasi DB lewat environment variable (lihat .env.example).
"""

import os
import re

from dotenv import load_dotenv
load_dotenv()

import psycopg2
import psycopg2.extras
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # izinkan frontend Next.js (port lain) mengakses API

MAX_LEN = 250  # batas VARCHAR(250)


# --------------------------------------------------------------------------- #
# Koneksi database
# --------------------------------------------------------------------------- #
def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "berita_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
    )


def row_to_dict(row):
    """Ubah baris DB jadi dict yang ramah JSON."""
    return {
        "id": row["id"],
        "tanggal": row["tanggal"].isoformat() if row["tanggal"] else None,
        "kalimat": row["kalimat"],
        "status": row["status"],
        "alasan": row["alasan"],
    }


# --------------------------------------------------------------------------- #
# "Perbudak AI": auto-moderation sederhana berbasis aturan.
# Dipanggil saat input berita baru. Tujuannya menyaring spam jelas secara
# otomatis sebelum masuk antrian moderasi manusia.
#
# Aturan:
#   - mengandung kata terlarang (spam/judi/penipuan)  -> langsung rejected
#   - HURUF KAPITAL SEMUA + banyak tanda seru          -> langsung rejected
#   - terlalu pendek (< 10 karakter)                   -> langsung rejected
#   - selain itu                                       -> pending (tunggu manusia)
#
# Catatan: blok ini gampang diganti dengan panggilan ke model LLM bila mau
# moderasi yang lebih cerdas — antarmukanya sama: terima teks, balikan
# (status, alasan).
# --------------------------------------------------------------------------- #
BANNED_KEYWORDS = [
    "gratis pulsa", "klik sekarang", "menangkan hadiah", "judi", "slot gacor",
    "transfer dana", "pinjaman cepat", "viagra", "promo undian",
]


def auto_screen(teks: str):
    t = teks.strip()
    low = t.lower()

    if len(t) < 10:
        return "rejected", "Otomatis: teks terlalu pendek untuk dianggap berita."

    for kw in BANNED_KEYWORDS:
        if kw in low:
            return "rejected", f"Otomatis: terdeteksi kata terlarang ('{kw}')."

    letters = [c for c in t if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio > 0.8 and t.count("!") >= 2:
            return "rejected", "Otomatis: terlihat seperti spam (kapital + tanda seru berlebihan)."

    return "pending", None


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
        return jsonify({"ok": True, "db": "connected"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/api/news")
def list_news():
    """Tampilkan berita. ?status=approved|pending|rejected (opsional)."""
    status = request.args.get("status")
    sql = "SELECT id, tanggal, kalimat, status, alasan FROM berita"
    params = []
    if status:
        if status not in ("pending", "approved", "rejected"):
            return jsonify({"error": "status tidak valid"}), 400
        sql += " WHERE status = %s"
        params.append(status)
    sql += " ORDER BY tanggal DESC, id DESC;"

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.post("/api/news")
def create_news():
    """Input berita baru. Body JSON: {"berita": "..."}."""
    data = request.get_json(silent=True) or {}
    # terima 'berita' (sesuai spec input) maupun 'kalimat' biar fleksibel
    teks = (data.get("berita") or data.get("kalimat") or "").strip()

    if not teks:
        return jsonify({"error": "field 'berita' wajib diisi"}), 400
    if len(teks) > MAX_LEN:
        return jsonify({"error": f"berita maksimal {MAX_LEN} karakter"}), 400

    status, alasan = auto_screen(teks)

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "INSERT INTO berita (kalimat, status, alasan) "
            "VALUES (%s, %s, %s) RETURNING id, tanggal, kalimat, status, alasan;",
            (teks, status, alasan),
        )
        row = cur.fetchone()
        conn.commit()
    return jsonify(row_to_dict(row)), 201


@app.post("/api/input")
def input_berita():
    """API terpisah khusus input berita. Body JSON: {"berita": "..."}."""
    data = request.get_json(silent=True) or {}
    teks = (data.get("berita") or "").strip()

    if not teks:
        return jsonify({"error": "field 'berita' wajib diisi"}), 400
    if len(teks) > MAX_LEN:
        return jsonify({"error": f"berita maksimal {MAX_LEN} karakter"}), 400

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "INSERT INTO berita (kalimat, status) "
            "VALUES (%s, 'pending') RETURNING id, tanggal, kalimat, status, alasan;",
            (teks,),
        )
        row = cur.fetchone()
        conn.commit()
    return jsonify(row_to_dict(row)), 201


def _set_status(news_id, new_status, alasan=None):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "UPDATE berita SET status = %s, alasan = %s "
            "WHERE id = %s RETURNING id, tanggal, kalimat, status, alasan;",
            (new_status, alasan, news_id),
        )
        row = cur.fetchone()
        conn.commit()
    return row


@app.patch("/api/news/<int:news_id>/approve")
def approve_news(news_id):
    row = _set_status(news_id, "approved", alasan=None)
    if not row:
        return jsonify({"error": "berita tidak ditemukan"}), 404
    return jsonify(row_to_dict(row))


@app.patch("/api/news/<int:news_id>/reject")
def reject_news(news_id):
    data = request.get_json(silent=True) or {}
    alasan = (data.get("alasan") or "Ditolak oleh moderator.").strip()
    row = _set_status(news_id, "rejected", alasan=alasan)
    if not row:
        return jsonify({"error": "berita tidak ditemukan"}), 404
    return jsonify(row_to_dict(row))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
