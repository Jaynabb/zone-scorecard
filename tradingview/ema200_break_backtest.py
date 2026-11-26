# Coming out of a fresh zone, price closes through the 200 EMA (below it out of supply, above it out of demand) before
# it ever comes back to the zone. Enter on that close (BREAK) versus waiting for the first retest of the near edge
# (TOUCH, the current entry). Same stop for both, a tenth of the zone past the far edge, target 3R from each entry.
# A trade still open after the time limit is left out. Zones as zone_ema_backtest.py (simplified Jay S&D).
#   BREAK  the first close across the 200 EMA from 8 candles before the zone is confirmed until the retest
#   TOUCH  limit at the near edge on the first retest, also split by the 200 EMA side on the candle before
# Usage: python ema200_break_backtest.py <datadir> <interval>
import sys, numpy as np, pandas as pd
DATA, IV = sys.argv[1], sys.argv[2]
src = open(__file__.replace("ema200_break_backtest.py", "zone_ema_backtest.py")).read().split("\nr = run()")[0]
g = {}; exec(src, g)
SYMS, load, zones, sim, MAXB = g["SYMS"], g["load"], g["zones"], g["sim"], g["MAXB"]
RR = 3

res = {k: [] for k in ("B", "T", "Tw", "Ta", "pB", "pT", "Bnear", "Bfar", "Bret", "Bnoret")}
dist = []
for s in SYMS:
    df = load(s); o, h, l, c = [df[x].values for x in ("Open", "High", "Low", "Close")]
    yard = pd.Series(np.abs(c - o)).rolling(20).median().values
    e = df.Close.ewm(span=200, adjust=False).mean().values
    for (k, sup, top, btm) in zones(o, h, l, c, yard):
        if k < 400: continue
        d = -1 if sup else 1
        near, far = (btm, top) if sup else (top, btm); hgt = top - btm
        stop = far - d * 0.1 * hgt
        side = lambda j: (c[j] - e[j]) * d > 0          # close on the trade side of the 200
        rb = rt = None; jb = None; retested = False
        for j in range(max(k - 8, 1), min(k + 1 + MAXB * 2, len(c))):
            if j > k and (l[j] <= near if d == 1 else h[j] >= near):
                en = near if (o[j] - near) * d > 0 else o[j]
                if (en - stop) * d > 0:
                    rt = sim(h, l, c, j, en, stop, en + d * RR * (en - stop) * d, d)
                    if rt is not None:
                        res["T"].append(rt); res["Tw" if side(j - 1) else "Ta"].append(rt)
                retested = True
                break
            if j > k and (c[j] - far) * d < 0: break
            if jb is None and side(j) and not side(j - 1): jb = j
            if jb is not None and rb is None and j >= k and side(j):
                en = c[j]; risk = (en - stop) * d
                rb = sim(h, l, c, j + 1, en, stop, en + d * RR * risk, d)
                if rb is not None:
                    res["B"].append(rb); x = risk / hgt; dist.append(x)
                    res["Bnear" if x <= 3 else "Bfar"].append(rb)
        if rb is not None:
            res["Bret" if retested else "Bnoret"].append(rb)
        if rb is not None and rt is not None: res["pB"].append(rb); res["pT"].append(rt)

def f(v):
    v = np.array(v)
    return f"{len(v):5d} trades | win {np.mean(v > 0) * 100:5.1f}% | avg {v.mean():+.2f}R | total {v.sum():+7.1f}R" if len(v) else "no trades"
print(f"\n=== {IV} | {', '.join(SYMS)} | 3R target, stop a tenth past the far edge ===")
print(f"  BREAK  enter on the 200 EMA break, no retest      {f(res['B'])}")
print(f"         risk within 3 zone heights                  {f(res['Bnear'])}")
print(f"         risk over 3 zone heights                    {f(res['Bfar'])}")
print(f"  TOUCH  wait for the retest (current)               {f(res['T'])}")
print(f"         200 EMA already on the zone's side          {f(res['Tw'])}")
print(f"         200 EMA against the zone                    {f(res['Ta'])}")
print(f"  same zones, both entries taken:  BREAK {f(res['pB'])}")
print(f"                                   TOUCH {f(res['pT'])}")
print(f"  BREAK, price never came back to the zone       {f(res['Bnoret'])}")
print(f"  BREAK, price came back to the zone later       {f(res['Bret'])}")
if dist: print(f"  BREAK risk in zone heights: median {np.median(dist):.1f}")
