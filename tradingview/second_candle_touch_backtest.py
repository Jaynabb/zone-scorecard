# Does the second candle of a visit count as a new touch? A visit is price trading into a fresh zone; the indicator
# counts candles that stay inside as one visit and only starts a new touch after a candle closes back out. Compared:
#   FIRST   limit at the near edge on the first candle of the first visit (the Touch entry)
#   CANDLE2 entering at the open of the second candle of that same visit, when candle 1 closed inside the zone
#           (what a trader arriving one candle late gets if the second candle is still the first touch)
#   SECOND  limit at the near edge on the first candle of the second visit (price closed back out, then came back)
# Stop a tenth of the zone past the far edge, target 2R and 3R from each entry; a candle hitting both is a loss; trades
# open at the time limit are left out. Zones as zone_ema_backtest.py (simplified Jay S&D), fresh zones only.
# Usage: python second_candle_touch_backtest.py <datadir> <interval>
import sys, numpy as np, pandas as pd
DATA, IV = sys.argv[1], sys.argv[2]
src = open(__file__.replace("second_candle_touch_backtest.py", "zone_ema_backtest.py")).read().split("\nr = run()")[0]
g = {}; exec(src, g)
SYMS, load, zones, sim, MAXB = g["SYMS"], g["load"], g["zones"], g["sim"], g["MAXB"]

res = {k: [] for k in ("F2", "F3", "C2", "C3", "S2", "S3", "Fc2", "Fc3", "S1c2", "S1c3", "Smc2", "Smc3")}
for s in SYMS:
    df = load(s); o, h, l, c = [df[x].values for x in ("Open", "High", "Low", "Close")]
    yard = pd.Series(np.abs(c - o)).rolling(20).median().values
    for (k, sup, top, btm) in zones(o, h, l, c, yard):
        d = -1 if sup else 1
        near, far = (btm, top) if sup else (top, btm); hgt = top - btm
        stop = far - d * 0.1 * hgt
        inside = lambda j: (l[j] <= near) if d == 1 else (h[j] >= near)      # traded into the zone
        closed_out = lambda j: (c[j] - near) * d > 0                          # closed back beyond the near edge
        dead = lambda j: (c[j] - far) * d < 0                                 # closed through the far edge
        visit = 0; j = k + 1; end = min(k + 1 + MAXB * 2, len(c))
        while j < end and visit < 2:
            if dead(j): break
            if inside(j):
                visit += 1
                e = near if (o[j] - near) * d > 0 else o[j]
                if (e - stop) * d > 0:
                    rk = (e - stop) * d
                    r2 = sim(h, l, c, j, e, stop, e + d * 2 * rk, d); r3 = sim(h, l, c, j, e, stop, e + d * 3 * rk, d)
                    key = "F" if visit == 1 else "S"
                    if r2 is not None: res[key + "2"].append(r2)
                    if r3 is not None: res[key + "3"].append(r3)
                    if visit == 2:
                        kk = "S1c" if v1_len == 1 else "Smc"
                        if r2 is not None: res[kk + "2"].append(r2)
                        if r3 is not None: res[kk + "3"].append(r3)
                # stay in this visit while candles do not close back out
                v_start = j
                while j < end and not closed_out(j) and not dead(j):
                    if visit == 1 and j == v_start + 1 and not dead(j - 1):
                        e2 = o[j]
                        if (e2 - stop) * d > 0:
                            rk = (e2 - stop) * d
                            r2 = sim(h, l, c, j, e2, stop, e2 + d * 2 * rk, d); r3 = sim(h, l, c, j, e2, stop, e2 + d * 3 * rk, d)
                            if r2 is not None:
                                res["C2"].append(r2); res["Fc2"].append(res["F2"][-1] if res["F2"] else np.nan)
                            if r3 is not None:
                                res["C3"].append(r3); res["Fc3"].append(res["F3"][-1] if res["F3"] else np.nan)
                    j += 1
                if visit == 1: v1_len = j - v_start + 1
                if j < end and dead(j): break
            j += 1

def f(v):
    v = np.array([x for x in v if x == x])
    return f"{len(v):5d} trades | win {np.mean(v > 0) * 100:5.1f}% | avg {v.mean():+.2f}R | total {v.sum():+7.1f}R" if len(v) else "no trades"
print(f"\n=== {IV} | {', '.join(SYMS)} ===")
for t in ("2", "3"):
    print(f"  target {t}R")
    print(f"    FIRST   first candle of the first visit (limit at near edge)      {f(res['F' + t])}")
    print(f"    CANDLE2 second candle of the first visit (enter at its open)      {f(res['C' + t])}")
    print(f"            FIRST on those same visits                               {f(res['Fc' + t])}")
    print(f"    SECOND  first candle of the second visit (left, came back)        {f(res['S' + t])}")
    print(f"            first visit was one candle                                {f(res['S1c' + t])}")
    print(f"            first visit was two or more candles                       {f(res['Smc' + t])}")
