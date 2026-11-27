# Do touched (used) zones still work as targets, and do counter-trend trades pay when they aim at the nearest zone?
# Part 1, does price stall at a zone: every visit to a zone (price trades into the near edge after closing outside it)
#   counts as a stall when price moves back one zone height away from the near edge before a candle closes through the
#   far edge, within the trade time limit. Split by visit number (1 = fresh, 2 = touched once, 3+ = touched twice or
#   more). Placebo: fake zones of typical height placed 2 to 10 typical bodies away from price at random candles.
# Part 2, counter-trend trades: first touch of a fresh zone, limit at the near edge, stop a tenth of the zone past the
#   far edge. Higher timeframe trend = 12x candles (5m -> 1h, 1h -> 12h), up when the close is above a rising EMA 50,
#   down when below a falling one. Counter-trend = demand in a down trend, supply in an up trend. Targets:
#   FIXED 2R / 3R, FRESH = near edge of the nearest opposing fresh zone, ANY = nearest opposing zone fresh or used
#   (alive = no close through its far edge yet). The FRESH and ANY rows only take the trade when that target pays 2R.
#   A candle hitting both stop and target is a loss; trades open at the time limit are left out.
# Zones as zone_ema_backtest.py (simplified Jay S&D). Usage: python used_zone_target_backtest.py <datadir> <interval>
import sys, numpy as np, pandas as pd
DATA, IV = sys.argv[1], sys.argv[2]
src = open(__file__.replace("used_zone_target_backtest.py", "zone_ema_backtest.py")).read().split("\nr = run()")[0]
g = {}; exec(src, g)
SYMS, load, zones, sim, MAXB = g["SYMS"], g["load"], g["zones"], g["sim"], g["MAXB"]
LIFE = MAXB * 15                    # how far forward a zone is followed
rng = np.random.default_rng(7)

def stall(h, l, c, j, near, far, hgt, d, m=1):
    # d = direction of the reaction (+1 demand, -1 supply); True stall, False broke through, None unresolved
    for t in range(j, min(j + MAXB, len(c))):
        if (c[t] - far) * d < 0: return False
        if (h[t] >= near + m * hgt) if d == 1 else (l[t] <= near - m * hgt): return True
    return None

def trend_htf(df):
    df = df.copy(); df.index = pd.to_datetime(df.index, utc=True)
    r = df[["Open", "High", "Low", "Close"]].resample("1h" if IV == "5m" else "12h").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    e = r.Close.ewm(span=50, adjust=False).mean()
    t = np.where((r.Close > e) & (e > e.shift(1)), 1, np.where((r.Close < e) & (e < e.shift(1)), -1, 0))
    t = pd.Series(t, index=r.index).shift(1)                       # only closed higher timeframe candles
    return t.reindex(df.index, method="ffill").fillna(0).values

P1 = {}
P2 = {}
def add(k, r):
    if r is not None: P2.setdefault(k, []).append(r)

for s in SYMS:
    df = load(s); o, h, l, c = [df[x].values for x in ("Open", "High", "Low", "Close")]
    n = len(c); yard = pd.Series(np.abs(c - o)).rolling(20).median().values
    tr = trend_htf(df)
    Z = []
    for (k, sup, top, btm) in zones(o, h, l, c, yard):
        d = -1 if sup else 1; near, far = (btm, top) if sup else (top, btm)
        e = min(k + 1 + LIFE, n); seg = slice(k + 1, e)
        dead = np.nonzero((c[seg] - far) * d < 0)[0]
        death = k + 1 + dead[0] if len(dead) else e
        jj = np.arange(k + 1, min(death, n - 1) + 1)
        ins = (l[jj] <= near) if d == 1 else (h[jj] >= near)
        out_prev = (c[jj - 1] - near) * d > 0                     # previous candle closed outside the zone
        starts = jj[ins & out_prev]
        Z.append(dict(k=k, d=d, near=near, far=far, hgt=top - btm, death=death, starts=starts))
        for vi, j in enumerate(starts[:6]):
            for m in (1, 2, 3):
                r = stall(h, l, c, j, near, far, top - btm, d, m)
                if r is not None: P1.setdefault(("v1" if vi == 0 else "v2" if vi == 1 else "v3", m), []).append(r)
    hy = np.nanmedian([z["hgt"] / yard[z["k"]] for z in Z if yard[z["k"]] > 0])
    for i in rng.integers(60, n - 10, 3000):
        if not yard[i] > 0: continue
        d = rng.choice([-1, 1]); near = c[i] - d * rng.uniform(2, 10) * yard[i]; hgt = hy * yard[i]
        far = near - d * hgt
        hit = np.nonzero((l[i + 1:] <= near) if d == 1 else (h[i + 1:] >= near))[0]
        if not len(hit) or hit[0] > LIFE: continue
        for m in (1, 2, 3):
            r = stall(h, l, c, i + 1 + hit[0], near, far, hgt, d, m)
            if r is not None: P1.setdefault(("fake", m), []).append(r)
    # part 2
    for z in Z:
        if not len(z["starts"]): continue
        j = z["starts"][0]; d = z["d"]; near, far, hgt = z["near"], z["far"], z["hgt"]
        e = near if (o[j] - near) * d > 0 else o[j]; stop = far - d * 0.1 * hgt; rk = (e - stop) * d
        if rk <= 0: continue
        if tr[j] == 0: continue
        side = "CT" if tr[j] == -d else "WT"
        add(side + "_2R", sim(h, l, c, j, e, stop, e + d * 2 * rk, d))
        add(side + "_3R", sim(h, l, c, j, e, stop, e + d * 3 * rk, d))
        fresh = []; anyz = []
        for y in Z:                                                # opposing zones alive at j, beyond the entry
            if y["d"] != -d or not (y["k"] < j <= y["death"]) or (y["near"] - e) * d <= 0: continue
            used = (y["starts"] < j).any()
            anyz.append(y["near"]);
            if not used: fresh.append(y["near"])
        for name, lv in (("FRESH", fresh), ("ANY", anyz)):
            if not lv: add(f"{side}_{name}_none", 0.0); continue
            tgt = min(lv) if d == 1 else max(lv)
            rr = (tgt - e) * d / rk
            if rr < 2: add(f"{side}_{name}_skip", 0.0); continue
            add(f"{side}_{name}", sim(h, l, c, j, e, stop, tgt, d))
            add(f"{side}_{name}_fix2", sim(h, l, c, j, e, stop, e + d * 2 * rk, d))       # same trades, fixed 2R
            add(f"{side}_{name}_cap3", sim(h, l, c, j, e, stop, e + d * min(rr, 3) * rk, d))  # zone, at most 3R

def p1(v):
    v = np.array(v, bool); return f"{len(v):5d} visits held {v.mean() * 100:5.1f}%"
def p2(k):
    v = np.array(P2.get(k, []))
    return f"{len(v):5d} trades | win {np.mean(v > 0) * 100:5.1f}% | avg {v.mean():+.2f}R | total {v.sum():+7.1f}R" if len(v) else "no trades"
print(f"\n=== {IV} | {', '.join(SYMS)} ===")
print("Part 1: does price turn back at the zone before closing through it (bounce of 1, 2, 3 zone heights)")
for k, nm in (("v1", "fresh zone, first visit"), ("v2", "touched once, second visit"), ("v3", "touched 2+, third visit on"),
              ("fake", "placebo: random fake zone")):
    print(f"  {nm:28s}" + " || ".join(f"{m}x {p1(P1[(k, m)])}" for m in (1, 2, 3)))
print("Part 2: first touch of a fresh zone, by higher timeframe trend (close vs EMA 50)")
for side, nm in (("WT", "with the trend"), ("CT", "counter-trend")):
    print(f"  {nm}")
    print(f"    fixed 2R, every trade                      {p2(side + '_2R')}")
    print(f"    fixed 3R, every trade                      {p2(side + '_3R')}")
    for t, tn in (("FRESH", "nearest fresh zone"), ("ANY", "nearest zone, fresh or used")):
        sk = len(P2.get(f"{side}_{t}_skip", [])); no = len(P2.get(f"{side}_{t}_none", []))
        print(f"    target {tn:36s}{p2(side + '_' + t)}  (skipped: under 2R {sk}, no zone {no})")
        print(f"      same trades, zone target capped at 3R    {p2(side + '_' + t + '_cap3')}")
        print(f"      same trades, fixed 2R                    {p2(side + '_' + t + '_fix2')}")
