# Entry types backtest (TradePhantoms course): Touch, Zone and Exit entries, by purity and trend.
#   Touch: limit at the near edge the moment price comes back (course: purity 4/4, first retrace).
#   Zone:  price is in the zone and a candle CLOSES inside it, enter at that close (course: purity 2/4, trend trade).
#   Exit:  price went in, turned, and a candle closes back out past the near edge, enter at that close
#          (course: purity 0/4, or counter trend at 2/4 or 0/4).
# Purity is scored at each visit the way the sheet does: never retouched 4, retouched once under 50% deep 2, else 0.
# Trend is the Mid timeframe (EMA 20 over EMA 50 on closed Mid candles). Zones, stop (a tenth of the zone past the far
# edge) and the path fill rule follow ltf_rules_backtest.py. Exits: fixed 2R, and breakeven at 1R then out on a close
# back across the 9 EMA (the indicator's 9 EMA exit). A Zone entry closer to the stop than 30% of the touch stop
# distance is skipped (it would only look good because its R is tiny).
# Usage: python entry_types_backtest.py <datadir>
import sys, numpy as np, pandas as pd
DATA = sys.argv[1]
SYMS = ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD", "NQ"]
PRESETS = [("Scalping", "5m", "30m"), ("Day Trading", "1h", "4h"), ("Swing Trading", "4h", "1d")]
MAXB = {"5m": 288, "1h": 120, "4h": 60}
src = open(__file__.replace("entry_types_backtest.py", "ltf_rules_backtest.py")).read()
g = {"np": np, "pd": pd, "FILL": "path"}
exec("def ema9_sig" + src.split("\ndef ema9_sig")[1].split("\ndef stats")[0], g)
zsrc = open(__file__.replace("entry_types_backtest.py", "zone_ema_backtest.py")).read()
exec("def zones" + zsrc.split("\ndef zones")[1].split("\ndef sim")[0], g)
zones, path, fixed, trail_ema, ema_back, ema9_sig, OPEN = (g[x] for x in ("zones", "path", "fixed", "trail_ema", "ema_back", "ema9_sig", "OPEN"))

def load(s, iv):
    base = {"5m": "5m", "30m": "5m", "1h": "1h", "4h": "1h", "1d": "1d"}[iv]
    df = pd.read_csv(f"{DATA}/{s}_{base}.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    if base != iv:
        df = df.resample(iv.replace("m", "min")).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    return df[df.High > df.Low]

def mid_trend(low_df, mid_df):
    e20 = mid_df.Close.ewm(span=20, adjust=False).mean(); e50 = mid_df.Close.ewm(span=50, adjust=False).mean()
    t = np.sign(e20 - e50)
    # a Mid candle is known once it closes: stamp it at its close time, then carry it forward onto the Low candles
    step = mid_df.index.to_series().diff().median()
    t.index = t.index + step
    return t.reindex(low_df.index, method="ffill").fillna(0).values.astype(int)

def stats(v):
    v = np.array([x for x in v if x is not None])
    if not len(v): return "   no trades"
    return f"{len(v):5d} trades | win {np.mean(v > 0) * 100:5.1f}% | avg {v.mean():+.2f}R | total {v.sum():+7.1f}R"

for name, lo, mid in PRESETS:
    R = {}
    def add(key, r):
        if r is not None: R.setdefault(key, []).append(r)
    for s in SYMS:
        df = load(s, lo); o, h, l, c = [df[x].values for x in ("Open", "High", "Low", "Close")]; OPEN[0] = o
        trend = mid_trend(df, load(s, mid))
        yard = pd.Series(np.abs(c - o)).rolling(20).median().values
        sig, e9 = ema9_sig(c)
        n = MAXB[lo]
        for (k, sup, top, btm) in zones(o, h, l, c, yard):
            if k < 60: continue
            d = -1 if sup else 1
            near, far = (btm, top) if sup else (top, btm); hgt = top - btm
            stop = far - d * 0.1 * hgt
            min_risk = 0.3 * 1.1 * hgt    # a stop tighter than 30% of the touch stop is spread noise, not a real trade
            visits, depth_prev, j = 0, 0.0, k + 1
            end = min(k + 1 + n * 4, len(c))
            while j < end:
                touching = l[j] <= near if d == 1 else h[j] >= near
                if not touching: j += 1; continue
                # a visit: from this touch until a candle closes back out past the near edge, or the zone dies
                visits += 1
                pur = 4 if visits == 1 else (2 if visits == 2 and depth_prev < 0.5 else 0)
                tr = "with" if trend[j - 1] == d else ("counter" if trend[j - 1] == -d else "flat")
                ema_ok = sig[j - 1] == d
                tag = (pur, tr)
                # Touch
                e = near if (o[j] - near) * d > 0 else o[j]
                if (e - stop) * d > 0:
                    p = path(h, l, c, j, e, (e - stop) * d, d, n, True)
                    add(("touch", tag, "2R"), fixed(p, 2.0)); add(("touch", tag, "ema"), trail_ema(*p, ema_back(c, e9, j, n, d)))
                    if ema_ok: add(("touch", tag, "2R+ema_ok"), fixed(p, 2.0))
                zone_done, depth, dead = False, 0.0, False
                i = j
                while i < end:
                    depth = max(depth, ((near - l[i]) if d == 1 else (h[i] - near)) / hgt)
                    if (c[i] - far) * d < 0: dead = True; break          # close through the far edge kills the zone
                    inside = (c[i] - near) * d <= 0
                    if inside and not zone_done:                          # Zone: first close inside the zone
                        zone_done = True
                        ez = c[i]
                        if (ez - stop) * d >= min_risk and i + 1 < len(c):
                            p = path(h, l, c, i + 1, ez, (ez - stop) * d, d, n, False)
                            add(("zone", tag, "2R"), fixed(p, 2.0)); add(("zone", tag, "ema"), trail_ema(*p, ema_back(c, e9, i + 1, n, d)))
                            if ema_ok: add(("zone", tag, "2R+ema_ok"), fixed(p, 2.0))
                    if not inside and i > j or (not inside and i == j and (o[j] - near) * d <= 0):
                        # Exit: price was in and the candle closes back out past the near edge
                        ex = c[i]
                        if i + 1 < len(c):
                            p = path(h, l, c, i + 1, ex, (ex - stop) * d, d, n, False)
                            add(("exit", tag, "2R"), fixed(p, 2.0)); add(("exit", tag, "ema"), trail_ema(*p, ema_back(c, e9, i + 1, n, d)))
                            if ema_ok: add(("exit", tag, "2R+ema_ok"), fixed(p, 2.0))
                        break
                    if not inside and i == j:
                        # the touch candle itself closed back out: wick only, that is the exit too
                        ex = c[i]
                        if i + 1 < len(c):
                            p = path(h, l, c, i + 1, ex, (ex - stop) * d, d, n, False)
                            add(("exit", tag, "2R"), fixed(p, 2.0)); add(("exit", tag, "ema"), trail_ema(*p, ema_back(c, e9, i + 1, n, d)))
                            if ema_ok: add(("exit", tag, "2R+ema_ok"), fixed(p, 2.0))
                        break
                    i += 1
                if dead: break
                depth_prev = depth
                j = i + 1
    print(f"\n######## {name}: Low {lo}, Mid {mid} (trend)")
    for ent in ("touch", "zone", "exit"):
        print(f"\n  {ent.upper()} entry")
        for pur in (4, 2, 0):
            for tr in ("with", "counter"):
                a, b, e_ = R.get((ent, (pur, tr), "2R"), []), R.get((ent, (pur, tr), "ema"), []), R.get((ent, (pur, tr), "2R+ema_ok"), [])
                if not a: continue
                print(f"    purity {pur} {tr:7s} 2R      {stats(a)}")
                print(f"    purity {pur} {tr:7s} 9EMA    {stats(b)}")
                print(f"    purity {pur} {tr:7s} 2R+EMA  {stats(e_)}")
    # the course plan versus touch-only on fresh zones
    def pick(ent, pur, tr, ex): return R.get((ent, (pur, tr), ex), [])
    for ex in ("2R", "ema", "2R+ema_ok"):
        base = pick("touch", 4, "with", ex) + pick("touch", 4, "counter", ex) + pick("touch", 4, "flat", ex)
        course = base + pick("zone", 2, "with", ex) + pick("exit", 0, "with", ex) + pick("exit", 2, "counter", ex) + pick("exit", 0, "counter", ex)
        print(f"\n  [{ex}] touch only, fresh zones        {stats(base)}")
        print(f"  [{ex}] course plan (touch + zone + exit) {stats(course)}")
        print(f"  [{ex}]   added zone entries (P2 trend)  {stats(pick('zone', 2, 'with', ex))}")
        print(f"  [{ex}]   added exit entries             {stats(pick('exit', 0, 'with', ex) + pick('exit', 2, 'counter', ex) + pick('exit', 0, 'counter', ex))}")
