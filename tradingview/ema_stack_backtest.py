# EMA stack cross backtest: enter when the 9 / 21 / 50 EMAs line up (9 above 21 above 50 = buy, 9 below 21 below
# 50 = sell) on the candle the stack forms, entry at its close, no zone retest. Compared against the current rule
# (zone retest + 9 EMA close agrees) and against random entries. Usage:
#   python ema_stack_backtest.py <datadir> <interval>
import sys, numpy as np, pandas as pd
DATA, IV = sys.argv[1], sys.argv[2]
src = open(__file__.replace("ema_stack_backtest.py", "zone_ema_backtest.py")).read().split("\nr = run()")[0]
g = {}; exec(src, g)
SYMS, load, zones, sim, MAXB = g["SYMS"], g["load"], g["zones"], g["sim"], g["MAXB"]
SW = 10                      # swing stop: lowest low / highest high of the last 10 candles
rng = np.random.default_rng(7)

def exit_on_flip(h, l, c, start, entry, stop, d, stack):
    # hold until the stop or until the stack turns the other way, exit at that close
    risk = (entry - stop) * d
    for j in range(start, min(start + MAXB, len(c))):
        if (l[j] <= stop if d == 1 else h[j] >= stop): return -1.0
        if stack[j] == -d: return (c[j] - entry) * d / risk
    return None

res = {k: [] for k in ("S1", "S2", "S3", "Sflip", "Z", "Zw", "A", "R2")}
by = {}
for s in SYMS:
    df = load(s); o, h, l, c = [df[x].values for x in ("Open", "High", "Low", "Close")]
    yard = pd.Series(np.abs(c - o)).rolling(20).median().values
    e9, e21, e50 = [df.Close.ewm(span=p, adjust=False).mean().values for p in (9, 21, 50)]
    stack = np.where((e9 > e21) & (e21 > e50), 1, np.where((e9 < e21) & (e21 < e50), -1, 0))
    lo = pd.Series(l).rolling(SW).min().values; hi = pd.Series(h).rolling(SW).max().values
    by[s] = []
    for i in range(60, len(c) - 1):
        if stack[i] == 0 or stack[i] == stack[i - 1]: continue
        d = stack[i]; stop = lo[i] if d == 1 else hi[i]
        risk = (c[i] - stop) * d
        if risk <= 0: continue
        for k, m in (("S1", 1), ("S2", 2), ("S3", 3)):
            r = sim(h, l, c, i + 1, c[i], stop, c[i] + d * m * risk, d)
            if r is not None:
                res[k].append(r)
                if k == "S2": by[s].append(r)
        r = exit_on_flip(h, l, c, i + 1, c[i], stop, d, stack)
        if r is not None: res["Sflip"].append(r)
        # random baseline: same count of entries at random candles, random side, same stop and 2R logic
        j = rng.integers(60, len(c) - 1); dd = rng.choice([-1, 1]); st2 = lo[j] if dd == 1 else hi[j]
        rk = (c[j] - st2) * dd
        if rk > 0:
            r = sim(h, l, c, j + 1, c[j], st2, c[j] + dd * 2 * rk, dd)
            if r is not None: res["R2"].append(r)
    # Z: stack forms the way of a fresh zone that price has left and not retested; stop beyond the zone, 2R
    sig = np.zeros(len(c), int); st = 0; e9up = c > e9; e9dn = c < e9
    for i in range(1, len(c)):
        if e9up[i] and not e9up[i - 1]: st = 1
        if e9dn[i] and not e9dn[i - 1]: st = -1
        sig[i] = st
    for (k, sup, top, btm) in zones(o, h, l, c, yard):
        if k < 60: continue
        d = -1 if sup else 1
        near, far = (btm, top) if sup else (top, btm); hgt = top - btm
        zstop = far - d * 0.1 * hgt; target = near + d * 2 * abs(near - zstop)
        done = False
        for j in range(k + 1, min(k + 1 + MAXB * 2, len(c))):
            if not done and stack[j] == d and stack[j - 1] != d and (c[j] - near) * d > 0:
                done = True
                r = sim(h, l, c, j + 1, c[j], zstop, c[j] + d * 2 * abs(c[j] - zstop), d)
                if r is not None: res["Z"].append(r)
                sw = lo[j] if d == 1 else hi[j]
                if (c[j] - sw) * d > 0:
                    r = sim(h, l, c, j + 1, c[j], sw, c[j] + d * 2 * (c[j] - sw) * d, d)
                    if r is not None: res["Zw"].append(r)
            if (l[j] <= near if d == 1 else h[j] >= near):
                e = near if (o[j] - near) * d > 0 else o[j]
                if (e - zstop) * d > 0 and sig[j - 1] == d:
                    r = sim(h, l, c, j, e, zstop, target, d)
                    if r is not None: res["A"].append(r)
                break
            if (c[j] - far) * d < 0: break

def f(v):
    v = np.array(v)
    return f"{len(v):5d} trades | win {np.mean(v > 0) * 100:5.1f}% | avg {v.mean():+.2f}R | total {v.sum():+7.1f}R" if len(v) else "no trades"
print(f"\n=== {IV} | {', '.join(SYMS)} ===")
print(f"  EMA stack cross, swing stop, 1R target           {f(res['S1'])}")
print(f"  EMA stack cross, swing stop, 2R target           {f(res['S2'])}")
print(f"  EMA stack cross, swing stop, 3R target           {f(res['S3'])}")
print(f"  EMA stack cross, swing stop, exit on opposite    {f(res['Sflip'])}")
print(f"  random entries, swing stop, 2R (baseline)        {f(res['R2'])}")
print(f"  stack cross toward a fresh zone, zone stop, 2R   {f(res['Z'])}")
print(f"  stack cross toward a fresh zone, swing stop, 2R  {f(res['Zw'])}")
print(f"  current rule: zone retest + 9 EMA agrees, 2R     {f(res['A'])}")
print("  stack cross 2R by symbol: " + " | ".join(f"{s} {np.mean(v):+.2f}R ({len(v)})" for s, v in by.items() if v))
