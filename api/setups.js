// Latest setup per symbol and side, for the Setups board.
import { send } from "./_shared.js";
import { hasRedis, redis } from "./_redis.js";

export default async function handler(req, res) {
  if (req.method !== "GET") return send(res, 405, { error: "GET only." });
  if (!hasRedis()) return send(res, 200, { configured: false, setups: [], now: Date.now() });
  try {
    const flat = await redis("HGETALL", "setups:latest");
    const setups = [];
    for (let i = 0; i + 1 < (flat || []).length; i += 2) {
      try { setups.push(JSON.parse(flat[i + 1])); } catch (e) { /* skip bad row */ }
    }
    setups.sort((a, b) => (b.score - a.score) || (b.at - a.at));
    return send(res, 200, { configured: true, setups, now: Date.now() });
  } catch (e) {
    return send(res, 502, { error: "Store read failed: " + (e && e.message ? e.message : "unknown") });
  }
}
