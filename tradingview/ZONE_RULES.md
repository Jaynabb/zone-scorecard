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

## Open questions

- **V-top with no small base** (BTC 5M 10:00, a full size rally candle that price turned down from): how to mark it.
