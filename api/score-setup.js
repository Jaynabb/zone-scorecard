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
  required: ["direction", "zone_found", "target_zone", "range", "time", "trend", "strength_move", "strength_structure", "purity", "rrr", "notes"],
  properties: {
    direction: { type: "string", enum: ["BUY", "SELL", "unclear"] },
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
  const dirText = direction === "AUTO"
    ? "First work out the trade direction from the position tool on Screenshot 2. TradingView's long position tool has its green profit box above the entry line and its red stop box below the entry: that is a BUY. " +
      "The short position tool has the green profit box below the entry and the red stop box above it: that is a SELL. Set direction to BUY or SELL from that. " +
      "If there is no position tool on Screenshot 2, set direction to 'unclear', set zone_found to false, and say so in notes. "
    : "The trader is going to " + direction + ". Set direction to " + direction + ". ";
  const zoneText = dirText + (zone
    ? "The target zone is: " + zone + ". "
    : "The target zone is the box in Screenshot 2 whose label contains the word TARGET on the matching side: the SUPPLY box for a SELL, the DEMAND box for a BUY" +
      (direction === "AUTO" ? "" : ", here the " + side + " box") + ". It is the nearest box of that side to price, drawn with a thick white outline. Read its exact price range from its label. ");
  return "You are pre-filling a supply and demand zone scorecard for a trader. The trader reviews every answer, so be honest about uncertainty. " +
    "Screenshot 1 is the Mid timeframe (" + mid + "). Screenshot 2 is the Low timeframe (" + low + ") and shows the target zone. " +
    zoneText +
    "The charts carry the trader's own indicator. Supply zones are red boxes and demand zones are green boxes, filled, and all end at the right margin. " +
    "Timeframe is shown by shade and width: Low timeframe (" + low + ") zones are the lightest shade and the shortest boxes, Mid timeframe (" + mid + ") zones a medium shade and longer, High timeframe (" + high + ") zones the darkest shade and the longest. " +
    "Where zones of different timeframes overlap, the fills stack and the shorter box sits inside the longer one: that is correlation. " +
    "Only the nearest box on each side of price is labeled: it has a thick white outline and a label with its timeframe, side, price range and the word TARGET, " +
    "written on three or four lines, for example DAILY DEMAND 1720.31 - 1743.28 on the first line, TARGET +W +M on the second line, base 3 | touches 1 (40% deep) | OS yes on the third line, and SCORE 15/20 | range 1 | time 2 | trend 2 | move 2 (6.1x) | OS 2 | purity 4 | rrr 2 (3.4:1) on the fourth. " +
    "The TARGET line's suffixes name the higher timeframes whose zones overlap it, for example +W for Weekly, +M for Monthly, +4H for the 4 hour; no suffix means no higher timeframe backing. " +
    "The SCORE line is the indicator's own point estimate for every check. Its range uses an automatic range (100% at the middle of the nearest " + high + " supply, 0% at the middle of the nearest " + high + " demand) and its rrr uses an automatic trade (entry at the zone's near edge, stop at its far edge, target at the other target zone). " +
    "The trader's own retracement tool and position tool take precedence when they are on the chart. When they are not, use the SCORE line's range and rrr values and say in the reason that they came from the indicator's automatic range or trade. " +
    "After the backing come three facts measured by the indicator itself, which are exact and override anything you would estimate by eye: 'base N' is the number of base candles the zone was built from; " +
    "'touches N' is how many separate retests the zone has had: each time price came back into the zone after a candle had closed back outside it, with the deepest retest as a share of the zone height in brackets, and 'touches 0' means never retouched; " +
    "'OS yes' means that during the whole directional move out of the zone, before its first retest, price closed through an opposing zone of the same timeframe (oppositional structure); 'OS no' means it did not. " +
    "'base read on WEEKLY' (or DAILY) means the higher timeframe candle at that turn had no clean base, so the indicator took the base from the timeframe below and drew it as the higher timeframe zone; treat it as a normal zone of the labeled timeframe. " +
    "The grey zig zag line on each chart joins the confirmed swing highs and lows of that chart's timeframe; the leg after its last pivot is the current, unconfirmed move. " +
    "A readout box in the top right corner of each chart states the trend of the Mid timeframe and of the chart's own timeframe, computed by the indicator from those zig zag swings with the 3 segment rule on closes, " +
    "for example WEEKLY TREND: DOWN | control point 2600.00 (a close above ends it) | highs 2600.00 < 3400.00 | lows 1450.00 < 1600.00. The state comes from breaks of structure on closes: a close below the last swing low starts DOWN and the swing high before it is the control point; a close above the last swing high starts UP and the swing low before it is the control point; the state holds until the opposite break, so a higher high followed by a close through the higher low is DOWN, not RANGE. RANGE only appears before any break. That readout is exact and overrides your own reading of the swings. " +
    "Other boxes have no label. The labeled boxes are always the nearest Low timeframe (" + low + ") zones, on every chart including the Mid and High ones, because the entry is taken from the Low timeframe zone and trend is scored against it. " +
    "Boxes have a fixed width and do not start at their base candle; find the base candles by price, where the candles paused inside the zone's price range before the move out. Use the price range in the label as the zone's exact top and bottom. " +
    "How the charts are drawn (TradingView, dark theme): the range comes from the High timeframe (" + high + ") and is shown on every chart as a retracement tool with horizontal levels labeled by percentage: 100.00% is the top of the range, 0.00% is the bottom, with 75.00% and 25.00% in between. " +
    "The band from 75% to 100% is the top of the range, the band from 25% to 75% is the middle, and the band from 0% to 25% is the bottom. Use the percentage labels first. The top and bottom bands are usually shaded purple and the middle band blue or olive, but go by the labels when colors differ. " +
    "Price levels on the right axis can help you place a zone relative to the range levels. " +
    "Supply zones are red or pink rectangles labeled with their timeframe, for example WEEKLY or MONTHLY. Demand zones are green rectangles labeled the same way. " +
    "Yellow dashed lines are the cursor crosshair, ignore them. Only candle closes count, never wicks, unless a check says otherwise. " +
    "For a sell, price travels up into the zone. For a buy, price travels down into it. " +
    "Answer these checks. " +
    "1. RANGE: where does the target zone sit in the range? 'top_or_bottom' means selling at the top where banks sold or buying at the bottom where banks bought (a sell zone in or above the upper purple band, or a buy zone in or below the lower purple band). " +
    "'middle' means the zone is in the blue band. 'opposite' means buying where banks sold or selling where banks bought (a buy zone at the top, or a sell zone at the bottom). " +
    "2. TIME: read 'base N' from the target label and pick 'one_to_three', 'four_to_six' or 'seven_plus' from it with high confidence. State the count. Only count candles by eye if the label is unreadable. " +
    "3. TREND: what will the Mid timeframe trend be when price travels to the target zone? Start from the " + mid.toUpperCase() + " TREND line of the readout box (quote it). Then trace price to the zone: if price can reach the zone without closing through the control point, the readout state holds on arrival. " +
    "If price must close through the control point to reach the zone (a sell zone above the control point of a downtrend, or a buy zone below the control point of an uptrend), the trend ends on the way, so answer 'no_trend' at most, never 'with_zone'. If the readout says RANGE, answer 'no_trend'. " +
    "Only if the readout is missing or unreadable, read the structure from the grey zig zag pivots on Screenshot 1, never from smaller wiggles inside a leg. " +
    "A trend is 3 segments: an impulse that breaks the control point, a pullback to a pivot, a new impulse past the last extreme. " +
    "The control point is the lower high in a downtrend and the higher low in an uptrend. The trend holds until a candle closes through the control point. " +
    "An uptrend needs a zig zag high above the previous zig zag high AND a low above the previous low; a downtrend needs the mirror. If the pivots show a higher low but the last high is still below the prior high, or the reverse, price is inside a range: answer 'no_trend'. " +
    "The current unconfirmed leg counts only if it has closed beyond the last zig zag extreme. Name the two pivots you compared and their prices. " +
    "If the zone sits well short of any Mid timeframe zone or level that could flip the trend, the trend cannot change on the way. " +
    "'with_zone' means the Mid trend on arrival matches the trade (a sell matches a downtrend, a buy matches an uptrend). 'no_trend' means sideways. 'against_zone' means counter-trend. Give the trend, 3 short segment descriptions and the control point. " +
    "4. STRENGTH_MOVE: was the move out of the target zone at least 2 times the height of the zone? Estimate the ratio of the move to the zone height. " +
    "5. STRENGTH_STRUCTURE: read 'OS yes' or 'OS no' from the target label and answer 'yes' or 'no' with high confidence. The indicator checked whether the entire move out of the zone, up to its first retest, closed through an opposing zone of the same timeframe, not just the first candle. Only say 'unclear' if the label is unreadable. " +
    "6. PURITY: read 'touches' from the target label. 'touches 0' is 'never'. 'touches 1' with a depth under 50% is 'once'. Anything else (two or more touches, or any depth of 50% or more) is 'multiple'. High confidence; quote the label values in the reason. " +
    "7. RRR: if a position tool or entry, stop and target with readable numbers is visible, give the reward per 1 risk as a ratio and pick 'five_plus', 'three_to_five' or 'under_three'. If not, use the rrr ratio in brackets on the SCORE line, at medium confidence, and say it is the indicator's automatic trade. Only if neither is readable answer 'not_visible'. Never guess this one. " +
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

  const dirOut = g.direction === "AUTO" ? (p.direction === "BUY" || p.direction === "SELL" ? p.direction : "") : g.direction;

  return send(res, 200, {
    direction: dirOut,
    direction_source: g.direction === "AUTO" ? "chart" : "user",
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
