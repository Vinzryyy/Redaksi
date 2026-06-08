# Aplikasi Berita — Flask API + PostgreSQL + Next.js

Tiga bagian sesuai permintaan:

1. **API tampil berita** — `GET /api/news` (ambil dari PostgreSQL lokal).
2. **API input berita** — `POST /api/news`.
3. **Web Next.js** — mengakomodasi kedua API + fitur **approve / reject**.

## Catatan rekonsiliasi spesifikasi

Spesifikasi awal menyebut dua bentuk kolom yang sedikit berbeda
(tampil: `tanggal`, `kalimat VARCHAR(250)`; input: `id`, `berita TEXT`).
Keduanya digabung jadi **satu tabel** `berita` supaya konsisten:

| kolom    | tipe          | keterangan                                   |
| -------- | ------------- | -------------------------------------------- |
| id       | SERIAL (PK)   | autonumber                                   |
| tanggal  | TIMESTAMPTZ   | otomatis `now()` saat dibuat                 |
| kalimat  | VARCHAR(250)  | isi berita (input `berita` disimpan di sini) |
| status   | VARCHAR(20)   | `pending` / `approved` / `rejected`          |
| alasan   | TEXT          | catatan kenapa ditolak (opsional)            |

`status` dan `alasan` ditambahkan untuk mendukung fitur approve/reject.
Input dibatasi 250 karakter mengikuti constraint `VARCHAR(250)`.

## Logic approve / reject ("perbudak AI")

- Berita baru lewat `POST` disaring otomatis (`auto_screen` di `backend/app.py`):
  - kata terlarang (spam/judi) → langsung `rejected`,
  - HURUF KAPITAL + tanda seru berlebihan → `rejected`,
  - terlalu pendek (< 10 karakter) → `rejected`,
  - selain itu → `pending` (menunggu moderasi manusia).
- Moderator menekan **Setujui** / **Tolak** di web → memanggil
  `PATCH /api/news/<id>/approve|reject`.
- Blok `auto_screen` sengaja dibuat modular; mudah diganti panggilan ke LLM
  bila ingin moderasi lebih cerdas (antarmukanya tetap: teks → status, alasan).

---

## 1. Database (PostgreSQL lokal)

```bash
createdb berita_db
psql -d berita_db -f backend/schema.sql
```

## 2. Backend (Flask)

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # sesuaikan kredensial DB
# muat .env (mis. pakai 'set -a; source .env; set +a' atau python-dotenv)
python app.py               # jalan di http://localhost:5000
```

Cek: `curl http://localhost:5000/api/health`

## 3. Frontend (Next.js)

```bash
cd frontend
npm install
cp .env.local.example .env.local   # set BACKEND_URL bila Flask beda alamat
npm run dev                        # buka http://localhost:3000
```

## Ringkasan endpoint

### Backend (Flask — port 5000)

| Method | Endpoint                   | Fungsi                                    |
| ------ | -------------------------- | ----------------------------------------- |
| GET    | `/api/health`              | cek koneksi DB                            |
| GET    | `/api/news?status=...`     | tampilkan berita (filter status opsional) |
| POST   | `/api/news`                | input berita `{"berita": "..."}`          |
| POST   | `/api/input`               | input berita (tanpa auto-screening)       |
| PATCH  | `/api/news/<id>/approve`   | setujui                                   |
| PATCH  | `/api/news/<id>/reject`    | tolak `{"alasan": "..."}` (opsional)      |

### Frontend API Routes (Next.js — port 3000)

| Method | Endpoint                   | Fungsi                                    |
| ------ | -------------------------- | ----------------------------------------- |
| GET    | `/api/news`                | proxy → Flask `GET /api/news`             |
| POST   | `/api/news`                | proxy → Flask `POST /api/input`           |
| PATCH  | `/api/news/[id]/approve`   | proxy → Flask `PATCH /api/news/<id>/approve` |
| PATCH  | `/api/news/[id]/reject`    | proxy → Flask `PATCH /api/news/<id>/reject`  |

Contoh input:

```bash
curl -X POST http://localhost:5000/api/news \
  -H "Content-Type: application/json" \
  -d '{"berita":"Pemerintah resmikan taman kota baru hari ini."}'
```

---

## Update: Arsitektur API Routes

### Perubahan

Sebelumnya, frontend (browser) memanggil Flask backend **secara langsung**:

```
Browser  →  Flask (localhost:5000)  →  PostgreSQL
```

Sekarang, semua request dari browser melewati **Next.js API Routes** sebagai middleware:

```
Browser  →  Next.js API Routes (localhost:3000/api/...)  →  Flask (localhost:5000)  →  PostgreSQL
```

### Apa yang berubah

| Komponen | Sebelum | Sesudah |
| -------- | ------- | ------- |
| Frontend fetch URL | `http://localhost:5000/api/...` (langsung ke Flask) | `/api/...` (relative, ke Next.js API routes) |
| Env variable | `NEXT_PUBLIC_API_URL` (terekspos ke browser) | `BACKEND_URL` (server-side only) |
| File baru | — | `app/api/news/route.js`, `app/api/news/[id]/approve/route.js`, `app/api/news/[id]/reject/route.js` |

### Keuntungan

- **Keamanan** — URL dan kredensial Flask backend tidak terekspos ke browser. `BACKEND_URL` hanya diakses di server-side (tanpa prefix `NEXT_PUBLIC_`).
- **Konsistensi** — Semua action (ambil berita, input berita, approve, reject) melewati satu lapisan API yang seragam.
- **Fleksibilitas** — Mudah menambahkan logic tambahan (auth, rate limiting, logging) di API routes tanpa mengubah Flask backend.
