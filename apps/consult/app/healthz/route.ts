// App Platform health probe (production/consult.tf health_check) and the
// Docker smoke route. The one path the Access middleware lets through without
// a JWT, so it must never return data.
export const dynamic = "force-dynamic";

export function GET() {
  return new Response("ok", {
    headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
  });
}

export function HEAD() {
  return new Response(null, { headers: { "cache-control": "no-store" } });
}
