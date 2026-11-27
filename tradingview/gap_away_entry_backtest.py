# Gap away entries: the impulse opens past the zone's near edge with a gap (bodies only, wicks ignored). Enter at the
# close of the candle that confirms the zone (no retest) vs a limit at the near edge on the first retest. Compared with
# zones whose impulse did not gap, entered the same way. Stop a tenth of the zone past the far edge, targets 2R and 3R,
# a candle hitting both counts as the stop, trades open at the time limit left out. Zones as zone_ema_backtest.py.
# Usage: python gap_away_entry_backtest.py <datadir> <interval>
import sys, numpy as np, pandas as pd
DATA, IV = sys.argv[1], sys.argv[2]
src = open(__file__.replace("gap_away_entry_backtest.py", "zone_ema_backtest.py")).read().split("\nr = run()")[0]
g = {}; exec(src, g)
SYMS, load, zones, sim, MAXB = g["SYMS"], g["load"], g["zones"], g["sim"], g["MAXB"]
res = {}
def add(k, r):
    if r is not None: res.setdefault(k, []).append(r)
for s in SYMS:
    df = load(s); o, h, l, c = [df[x].values for x in ("Open", "High", "Low", "Close")]
    yard = pd.Series(np.abs(c - o)).rolling(20).median().values
    for (k, sup, top, btm) in zones(o, h, l, c, yard):
        d = -1 if sup else 1; near, far = (btm, top) if sup else (top, btm); hgt = top - btm
        # the impulse is the first candle after the base that leaves it: find it walking back from k
        i = k
        while i > 0 and ((c[i - 1] > top) if d == 1 else (c[i - 1] < btm)) and i > k - 8: i -= 1
        mg = 0.1 * yard[i]
        gap = (o[i] > top + mg and o[i] > c[i - 1]) if d == 1 else (o[i] < btm - mg and o[i] < c[i - 1])
        tag = "GAP" if gap else "NOGAP"
        stop = far - d * 0.1 * hgt
        e = c[k]; rk = (e - stop) * d
        if rk > 0:
            add(tag + "_now2", sim(h, l, c, k + 1, e, stop, e + d * 2 * rk, d)); add(tag + "_now3", sim(h, l, c, k + 1, e, stop, e + d * 3 * rk, d))
        for j in range(k + 1, min(k + 1 + MAXB * 2, len(c))):
            if (l[j] <= near) if d == 1 else (h[j] >= near):
                e2 = near if (o[j] - near) * d > 0 else o[j]; rk2 = (e2 - stop) * d
                if rk2 > 0:
                    add(tag + "_ret2", sim(h, l, c, j, e2, stop, e2 + d * 2 * rk2, d)); add(tag + "_ret3", sim(h, l, c, j, e2, stop, e2 + d * 3 * rk2, d))
                break
        else:
            add(tag + "_never", 1.0)
def f(k):
    v = np.array(res.get(k, []))
    return f"{len(v):5d} trades | win {np.mean(v > 0) * 100:5.1f}% | avg {v.mean():+.2f}R | total {v.sum():+7.1f}R" if len(v) else "no trades"
print(f"\n=== {IV} | {', '.join(SYMS)} ===")
for t in ("GAP", "NOGAP"):
    print(f"  {'gap away' if t == 'GAP' else 'no gap  '}  enter now 2R {f(t + '_now2')}")
    print(f"            enter now 3R {f(t + '_now3')}")
    print(f"            retest 2R    {f(t + '_ret2')}")
    print(f"            retest 3R    {f(t + '_ret3')}")
    print(f"            never retested: {len(res.get(t + '_never', []))}")
