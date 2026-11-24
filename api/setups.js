// Latest setup per symbol and side, for the Setups board.
import { send } from "./_shared.js";
import { hasRedis, redis, pipeline } from "./_redis.js";

// Styles shown on the board. Jay dropped day trading on 2026-11-18: the Daily / Weekly / Monthly style only, under its
// old name (alerts made before v97) and its new one. Add a style here to show it again.
export const BOARD_STYLES = new Set(["Position trader", "Longer Swing"]);
// A report older than this is stale (alert deleted or dead) and is removed from the store on the next read.
const MAX_AGE_MS = 24 * 60 * 60 * 1000;

export default async function handler(req, res) {
  if (req.method !== "GET") return send(res, 405, { error: "GET only." });
  if (!hasRedis()) return send(res, 200, { configured: false, setups: [], now: Date.now() });
  try {
    const [flat, seen] = await Promise.all([redis("HGETALL", "setups:latest"), redis("HGETALL", "setups:seen")]);
    const now = Date.now();
    const prune = [];
    const keep = (rec) => rec && BOARD_STYLES.has(rec.style) && typeof rec.at === "number" && now - rec.at < MAX_AGE_MS;
    const setups = [];
    for (let i = 0; i + 1 < (flat || []).length; i += 2) {
      let rec = null;
      try { rec = JSON.parse(flat[i + 1]); } catch (e) { /* bad row, prune it */ }
      if (keep(rec)) setups.push(rec);
      else { prune.push(["HDEL", "setups:latest", flat[i]]); prune.push(["ZREM", "setups:valid", flat[i]]); }
    }
    setups.sort((a, b) => (b.score - a.score) || (b.at - a.at));
    // feeds: one entry per symbol and style, with the time of its last report (heartbeat), even when it had no target
    const feeds = [];
    for (let i = 0; i + 1 < (seen || []).length; i += 2) {
      let rec = null;
      try { rec = JSON.parse(seen[i + 1]); } catch (e) { /* bad row, prune it */ }
      if (keep(rec)) feeds.push(rec);
      else prune.push(["HDEL", "setups:seen", seen[i]]);
    }
    feeds.sort((a, b) => (a.symbol + a.style).localeCompare(b.symbol + b.style));
    if (prune.length) { try { await pipeline(prune); } catch (e) { /* cosmetic, retried on the next read */ } }
    return send(res, 200, { configured: true, setups, feeds, now });
  } catch (e) {
    return send(res, 502, { error: "Store read failed: " + (e && e.message ? e.message : "unknown") });
  }
}
