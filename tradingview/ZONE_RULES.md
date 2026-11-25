# Jay S&D zone rules

How a supply or demand zone is read from the candles, written down from the zones Jay has marked as correct.
Each rule lists the chart it came from so it can be checked again. When a new marked zone disagrees with a rule,
the rule is changed here first, then in `jay_sd.pine`.

## 1. A zone is leg in, base, leg out

- **Leg in:** the move into the base. Full size candles (body more than about 1.5 typical bodies) heading toward
  the base are the leg in, never base.
- **Base:** the pause. Small candles (bodies up to about 1.5 typical bodies) sitting at the turn.
- **Leg out (impulse):** the move away. One candle of at least a typical body, or a candle that closes past the
  whole base candle and has moved a typical body from the base's wick.
- **The zone never holds the move in or the move out.** Only the base candles set its edges.

Examples: USOIL 5M 81.26-81.36 (base 06:05-06:10; 06:15 to 07:00 is the move up), USOIL 5M 82.26-82.55
(base 09:00-09:10; 09:15 is the impulse), NQ 1H (15:00 green is the leg in, 16:00 doji the base, 18:00 the leg out).

## 2. Which candles are base

- The base starts at the candle at the extreme (lowest body for demand, highest body for supply).
- It takes the small candles next to it that stay level with it.
- **Sideways base:** if price steps away and comes back to the extreme before the impulse, all of it is base, up to
  the last candle that comes back, plus any candles after that which stay inside the base's own range.
  Example: USOIL 1H 79.57-80.12 (23:00 to 05:00, impulse 06:00).
- **Once price leaves and does not come back, the rest is the move.** Example: USOIL 5M 06:15 onward.
- The base can be one candle (common on higher timeframes) or several (common on lower timeframes).

## 3. Edges: wick to body

- **Demand:** lowest wick of the base up to the top of the highest base body.
- **Supply:** highest wick of the base down to the bottom of the lowest base body.
- **Spike wicks** (a wick far longer than the base's other wicks and longer than its own body) are left out.
  Example: USOIL 1H, the 00:00 and 03:00 lows.
- Small wicks still count: stretch the zone to catch them.

## 4. Doji bases (one candle, body a quarter of its range or less)

- **Normal:** wick to body, like any base. Examples: USOIL 5M 07:00 (81.57-81.64), ETH 5M 22:20
  (1663.89-1668.98), BTC 5M 10:35 (58245-58599, Jay 58242-58597), BTC 5M 08:25 supply (58768.91-58835.67,
  Jay 58768.92-58836.54; 08:20 green is the leg in, 08:30 red the leg out), USOIL Monthly Apr 2026 (101.72-117.63).
- **Flip:** only when the wick on the zone's far side is a stub (under a quarter of a typical body) and the other
  wick is long. Then the zone runs from the long wick to the body's far side. Example: NQ 1H 16:00 supply
  (26215.25-26284.25).

## 5. A zone stays valid until a candle of its own timeframe closes through it

- Wicks through a zone do not break it.
- A 5M close below a 15M demand does not break the 15M zone.

## 6. Newest base wins on the entry timeframe

- When price comes back to an older zone and bases again, the new base is the zone and the older one is hidden.
- A base that is only a reaction off a higher timeframe zone is not a new zone.
- **Origin zones stay on the chart.** When price comes back to a valid zone, bases on it and leaves again, the
  retest base may be drawn too, but the older zone is the origin of the move and always stays visible (dashed once
  touched) until a close goes through it. It shows twice as far from price as other old zones, so the chart
  does not fill up with every origin from the whole history. Example: BTC 5M demand 59038-59163 (12:10 doji)
  with the 12:25 retest base 58946-59080 under it.

## 7. Worked example: BTC 5M, 2026-11-25 (Jay's story)

1. **Older supply 58746-58836** (base 05:55-06:15, leg in 05:50 red, leg out 06:20-06:30). Price rallied back into it at
   08:10-08:25 and dropped 1,600 points to 57244 (the sell). The indicator misses this one (see open questions).
2. **Demand 57396-57662** (Jay 57408-57666): leg in 09:45 green (body 285, full size, it holds the V low at 57244),
   base 09:50 (body 65), leg out 09:55 green (body 495). The V low wick of 09:45 is NOT in the zone: only the base
   candle's wick counts. Retested at 10:15 (low 57627) and bounced to 58599 (the buy). The indicator draws it exactly.
3. **Demand 59038-59163** (Jay 59048-59164): 12:05 green leg in, 12:10 doji base (lower wick 110 is not a stub, so
   plain wick to body), 12:15 green leg out. Retested at 12:20-12:25 and ran to 60,000 (the buy). The indicator draws
   it exactly.
4. **No zone at the 10:00 V top:** 10:00 is a full size candle with no small candle at the turn, and Jay draws no zone
   there. Rule: a turn made only of full size candles is not a zone.

## Open questions

- **BTC 5M older supply, Jay 58746-58836 (base 05:55-06:15, leg in 05:50, leg out 06:20-06:30, retested at 08:25 for a
  1,600 point drop):** not drawn by the indicator. The base candles (bodies 45-91) are more than half the first
  leg-out candle (06:20, body 129), so the base walk stops at 06:10. The leg out is really three candles (06:20 to
  06:30, about 390 points). Letting base candles reach 1.5 typical bodies found it but broke USOIL 5M 81.57-81.64,
  so it was reverted. Next idea: measure the leg out over its run of candles instead of the first candle alone.
