// Shared helpers for the Zone Scorecard serverless functions.
// Files in api/ that start with an underscore are not deployed as functions.

import Anthropic from "@anthropic-ai/sdk";

export const MODEL = "claude-sonnet-5-5";

export const MAX_BODY_BYTES = 4 * 1024 * 1024;        // whole JSON request body
export const MAX_IMAGE_B64_CHARS = 2.6 * 1024 * 1024; // per image, about 1.9 MB decoded
export const MAX_ZONE_CHARS = 300;
const RATE_WINDOW_MS = 10 * 60 * 1000;                // 10 minutes
const RATE_MAX = 10;                                  // requests per IP per window per function
const hits = new Map();                               // best effort, per warm instance

const ALLOWED_MEDIA = new Set(["image/jpeg", "image/png", "image/webp", "image/gif"]);

export function clientIp(req) {
  const fwd = req.headers["x-forwarded-for"];
  if (typeof fwd === "string" && fwd.length) return fwd.split(",")[0].trim();
  const real = req.headers["x-real-ip"];
  if (typeof real === "string" && real.length) return real;
  return (req.socket && req.socket.remoteAddress) || "unknown";
}

export function rateLimited(ip) {
  const now = Date.now();
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

export function send(res, status, body) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(body));
}

export function readBody(req) {
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

export function cleanImage(img, label) {
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

// Runs the common gatekeeping and returns either { error: [status, body] } or the parsed, validated input.
export async function gate(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return { error: [405, { error: "Use POST." }] };
  }
  const declared = Number(req.headers["content-length"] || 0);
  if (declared > MAX_BODY_BYTES) return { error: [413, { error: "Request is too large. Max 4 MB." }] };

  if (rateLimited(clientIp(req))) {
    res.setHeader("Retry-After", String(Math.ceil(RATE_WINDOW_MS / 1000)));
    return { error: [429, { error: "Too many checks from this connection. Try again in 10 minutes." }] };
  }
  if (!process.env.ANTHROPIC_API_KEY) {
    return { error: [500, { error: "Server is missing ANTHROPIC_API_KEY. Add it in the Vercel project settings." }] };
  }

  let body;
  try { body = await readBody(req); }
  catch (e) {
    if (e && e.message === "too_large") return { error: [413, { error: "Request is too large. Max 4 MB." }] };
    return { error: [400, { error: "Request body must be JSON." }] };
  }
  if (JSON.stringify(body).length > MAX_BODY_BYTES) return { error: [413, { error: "Request is too large. Max 4 MB." }] };

  // BUY, SELL, or AUTO (empty counts as AUTO): with AUTO the model reads the direction from the position tool on the Low chart.
  let direction = String(body.direction || "AUTO").toUpperCase();
  if (direction === "") direction = "AUTO";
  if (direction !== "BUY" && direction !== "SELL" && direction !== "AUTO") return { error: [400, { error: "Direction must be Buy, Sell or Auto." }] };

  // Optional: when empty, the function falls back to the TARGET tag the Jay S&D indicator puts on the chart.
  const zone = String(body.zone || "").replace(/\s+/g, " ").trim();
  if (zone.length > MAX_ZONE_CHARS) return { error: [400, { error: `Zone text must be ${MAX_ZONE_CHARS} characters or fewer.` }] };

  const images = Array.isArray(body.images) ? body.images : [];
  const img1 = cleanImage(images[0], "Screenshot 1");
  if (img1.error) return { error: [400, { error: img1.error }] };
  const img2 = cleanImage(images[1], "Screenshot 2");
  if (img2.error) return { error: [400, { error: img2.error }] };

  return { direction, zone, img1, img2, body };
}

export function makeClient() {
  return new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY, timeout: 55 * 1000, maxRetries: 1 });
}

// Calls the Messages API with both images and a prompt, enforcing a JSON schema on the reply.
// Returns { parsed, response } or { error: [status, body] }.
export async function askWithImages({ img1, img2, label1, label2, prompt, schema, maxTokens }) {
  const client = makeClient();
  let response;
  try {
    response = await client.beta.messages.create({
      model: MODEL,
      max_tokens: maxTokens || 4000,
      betas: ["server-side-fallback-2026-07-01"],
      fallbacks: "default",
      output_config: { format: { type: "json_schema", schema } },
      messages: [{
        role: "user",
        content: [
          { type: "text", text: label1 },
          { type: "image", source: { type: "base64", media_type: img1.media_type, data: img1.data } },
          { type: "text", text: label2 },
          { type: "image", source: { type: "base64", media_type: img2.media_type, data: img2.data } },
          { type: "text", text: prompt }
        ]
      }]
    });
  } catch (err) {
    if (err instanceof Anthropic.AuthenticationError) {
      return { error: [500, { error: "The server's ANTHROPIC_API_KEY was rejected. Check it in the Vercel project settings." }] };
    }
    if (err instanceof Anthropic.RateLimitError) {
      return { error: [429, { error: "The AI service is busy. Try again in a minute." }] };
    }
    if (err instanceof Anthropic.BadRequestError) {
      return { error: [400, { error: "The AI service rejected the request: " + err.message }] };
    }
    if (err instanceof Anthropic.APIConnectionTimeoutError) {
      return { error: [504, { error: "The check timed out. Try smaller screenshots." }] };
    }
    if (err instanceof Anthropic.APIError) {
      return { error: [502, { error: "AI service error (" + err.status + "). Try again." }] };
    }
    return { error: [500, { error: "Unexpected server error." }] };
  }

  if (response.stop_reason === "refusal") {
    return { error: [422, { error: "The model declined to analyze these screenshots. Try clearer chart images." }] };
  }
  if (response.stop_reason === "max_tokens") {
    return { error: [502, { error: "The model's answer was cut off. Try again." }] };
  }
  const text = response.content.filter((b) => b.type === "text").map((b) => b.text).join("");
  let parsed;
  try { parsed = JSON.parse(text); }
  catch (e) { return { error: [502, { error: "The model did not return valid JSON. Try again." }] }; }

  const fallbackRan = (response.usage && Array.isArray(response.usage.iterations))
    ? response.usage.iterations.some((it) => it.type === "fallback_message") : false;
  return { parsed, response, fallbackRan };
}
