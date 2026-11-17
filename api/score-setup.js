// Vercel serverless function: suggest answers for all six Zone Scorecard checks from two screenshots.
// Screenshot 1 is the Mid timeframe, screenshot 2 is the Low timeframe showing the target zone.
// Returns a suggested option for each check with a reason and a confidence. The trader confirms on the sheet.

import { gate, send, askWithImages } from "./_shared.js";

const CONF = { type: "string", enum: ["high", "medium", "low"] };
const check = (optionEnum, extra) => ({
  type: "object",
  additionalProperties: false,
  required: ["option", "reason", "confidence"].concat(Object.keys(extra || {})),
  properties: Object.assign({
    option: { type: "string", enum: optionEnum },
    reason: { type: "string" },
    confidence: CONF
  }, extra || {})
});

const SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["zone_found", "target_zone", "range", "time", "trend", "strength_move", "strength_structure", "purity", "rrr", "notes"],
  properties: {
    zone_found: { type: "boolean" },
    target_zone: { type: "string" },
    range: check(["top_or_bottom", "middle", "opposite", "unclear"]),
    time: check(["one_to_three", "four_to_six", "seven_plus", "unclear"], { candles: { type: ["integer", "null"] } }),
    trend: check(["with_zone", "no_trend", "against_zone", "unclear"], {
      trend: { type: "string", enum: ["up", "down", "sideways", "unclear"] },
      segments: { type: "array", items: { type: "string" } },
      control_point: { type: "string" }
    }),
    strength_move: check(["yes", "no", "unclear"], { ratio: { type: ["number", "null"] } }),
    strength_structure: check(["yes", "no", "unclear"]),
    purity: check(["never", "once", "multiple", "unclear"]),
    rrr: check(["five_plus", "three_to_five", "under_three", "not_visible"], { ratio: { type: ["number", "null"] } }),
    notes: { type: "string" }
  }
};

function buildPrompt(direction, zone, tf) {
  const low = tf.low || "Low", mid = tf.mid || "Mid", high = tf.high || "High";
  const side = direction === "SELL" ? "SUPPLY" : "DEMAND";
  const zoneText = zone
    ? "The trader is going to " + direction + " from the target zone: " + zone + ". "
    : "The trader is going to " + direction + ". The target zone is the box in Screenshot 2 whose label ends with the word TARGET on the " + side + " side, " +
      "that is the nearest " + side + " box to price, drawn with a thick white outline. Read its exact price range from its label. ";
  return "You are pre-filling a supply and demand zone scorecard for a trader. The trader reviews every answer, so be honest about uncertainty. " +
    "Screenshot 1 is the Mid timeframe (" + mid + "). Screenshot 2 is the Low timeframe (" + low + ") and shows the target zone. " +
    zoneText +
    "The charts carry the trader's own indicator. Supply zones are red boxes and demand zones are green boxes. " +
    "Only the nearest box on each side of price is labeled: it has a thick white outline and a label with its timeframe, side, price range and the word TARGET, " +
    "for example DAILY DEMAND 1720.31 - 1743.28 TARGET +W +M. A suffix +W means a Weekly zone overlaps it and +M means a Monthly zone overlaps it; no suffix means no higher timeframe backing. " +
    "Other boxes have no label. Boxes of the chart's own timeframe are the entry zones, filled solid, and a darker fill means higher timeframe backing. " +
    "Higher timeframe zones are drawn as dashed hollow frames and only where they overlap an entry zone, which marks correlation. " +
    "The zone's left edge is the base candle it was built from. Use the price range in the label as the zone's exact top and bottom. " +
    "How the charts are drawn (TradingView, dark theme): the range comes from the High timeframe (" + high + ") and is shown on every chart as a retracement tool with horizontal levels labeled by percentage: 100.00% is the top of the range, 0.00% is the bottom, with 75.00% and 25.00% in between. " +
    "The band from 75% to 100% is the top of the range, the band from 25% to 75% is the middle, and the band from 0% to 25% is the bottom. Use the percentage labels first. The top and bottom bands are usually shaded purple and the middle band blue or olive, but go by the labels when colors differ. " +
    "Price levels on the right axis can help you place a zone relative to the range levels. " +
    "Supply zones are red or pink rectangles labeled with their timeframe, for example WEEKLY or MONTHLY. Demand zones are green rectangles labeled the same way. " +
    "Yellow dashed lines are the cursor crosshair, ignore them. Only candle closes count, never wicks, unless a check says otherwise. " +
    "For a sell, price travels up into the zone. For a buy, price travels down into it. " +
    "Answer these checks. " +
    "1. RANGE: where does the target zone sit in the range? 'top_or_bottom' means selling at the top where banks sold or buying at the bottom where banks bought (a sell zone in or above the upper purple band, or a buy zone in or below the lower purple band). " +
    "'middle' means the zone is in the blue band. 'opposite' means buying where banks sold or selling where banks bought (a buy zone at the top, or a sell zone at the bottom). " +
    "2. TIME: count the base candles inside the target zone on the Low chart (the candles that formed the zone before the move out). 'one_to_three', 'four_to_six' or 'seven_plus'. Give the count. " +
    "3. TREND: what will the Mid timeframe trend be when price travels to the target zone? A trend is 3 segments: an impulse that breaks the control point, a pullback to a pivot, a new impulse past the last extreme. " +
    "The control point is the lower high in a downtrend and the higher low in an uptrend. The trend holds until a candle closes through the control point. " +
    "If the zone sits well short of any Mid timeframe zone or level that could flip the trend, the trend cannot change on the way. " +
    "'with_zone' means the Mid trend on arrival matches the trade (a sell matches a downtrend, a buy matches an uptrend). 'no_trend' means sideways. 'against_zone' means counter-trend. Give the trend, 3 short segment descriptions and the control point. " +
    "4. STRENGTH_MOVE: was the move out of the target zone at least 2 times the height of the zone? Estimate the ratio of the move to the zone height. " +
    "5. STRENGTH_STRUCTURE: did the move-out candle close past the previous supply or demand on the left side of the zone? This is oppositional structure. 'yes' or 'no'. If the previous zone is not in view, say 'unclear'. " +
    "6. PURITY: since the zone broke out, on the Low chart, has price come back into it? 'never' means never retouched. 'once' means retouched one time and less than halfway into the zone. 'multiple' means more than one retouch, or any touch deeper than halfway. " +
    "7. RRR: only if a position tool or entry, stop and target with readable numbers is visible, give the reward per 1 risk as a ratio and pick 'five_plus', 'three_to_five' or 'under_three'. Otherwise 'not_visible'. Never guess this one. " +
    "Set target_zone to the label of the zone you scored, including its price range, for example DAILY SUPPLY 1987.55 - 2018.59. " +
    "Set zone_found to false if you cannot identify the target zone. Use 'unclear' for any check you cannot read with reasonable confidence instead of guessing, and explain why in the reason. " +
    "Keep each reason to one or two short sentences a trader can verify on the chart. Put anything else worth knowing in notes. Reply as JSON only.";
}

const MAP = {
  range: { top_or_bottom: 0, middle: 1, opposite: 2 },
  time: { one_to_three: 0, four_to_six: 1, seven_plus: 2 },
  trend: { with_zone: 0, no_trend: 1, against_zone: 2 },
  yesno: { yes: 0, no: 1 },
  purity: { never: 0, once: 1, multiple: 2 },
  rrr: { five_plus: 0, three_to_five: 1, under_three: 2 }
};

function pack(c, map, extra) {
  const idx = map[c.option];
  return Object.assign({
    index: idx === undefined ? null : idx,
    option: c.option,
    reason: String(c.reason || ""),
    confidence: c.confidence
  }, extra || {});
}

export default async function handler(req, res) {
  const g = await gate(req, res);
  if (g.error) return send(res, g.error[0], g.error[1]);

  const tfIn = (g.body && typeof g.body.timeframes === "object" && g.body.timeframes) || {};
  const tf = {
    low: String(tfIn.low || "").slice(0, 12),
    mid: String(tfIn.mid || "").slice(0, 12),
    high: String(tfIn.high || "").slice(0, 12)
  };

  const out = await askWithImages({
    img1: g.img1, img2: g.img2,
    label1: "Screenshot 1 (Mid timeframe):",
    label2: "Screenshot 2 (Low timeframe, with the target zone):",
    prompt: buildPrompt(g.direction, g.zone, tf),
    schema: SCHEMA,
    maxTokens: 6000
  });
  if (out.error) return send(res, out.error[0], out.error[1]);

  const p = out.parsed;
  const time = pack(p.time, MAP.time, { candles: Number.isInteger(p.time.candles) ? p.time.candles : null });
  if (time.candles !== null && time.candles >= 1) time.index = time.candles <= 3 ? 0 : time.candles <= 6 ? 1 : 2;

  const segs = Array.isArray(p.trend.segments) ? p.trend.segments.map(String).slice(0, 3) : [];
  while (segs.length < 3) segs.push("");

  const rrrRatio = typeof p.rrr.ratio === "number" && p.rrr.ratio >= 0 ? p.rrr.ratio : null;
  const rrr = pack(p.rrr, MAP.rrr, { ratio: rrrRatio, visible: p.rrr.option !== "not_visible" });
  if (rrrRatio !== null) rrr.index = rrrRatio >= 5 ? 0 : rrrRatio >= 3 ? 1 : 2;

  return send(res, 200, {
    direction: g.direction,
    zone_found: Boolean(p.zone_found),
    target_zone: String(p.target_zone || ""),
    checks: {
      range: pack(p.range, MAP.range),
      time,
      trend: pack(p.trend, MAP.trend, { trend: p.trend.trend, segments: segs, control_point: String(p.trend.control_point || "") }),
      str1: pack(p.strength_move, MAP.yesno, { ratio: typeof p.strength_move.ratio === "number" ? p.strength_move.ratio : null }),
      str2: pack(p.strength_structure, MAP.yesno),
      purity: pack(p.purity, MAP.purity),
      rrr
    },
    notes: String(p.notes || ""),
    model: out.response.model,
    fallback_ran: out.fallbackRan
  });
}
