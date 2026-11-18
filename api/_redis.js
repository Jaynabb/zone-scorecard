// Tiny Upstash Redis REST client. Works with the Vercel Marketplace Upstash integration
// (KV_REST_API_URL / KV_REST_API_TOKEN) or a plain Upstash database (UPSTASH_REDIS_REST_URL / _TOKEN).
const URL = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL || "";
const TOKEN = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN || "";

export function hasRedis() {
  return Boolean(URL && TOKEN);
}

export async function redis(...command) {
  const r = await fetch(URL, {
    method: "POST",
    headers: { Authorization: "Bearer " + TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify(command)
  });
  const j = await r.json();
  if (j.error) throw new Error(j.error);
  return j.result;
}

export async function pipeline(commands) {
  const r = await fetch(URL + "/pipeline", {
    method: "POST",
    headers: { Authorization: "Bearer " + TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify(commands)
  });
  const j = await r.json();
  if (!Array.isArray(j)) throw new Error(j.error || "pipeline failed");
  return j.map((x) => x.result);
}
