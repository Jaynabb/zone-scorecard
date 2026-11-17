// Vercel serverless function: Trend check second opinion.
// Accepts two chart screenshots (base64) plus BUY/SELL and the target zone text,
// sends both images to the Anthropic Messages API and returns the model's JSON verdict.
// The API key is read from the ANTHROPIC_API_KEY environment variable only.

import Anthropic from "@anthropic-ai/sdk";

const MODEL = "claude-sonnet-5-5";

// Abuse protection
const MAX_BODY_BYTES = 4 * 1024 * 1024;        // whole JSON request body
const MAX_IMAGE_B64_CHARS = 2.6 * 1024 * 1024; // per image, about 1.9 MB decoded
const MAX_ZONE_CHARS = 300;
const RATE_WINDOW_MS = 10 * 60 * 1000;         // 10 minutes
const RATE_MAX = 10;                           // requests per IP per window
const hits = new Map();                        // best effort, per warm instance

const ALLOWED_MEDIA = new Set(["image/jpeg", "image/png", "image/webp", "image/gif"]);

const RESULT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["trend", "matches", "score", "segments", "control_point", "reason", "confidence"],
  properties: {
    trend: { type: "string", enum: ["up", "down", "sideways"] },
    matches: { type: "boolean" },
    score: { type: "integer", enum: [4, 2, 0] },
    segments: { type: "array", items: { type: "string" } },
    control_point: { type: "string" },
    reason: { type: "string" },
    confidence: { type: "string", enum: ["high", "medium", "low"] }
  }
};

function clientIp(req) {
  const fwd = req.headers["x-forwarded-for"];
  if (typeof fwd === "string" && fwd.length) return fwd.split(",")[0].trim();
  const real = req.headers["x-real-ip"];
  if (typeof real === "string" && real.length) return real;
  return (req.socket && req.socket.remoteAddress) || "unknown";
}

function rateLimited(ip) {
  const now = Date.now();
  // prune old entries so the map does not grow without bound
  if (hits.size > 5000) {
    for (const [k, v] of hits) if (now - v.start > RATE_WINDOW_MS) hits.delete(k);
  }
  const entry = hits.get(ip);
  if (!entry || now - entry.start > RATE_WINDOW_MS) {
    hits.set(ip, { start: now, count: 1 });
    return false;
  }
  entry.count += 1;
  return entry.count > RATE_MAX;
}

function send(res, status, body) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(body));
}

function readBody(req) {
  if (req.body !== undefined && req.body !== null) {
    if (typeof req.body === "string") return JSON.parse(req.body);
    if (Buffer.isBuffer(req.body)) return JSON.parse(req.body.toString("utf8"));
    return req.body;
  }
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on("data", (c) => {
      size += c.length;
      if (size > MAX_BODY_BYTES) { reject(new Error("too_large")); req.destroy(); return; }
      chunks.push(c);
    });
    req.on("end", () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString("utf8"))); }
      catch (e) { reject(new Error("bad_json")); }
    });
    req.on("error", reject);
  });
}

function cleanImage(img, label) {
  if (!img || typeof img !== "object") return { error: `${label} is missing.` };
  let data = typeof img.data === "string" ? img.data : "";
  const comma = data.indexOf(",");
  if (data.startsWith("data:") && comma > -1) data = data.slice(comma + 1);
  data = data.replace(/\s+/g, "");
  if (!data) return { error: `${label} is missing.` };
  if (data.length > MAX_IMAGE_B64_CHARS) return { error: `${label} is too large after resizing. Try a smaller screenshot.` };
  if (!/^[A-Za-z0-9+/]+=*$/.test(data)) return { error: `${label} is not valid image data.` };
  const media_type = String(img.media_type || "").toLowerCase();
  if (!ALLOWED_MEDIA.has(media_type)) return { error: `${label} must be a JPEG, PNG, WebP or GIF.` };
  return { data, media_type };
}

function buildPrompt(direction, zone) {
  return "You are checking trend for a supply and demand trader. Screenshot 1 is the Mid timeframe. " +
    "Screenshot 2 is the Low timeframe with the target zone. The trader is going to " + direction +
    " from the target zone: " + zone + ". Question: what will the Mid timeframe trend be when price travels to the target zone? " +
    "For a sell, price travels up into the zone. For a buy, price travels down into it. " +
    "Rules: a trend is 3 segments (an impulse that breaks the control point, a pullback to a pivot, a new impulse past the last extreme). " +
    "The control point is the lower high in a downtrend and the higher low in an uptrend. Only candle closes count, never wicks. " +
    "The trend holds until a candle closes through the control point. " +
    "Score: 4/4 if the Mid trend on arrival matches the trade direction (a sell matches a downtrend, a buy matches an uptrend), " +
    "2/4 if there is no trend (sideways), 0/4 if it is counter-trend. " +
    "If the zone sits well short of any Mid timeframe zone or level that could flip the trend, the trend cannot change on the way. " +
    "If the screenshots are unclear or the timeframe cannot be read, say so instead of guessing. " +
    "Reply as JSON only: {trend: 'up'|'down'|'sideways', matches: true|false, score: 4|2|0, segments: [3 short strings], " +
    "control_point: string, reason: string, confidence: 'high'|'medium'|'low'}.";
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return send(res, 405, { error: "Use POST." });
  }

  const declared = Number(req.headers["content-length"] || 0);
  if (declared > MAX_BODY_BYTES) return send(res, 413, { error: "Request is too large. Max 4 MB." });

  const ip = clientIp(req);
  if (rateLimited(ip)) {
    res.setHeader("Retry-After", String(Math.ceil(RATE_WINDOW_MS / 1000)));
    return send(res, 429, { error: "Too many checks from this connection. Try again in 10 minutes." });
  }

  if (!process.env.ANTHROPIC_API_KEY) {
    return send(res, 500, { error: "Server is missing ANTHROPIC_API_KEY. Add it in the Vercel project settings." });
  }

  let body;
  try { body = await readBody(req); }
  catch (e) {
    if (e && e.message === "too_large") return send(res, 413, { error: "Request is too large. Max 4 MB." });
    return send(res, 400, { error: "Request body must be JSON." });
  }
  if (JSON.stringify(body).length > MAX_BODY_BYTES) return send(res, 413, { error: "Request is too large. Max 4 MB." });

  const direction = String(body.direction || "").toUpperCase();
  if (direction !== "BUY" && direction !== "SELL") return send(res, 400, { error: "Pick Buy or Sell." });

  const zone = String(body.zone || "").replace(/\s+/g, " ").trim();
  if (!zone) return send(res, 400, { error: "Describe which zone is the target." });
  if (zone.length > MAX_ZONE_CHARS) return send(res, 400, { error: `Zone text must be ${MAX_ZONE_CHARS} characters or fewer.` });

  const images = Array.isArray(body.images) ? body.images : [];
  const img1 = cleanImage(images[0], "Screenshot 1");
  if (img1.error) return send(res, 400, { error: img1.error });
  const img2 = cleanImage(images[1], "Screenshot 2");
  if (img2.error) return send(res, 400, { error: img2.error });

  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY, timeout: 55 * 1000, maxRetries: 1 });

  let response;
  try {
    response = await client.beta.messages.create({
      model: MODEL,
      max_tokens: 4000,
      betas: ["server-side-fallback-2026-07-01"],
      fallbacks: "default",
      output_config: { format: { type: "json_schema", schema: RESULT_SCHEMA } },
      messages: [{
        role: "user",
        content: [
          { type: "text", text: "Screenshot 1 (Mid timeframe):" },
          { type: "image", source: { type: "base64", media_type: img1.media_type, data: img1.data } },
          { type: "text", text: "Screenshot 2 (Low timeframe, with the target zone):" },
          { type: "image", source: { type: "base64", media_type: img2.media_type, data: img2.data } },
          { type: "text", text: buildPrompt(direction, zone) }
        ]
      }]
    });
  } catch (err) {
    if (err instanceof Anthropic.AuthenticationError) {
      return send(res, 500, { error: "The server's ANTHROPIC_API_KEY was rejected. Check it in the Vercel project settings." });
    }
    if (err instanceof Anthropic.RateLimitError) {
      return send(res, 429, { error: "The AI service is busy. Try again in a minute." });
    }
    if (err instanceof Anthropic.BadRequestError) {
      return send(res, 400, { error: "The AI service rejected the request: " + err.message });
    }
    if (err instanceof Anthropic.APIConnectionTimeoutError) {
      return send(res, 504, { error: "The check timed out. Try smaller screenshots." });
    }
    if (err instanceof Anthropic.APIError) {
      return send(res, 502, { error: "AI service error (" + err.status + "). Try again." });
    }
    return send(res, 500, { error: "Unexpected server error." });
  }

  if (response.stop_reason === "refusal") {
    return send(res, 422, { error: "The model declined to analyze these screenshots. Try clearer chart images." });
  }
  if (response.stop_reason === "max_tokens") {
    return send(res, 502, { error: "The model's answer was cut off. Try again." });
  }

  const text = response.content.filter((b) => b.type === "text").map((b) => b.text).join("");
  let parsed;
  try { parsed = JSON.parse(text); }
  catch (e) { return send(res, 502, { error: "The model did not return valid JSON. Try again." }); }

  const segments = Array.isArray(parsed.segments) ? parsed.segments.map(String).slice(0, 3) : [];
  while (segments.length < 3) segments.push("");

  const fallbackRan = (response.usage && Array.isArray(response.usage.iterations))
    ? response.usage.iterations.some((it) => it.type === "fallback_message") : false;

  return send(res, 200, {
    trend: parsed.trend,
    matches: Boolean(parsed.matches),
    score: Number(parsed.score),
    segments,
    control_point: String(parsed.control_point || ""),
    reason: String(parsed.reason || ""),
    confidence: parsed.confidence,
    model: response.model,
    fallback_ran: fallbackRan
  });
}
