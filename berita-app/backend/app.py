"""
API Berita sederhana (Flask + PostgreSQL).

Endpoint:
    GET    /api/health                 -> cek koneksi
    GET    /api/news?status=approved   -> tampilkan berita (filter status opsional)
    POST   /api/news                   -> input berita baru  {"berita": "..."}
    POST   /api/news/<id>/approve      -> setujui berita
    POST   /api/news/<id>/reject       -> tolak berita      {"alasan": "..."} (opsional)
    PATCH  /api/news/<id>/approve      -> setujui berita (legacy)
    PATCH  /api/news/<id>/reject       -> tolak berita (legacy)
    POST   /api/keys/generate          -> buat API key baru
    GET    /api/keys                   -> daftar API key aktif

Konfigurasi DB lewat environment variable (lihat .env.example).
"""

import os
import re
import time
import secrets
import hashlib
from functools import wraps

from dotenv import load_dotenv
load_dotenv()

import psycopg2
import psycopg2.extras
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # izinkan frontend Next.js (port lain) mengakses API

MAX_LEN = 250  # batas VARCHAR(250)

# --------------------------------------------------------------------------- #
# API Key: generasi & validasi
# --------------------------------------------------------------------------- #
CHARSET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _encode_base62(num):
    """Encode integer ke base62 (azAZ09)."""
    if num == 0:
        return CHARSET[0]
    result = []
    while num > 0:
        result.append(CHARSET[num % 62])
        num //= 62
    return "".join(reversed(result))


def _generate_api_key():
    """
    Buat API key dengan format: {random_4}{timestamp_base62}{random_sisa}
    - Timestamp (detik sejak epoch) di-encode base62 lalu disisipkan
      di posisi ke-4, supaya key tetap terlihat acak tapi mengandung
      waktu pembuatan.
    - Panjang minimal 32 karakter (jauh di atas minimum 16).
    - Karakter hanya azAZ09.
    Returns: (key, timestamp)
    """
    ts = int(time.time())
    ts_encoded = _encode_base62(ts)

    prefix = "".join(secrets.choice(CHARSET) for _ in range(4))
    needed = max(32 - 4 - len(ts_encoded), 8)
    suffix = "".join(secrets.choice(CHARSET) for _ in range(needed))

    key = prefix + ts_encoded + suffix
    return key, ts


def _hash_key(key):
    """Hash API key untuk disimpan di DB (jangan simpan plaintext)."""
    return hashlib.sha256(key.encode()).hexdigest()


def _extract_timestamp(key):
    """Ekstrak timestamp dari API key (posisi 4 sampai sebelum suffix)."""
    ts_part = key[4:-8]
    num = 0
    for ch in ts_part:
        idx = CHARSET.index(ch)
        num = num * 62 + idx
    return num


def require_api_key(f):
    """Decorator: wajibkan header X-API-Key yang valid."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key", "")
        if not api_key:
            return jsonify({"error": "Header X-API-Key wajib diisi"}), 401

        key_hash = _hash_key(api_key)
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM api_keys WHERE key_hash = %s AND revoked = false;",
                (key_hash,),
            )
            row = cur.fetchone()

        if not row:
            return jsonify({"error": "API key tidak valid atau sudah direvoke"}), 403
        return f(*args, **kwargs)
    return decorated


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
        sslmode=os.getenv("DB_SSLMODE", "prefer"),
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
@app.get("/test")
def test_page():
    """Halaman tes API."""
    return render_template("test_api.html")


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
@app.post("/api/news/<int:news_id>/approve")
@require_api_key
def approve_news(news_id):
    row = _set_status(news_id, "approved", alasan=None)
    if not row:
        return jsonify({"error": "berita tidak ditemukan"}), 404
    return jsonify(row_to_dict(row))


@app.patch("/api/news/<int:news_id>/reject")
@app.post("/api/news/<int:news_id>/reject")
@require_api_key
def reject_news(news_id):
    data = request.get_json(silent=True) or {}
    alasan = (data.get("alasan") or "Ditolak oleh moderator.").strip()
    row = _set_status(news_id, "rejected", alasan=alasan)
    if not row:
        return jsonify({"error": "berita tidak ditemukan"}), 404
    return jsonify(row_to_dict(row))


# --------------------------------------------------------------------------- #
# API Key management
# --------------------------------------------------------------------------- #
@app.post("/api/keys/generate")
def generate_key():
    """Buat API key baru. Body opsional: {"label": "nama key"}."""
    data = request.get_json(silent=True) or {}
    label = (data.get("label") or "default").strip()

    key, ts = _generate_api_key()
    key_hash = _hash_key(key)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO api_keys (key_hash, label, created_ts) "
            "VALUES (%s, %s, %s) RETURNING id;",
            (key_hash, label, ts),
        )
        row = cur.fetchone()
        conn.commit()

    return jsonify({
        "id": row[0],
        "key": key,
        "label": label,
        "created_ts": ts,
        "pesan": "Simpan key ini — tidak bisa ditampilkan lagi.",
    }), 201


@app.get("/api/keys")
def list_keys():
    """Daftar API key aktif (tanpa menampilkan key asli)."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT id, label, created_ts, revoked FROM api_keys ORDER BY id DESC;"
        )
        rows = cur.fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/api/keys/<int:key_id>/revoke")
def revoke_key(key_id):
    """Revoke API key."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE api_keys SET revoked = true WHERE id = %s RETURNING id;",
            (key_id,),
        )
        row = cur.fetchone()
        conn.commit()
    if not row:
        return jsonify({"error": "key tidak ditemukan"}), 404
    return jsonify({"ok": True, "message": f"Key {key_id} berhasil direvoke."})


@app.get("/api/keys/verify")
def verify_key():
    """Verifikasi API key dari header X-API-Key."""
    api_key = request.headers.get("X-API-Key", "")
    if not api_key:
        return jsonify({"valid": False, "error": "Header X-API-Key kosong"}), 401

    key_hash = _hash_key(api_key)
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT id, label, revoked FROM api_keys WHERE key_hash = %s;",
            (key_hash,),
        )
        row = cur.fetchone()

    if not row:
        return jsonify({"valid": False, "error": "Key tidak ditemukan"}), 404
    if row["revoked"]:
        return jsonify({"valid": False, "error": "Key sudah direvoke"}), 403

    return jsonify({"valid": True, "id": row["id"], "label": row["label"]})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
