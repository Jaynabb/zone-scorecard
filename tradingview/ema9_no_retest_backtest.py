# Zone entry backtest: retest + EMA agrees (current rule, 9 EMA close flip) versus entering on the 9 EMA flip
# itself without waiting for the retest. Zones follow the simplified detection in zone_ema_backtest.py; only fresh
# zones are traded. Stop a tenth of the zone beyond the far edge in every case. Usage:
#   python ema9_no_retest_backtest.py <datadir> <interval>
import sys, numpy as np, pandas as pd
DATA, IV = sys.argv[1], sys.argv[2]
src = open(__file__.replace("ema9_no_retest_backtest.py", "zone_ema_backtest.py")).read().split("\nr = run()")[0]
g = {}; exec(src, g)
SYMS, load, zones, sim, MAXB = g["SYMS"], g["load"], g["zones"], g["sim"], g["MAXB"]

res = {k: [] for k in ("A", "E2", "Es", "En", "pA", "pE")}
for s in SYMS:
    df = load(s); o, h, l, c = [df[x].values for x in ("Open", "High", "Low", "Close")]
    yard = pd.Series(np.abs(c - o)).rolling(20).median().values
    e9 = df.Close.ewm(span=9, adjust=False).mean().values
    up = c > e9; dn = c < e9
    sig = np.zeros(len(c), int); st = 0
    for i in range(1, len(c)):
        if up[i] and not up[i - 1]: st = 1
        if dn[i] and not dn[i - 1]: st = -1
        sig[i] = st
    flip_b = np.r_[False, up[1:] & ~up[:-1]]; flip_s = np.r_[False, dn[1:] & ~dn[:-1]]
    for (k, sup, top, btm) in zones(o, h, l, c, yard):
        if k < 60: continue
        d = -1 if sup else 1
        near, far = (btm, top) if sup else (top, btm); hgt = top - btm
        stop = far - d * 0.1 * hgt
        target = near + d * 2 * abs(near - stop)
        ra = re = None; done_e = False
        for j in range(k + 1, min(k + 1 + MAXB * 2, len(c))):
            # E: the first 9 EMA flip the zone's way while the zone is fresh and price is still away from it
            if not done_e and (flip_b[j] if d == 1 else flip_s[j]) and (c[j] - near) * d > 0:
                done_e = True
                r2 = sim(h, l, c, j + 1, c[j], stop, c[j] + d * 2 * abs(c[j] - stop), d)
                if r2 is not None:
                    res["E2"].append(r2); re = r2
                    if abs(c[j] - near) <= 2 * hgt: res["En"].append(r2)
                if (target - c[j]) * d > 0:
                    rs = sim(h, l, c, j + 1, c[j], stop, target, d)
                    if rs is not None: res["Es"].append(rs)
            if (l[j] <= near if d == 1 else h[j] >= near):
                e = near if (o[j] - near) * d > 0 else o[j]
                if (e - stop) * d > 0 and sig[j - 1] == d:
                    ra = sim(h, l, c, j, e, stop, target, d)
                break
            if (c[j] - far) * d < 0: break
        if ra is not None: res["A"].append(ra)
        if ra is not None and re is not None: res["pA"].append(ra); res["pE"].append(re)

def f(v):
    v = np.array(v)
    return f"{len(v):5d} trades | win {np.mean(v > 0) * 100:5.1f}% | avg {v.mean():+.2f}R | total {v.sum():+7.1f}R" if len(v) else "no trades"
print(f"\n=== {IV} | {', '.join(SYMS)} ===")
print(f"  A  retest + 9 EMA agrees (current rule)            {f(res['A'])}")
print(f"  E  9 EMA flip, no retest, 2R from entry            {f(res['E2'])}")
print(f"  E' 9 EMA flip, no retest, same target as A         {f(res['Es'])}")
print(f"  E  only when within 2 zone heights of the zone     {f(res['En'])}")
print(f"  same zones (both traded): A {f(res['pA'])}")
print(f"                            E {f(res['pE'])}")
