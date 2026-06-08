"use client";

import { useEffect, useMemo, useState } from "react";

const MAX = 250;

const TABS = [
  { key: "all", label: "Semua" },
  { key: "pending", label: "Menunggu" },
  { key: "approved", label: "Disetujui" },
  { key: "rejected", label: "Ditolak" },
];

const STATUS_LABEL = {
  pending: "Menunggu",
  approved: "Disetujui",
  rejected: "Ditolak",
};

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("id-ID", {
      day: "numeric",
      month: "long",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function Page() {
  const [items, setItems] = useState([]);
  const [tab, setTab] = useState("all");
  const [teks, setTeks] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    setError("");
    try {
      const res = await fetch(`/api/news`, { cache: "no-store" });
      if (!res.ok) throw new Error("Gagal memuat berita");
      setItems(await res.json());
    } catch (e) {
      setError(`${e.message}. Pastikan backend API berjalan.`);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const counts = useMemo(() => {
    const c = { all: items.length, pending: 0, approved: 0, rejected: 0 };
    items.forEach((it) => (c[it.status] = (c[it.status] || 0) + 1));
    return c;
  }, [items]);

  const visible = useMemo(
    () => (tab === "all" ? items : items.filter((it) => it.status === tab)),
    [items, tab]
  );

  async function submit() {
    const value = teks.trim();
    if (!value || value.length > MAX) return;
    setSubmitting(true);
    setError("");
    try {
      const res = await fetch(`/api/news`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ berita: value }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Gagal menyimpan");
      setTeks("");
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function moderate(id, action) {
    setError("");
    let body;
    if (action === "reject") {
      const alasan = window.prompt("Alasan menolak (opsional):", "");
      body = JSON.stringify({ alasan: alasan || "Ditolak oleh moderator." });
    }
    try {
      const res = await fetch(`/api/news/${id}/${action}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body,
      });
      if (!res.ok) throw new Error("Gagal memperbarui status");
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  const over = teks.length > MAX;

  return (
    <main className="wrap">
      <header className="masthead">
        <p className="kicker">Meja Redaksi</p>
        <h1>Manajemen Berita</h1>
        <p>Input berita, tampilkan dari database, lalu setujui atau tolak.</p>
      </header>

      {error && <div className="error">{error}</div>}

      <section className="compose">
        <h2>Tulis berita baru</h2>
        <textarea
          value={teks}
          onChange={(e) => setTeks(e.target.value)}
          placeholder="Ketik kalimat berita di sini (maks. 250 karakter)…"
        />
        <div className="compose-row">
          <span className={`counter${over ? " over" : ""}`}>
            {teks.length} / {MAX}
          </span>
          <button
            className="btn-primary"
            onClick={submit}
            disabled={submitting || !teks.trim() || over}
          >
            {submitting ? "Mengirim…" : "Kirim untuk moderasi"}
          </button>
        </div>
      </section>

      <nav className="tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className="tab"
            data-active={tab === t.key}
            onClick={() => setTab(t.key)}
          >
            {t.label}
            <span className="count">{counts[t.key] ?? 0}</span>
          </button>
        ))}
      </nav>

      <div className="list">
        {visible.length === 0 && <div className="empty">Belum ada berita di sini.</div>}
        {visible.map((it) => (
          <article key={it.id} className="item" data-status={it.status}>
            <div className="meta">
              <span className="id">#{it.id}</span>
              <span className="date">{formatDate(it.tanggal)}</span>
              <span className={`badge ${it.status}`}>{STATUS_LABEL[it.status]}</span>
            </div>
            <p className="kalimat">{it.kalimat}</p>
            {it.status === "rejected" && it.alasan && (
              <p className="alasan">Alasan: {it.alasan}</p>
            )}
            <div className="actions">
              {it.status !== "approved" && (
                <button className="btn-approve" onClick={() => moderate(it.id, "approve")}>
                  ✓ Setujui
                </button>
              )}
              {it.status !== "rejected" && (
                <button className="btn-reject" onClick={() => moderate(it.id, "reject")}>
                  ✕ Tolak
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
    </main>
  );
}
