const BACKEND = process.env.BACKEND_URL || "http://localhost:5000";

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const status = searchParams.get("status");
  const url = status
    ? `${BACKEND}/api/news?status=${encodeURIComponent(status)}`
    : `${BACKEND}/api/news`;

  const res = await fetch(url, { cache: "no-store" });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}

export async function POST(request) {
  const body = await request.json();

  const res = await fetch(`${BACKEND}/api/input`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
