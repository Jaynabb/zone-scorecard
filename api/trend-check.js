// Vercel serverless function: Trend check second opinion.
// Accepts two chart screenshots (base64) plus BUY/SELL and the target zone text,
// sends both images to the Anthropic Messages API and returns the model's JSON verdict.
// The API key is read from the ANTHROPIC_API_KEY environment variable only.

import { gate, send, askWithImages } from "./_shared.js";

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
  const g = await gate(req, res);
  if (g.error) return send(res, g.error[0], g.error[1]);

  const out = await askWithImages({
    img1: g.img1, img2: g.img2,
    label1: "Screenshot 1 (Mid timeframe):",
    label2: "Screenshot 2 (Low timeframe, with the target zone):",
    prompt: buildPrompt(g.direction, g.zone),
    schema: RESULT_SCHEMA,
    maxTokens: 4000
  });
  if (out.error) return send(res, out.error[0], out.error[1]);

  const parsed = out.parsed;
  const segments = Array.isArray(parsed.segments) ? parsed.segments.map(String).slice(0, 3) : [];
  while (segments.length < 3) segments.push("");

  return send(res, 200, {
    trend: parsed.trend,
    matches: Boolean(parsed.matches),
    score: Number(parsed.score),
    segments,
    control_point: String(parsed.control_point || ""),
    reason: String(parsed.reason || ""),
    confidence: parsed.confidence,
    model: out.response.model,
    fallback_ran: out.fallbackRan
  });
}
