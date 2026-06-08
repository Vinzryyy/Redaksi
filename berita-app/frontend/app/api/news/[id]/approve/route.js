const BACKEND = process.env.BACKEND_URL || "http://localhost:5000";

export async function PATCH(request, { params }) {
  const { id } = await params;

  const res = await fetch(`${BACKEND}/api/news/${id}/approve`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
  });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
