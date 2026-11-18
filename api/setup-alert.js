// Webhook for Jay S&D setup alerts. TradingView posts the alert() JSON here on every bar close.
// URL: /api/setup-alert?key=SCAN_SECRET
import { send, clientIp } from "./_shared.js";
import { hasRedis, pipeline } from "./_redis.js";

// TradingView sends webhooks from these addresses (published in its alert documentation).
// With no SCAN_SECRET set, only these senders are accepted. With SCAN_SECRET set, the ?key= must match.
const TRADINGVIEW_IPS = new Set(["52.89.214.238", "34.212.75.30", "54.218.53.128", "52.32.178.7"]);

const MAX_BYTES = 64 * 1024;
const SIDES = new Set(["BUY", "SELL"]);

async function rawBody(req) {
  if (req.body !== undefined && req.body !== null) {
    return typeof req.body === "string" ? req.body : JSON.stringify(req.body);
  }
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c) => {
      data += c;
      if (data.length > MAX_BYTES) { reject(new Error("too_large")); req.destroy(); }
    });
    req.on("end", () => resolve(data));
    req.on("error", reject);
  });
}

const str = (v, n) => String(v === undefined || v === null ? "" : v).slice(0, n);
const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const int = (v, lo, hi) => (Number.isInteger(v) && v >= lo && v <= hi ? v : null);

export default async function handler(req, res) {
  if (req.method !== "POST") return send(res, 405, { error: "POST only." });
  const secret = process.env.SCAN_SECRET || "";
  const key = new URL(req.url, "http://local").searchParams.get("key") || "";
  if (secret) {
    if (key !== secret) return send(res, 401, { error: "Bad key." });
  } else if (!TRADINGVIEW_IPS.has(clientIp(req))) {
    return send(res, 401, { error: "Sender is not TradingView. Set SCAN_SECRET to use a key instead." });
  }
  if (!hasRedis()) return send(res, 503, { error: "No Redis store is configured." });

  let body;
  try { body = JSON.parse(await rawBody(req)); }
  catch (e) { return send(res, 400, { error: e && e.message === "too_large" ? "Payload too large." : "Body must be the Jay S&D alert JSON." }); }

  const symbol = str(body.symbol, 32).trim();
  if (!symbol) return send(res, 400, { error: "symbol missing." });
  const setups = Array.isArray(body.setups) ? body.setups.slice(0, 4) : [];
  const alertMin = int(body.alert_min, 0, 20) ?? 14;
  const now = Date.now();
  const common = {
    symbol,
    exchange: str(body.exchange, 32),
    chart_tf: str(body.chart_tf, 12),
    style: str(body.style, 24),
    low_tf: str(body.low_tf, 12), mid_tf: str(body.mid_tf, 12), high_tf: str(body.high_tf, 12),
    price: num(body.price),
    bar_time: num(body.bar_time),
    trend: str(body.trend, 8),
    control_point: num(body.control_point),
    range_top: num(body.range_top), range_btm: num(body.range_btm),
    alert_min: alertMin,
    at: now
  };

  const cmds = [];
  let stored = 0;
  for (const s of setups) {
    if (!s || typeof s !== "object") continue;
    const side = str(s.side, 4).toUpperCase();
    if (!SIDES.has(side)) continue;
    const score = int(s.score, 0, 20);
    if (score === null) continue;
    const checks = s.checks && typeof s.checks === "object" ? s.checks : {};
    const styleKey = (common.style || "position").toLowerCase().replace(/[^a-z]/g, "").slice(0, 12) || "position";
    const rec = Object.assign({}, common, {
      id: symbol + ":" + styleKey + ":" + side,
      side,
      zone: str(s.zone, 120),
      top: num(s.top), btm: num(s.btm),
      backing: str(s.backing, 24),
      base: int(s.base, 0, 99), touches: int(s.touches, 0, 999), depth: num(s.depth), os: Boolean(s.os),
      score,
      checks: {
        range: int(checks.range, 0, 2) ?? 0, time: int(checks.time, 0, 2) ?? 0, trend: int(checks.trend, 0, 4) ?? 0,
        move: int(checks.move, 0, 2) ?? 0, os: int(checks.os, 0, 2) ?? 0, purity: int(checks.purity, 0, 4) ?? 0, rrr: int(checks.rrr, 0, 4) ?? 0
      },
      rrr_ratio: num(s.rrr_ratio), move_ratio: num(s.move_ratio), range_pos: num(s.range_pos),
      valid: score >= alertMin
    });
    const json = JSON.stringify(rec);
    cmds.push(["HSET", "setups:latest", rec.id, json]);
    if (rec.valid) cmds.push(["ZADD", "setups:valid", String(now), rec.id]);
    else cmds.push(["ZREM", "setups:valid", rec.id]);
    cmds.push(["LPUSH", "setups:log", json]);
    stored++;
  }
  if (!stored) return send(res, 400, { error: "No usable setups in payload." });
  cmds.push(["LTRIM", "setups:log", "0", "999"]);
  cmds.push(["SET", "setups:last_seen:" + symbol, String(now)]);
  try { await pipeline(cmds); }
  catch (e) { return send(res, 502, { error: "Store failed: " + (e && e.message ? e.message : "unknown") }); }
  return send(res, 200, { ok: true, stored });
}
