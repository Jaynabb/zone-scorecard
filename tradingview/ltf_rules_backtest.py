# Lower timeframe rules backtest, three questions:
#   1. Mentor's "one and done": is a zone under 1 hour still worth trading on its 2nd or 3rd touch?
#   2. No-retest entries on 5m: gap-away rule, entering when the zone forms, versus the retest.
#   3. Exit ideas from Best Loser Wins (Hougaard) and Trading in the Zone (Douglas) on the 5m retest + 9 EMA rule.
# Zones and the trade model follow zone_ema_backtest.py (stop a tenth of the zone past the far edge, 2R from the
# near edge, a candle touching both stop and target is a loss). 15m and 30m are built from the 5m data.
# Usage: python ltf_rules_backtest.py <datadir> [intervals for 2 and 3, default 5m] [--fill=path|close|wick]
import sys, numpy as np, pandas as pd
DATA = sys.argv[1]
FILL = "path"
for a in list(sys.argv):
    if a.startswith("--fill="): FILL = a[7:]; sys.argv.remove(a)
SYMS = ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD", "NQ"]
MAXB = {"5m": 288, "15m": 96, "30m": 48, "1h": 120, "1d": 120}   # about a day intraday, 5 days on 1h, 6 months on 1d
src = open(__file__.replace("ltf_rules_backtest.py", "zone_ema_backtest.py")).read()
g = {"np": np}; exec("def zones" + src.split("\ndef zones")[1].split("\ndef sim")[0], g)
zones = g["zones"]

def load(s, iv):
    f = "5m" if iv in ("15m", "30m") else iv
    df = pd.read_csv(f"{DATA}/{s}_{f}.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    if f != iv:
        df = df.resample(iv.replace("m", "min")).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    return df[df.High > df.Low]

def ema9_sig(c):
    e9 = pd.Series(c).ewm(span=9, adjust=False).mean().values
    up = c > e9; dn = c < e9
    sig = np.zeros(len(c), int); st = 0
    for i in range(1, len(c)):
        if up[i] and not up[i - 1]: st = 1
        if dn[i] and not dn[i - 1]: st = -1
        sig[i] = st
    return sig, e9

OPEN = [None]

def path(h, l, c, j, e, risk, d, n, fill=False):
    o_ = OPEN[0]
    # bar by bar favourable / adverse / close excursion in R from the entry candle on
    # fill=True: filled inside candle j (a retest limit). Its extreme in our favour most likely printed before the
    # fill, so only its close counts in our favour; its extreme against us still counts.
    sl = slice(j, min(j + n, len(c)))
    if d == 1: fav, adv, cl = (h[sl] - e) / risk, (l[sl] - e) / risk, (c[sl] - e) / risk
    else: fav, adv, cl = (e - l[sl]) / risk, (e - h[sl]) / risk, (e - c[sl]) / risk
    # FILL = "close": only the close counts (worst case). "path": a green candle runs open, low, high, close and a red
    # one open, high, low, close, so a long filled on a green candle keeps its high (middle estimate).
    # "wick": the whole candle counts (what the earlier backtests did, best case).
    if fill and len(fav) and FILL != "wick":
        keep = FILL == "path" and (c[j] > o_[j] if d == 1 else c[j] < o_[j])
        if not keep: fav = fav.copy(); fav[0] = max(cl[0], 0.0)
    return fav, adv, cl

def fixed(p, t):
    fav, adv, _ = p
    for i in range(len(fav)):
        if adv[i] <= -1: return -1.0
        if fav[i] >= t: return t
    return None

def trail_ema(fav, adv, cl, eb, trig=1.0):
    # stop to breakeven at 1R, then ride until a candle closes back across the 9 EMA
    st, on = -1.0, False
    for i in range(len(fav)):
        if adv[i] <= st: return st
        if on and eb[i]: return cl[i]
        if fav[i] >= trig: on = True; st = max(st, 0.0)
    return cl[-1] if on else None

def ema_back(c, e9, j, n, d):
    x = slice(j, min(j + n, len(c)))
    return c[x] < e9[x] if d == 1 else c[x] > e9[x]

def stats(v):
    v = np.array([x for x in v if x is not None])
    if not len(v): return "no trades"
    return f"{len(v):5d} trades | win {np.mean(v > 0) * 100:5.1f}% | avg {v.mean():+.2f}R | total {v.sum():+7.1f}R"

# ---------------------------------------------------------------- 1. one and done
print("\n#### 1. Touch number: retest entry, 2R, trade every touch while the zone lives")
for iv in ("5m", "15m", "30m", "1h", "1d"):
    res = {(n, f): [] for n in (1, 2, 3) for f in ("all", "ema", "trail")}; per = {}
    for s in SYMS:
        df = load(s, iv); o, h, l, c = [df[x].values for x in ("Open", "High", "Low", "Close")]; OPEN[0] = o
        yard = pd.Series(np.abs(c - o)).rolling(20).median().values
        sig, e9 = ema9_sig(c)
        for (k, sup, top, btm) in zones(o, h, l, c, yard):
            if k < 60: continue
            d = -1 if sup else 1
            near, far = (btm, top) if sup else (top, btm); hgt = top - btm
            stop = far - d * 0.1 * hgt; risk = abs(near - stop)
            touches, inside = 0, False
            for j in range(k + 1, min(k + 1 + MAXB[iv] * 4, len(c))):
                touching = l[j] <= near if d == 1 else h[j] >= near
                if touching and not inside:
                    touches += 1
                    if touches > 3: break
                    e = near if (o[j] - near) * d > 0 else o[j]
                    if (e - stop) * d > 0:
                        p = path(h, l, c, j, e, (e - stop) * d, d, MAXB[iv], True)
                        r = fixed(p, 2 * risk / ((e - stop) * d))
                        res[(touches, "all")].append(r)
                        if sig[j - 1] == d:
                            res[(touches, "ema")].append(r); per.setdefault((s, touches), []).append(r)
                            res[(touches, "trail")].append(trail_ema(*p, ema_back(c, e9, j, MAXB[iv], d)))
                closed_out = (c[j] - near) * d > 0
                inside = touching and not closed_out
                if (c[j] - far) * d < 0: break     # zone dies on a close through the far edge
    print(f"\n  {iv}")
    for n in (1, 2, 3):
        print(f"    touch {n}  any EMA  {stats(res[(n, 'all')])}")
        print(f"    touch {n}  EMA ok   {stats(res[(n, 'ema')])}")
        print(f"    touch {n}  EMA ok, ride the 9 EMA exit  {stats(res[(n, 'trail')])}")
    def av(x): x = [y for y in x if y is not None]; return f"{np.mean(x):+.2f}" if x else "  -  "
    print("    by symbol, EMA ok, avg R touch 1 / 2 / 3: " + " | ".join(f"{s} {av(per.get((s, 1), []))} {av(per.get((s, 2), []))} {av(per.get((s, 3), []))}" for s in SYMS))

for iv in sys.argv[2:] or ['5m']:
    # ---------------------------------------------------------------- 2. no-retest entries on 5m
    print(f"\n#### 2. No-retest entries on {iv} (fresh zones only)")
    res = {k: [] for k in ("R", "R_ema", "G2", "Gs", "Gr", "Gr_ema", "F2", "Fs", "F2_ema")}
    for s in SYMS:
        df = load(s, iv); o, h, l, c = [df[x].values for x in ("Open", "High", "Low", "Close")]; OPEN[0] = o
        yard = pd.Series(np.abs(c - o)).rolling(20).median().values
        sig, _ = ema9_sig(c)
        body = np.abs(c - o)
        for (k, sup, top, btm) in zones(o, h, l, c, yard):
            if k < 60: continue
            d = -1 if sup else 1
            near, far = (btm, top) if sup else (top, btm); hgt = top - btm
            stop = far - d * 0.1 * hgt; risk = abs(near - stop); target = near + d * 2 * risk
            # impulse candle: last candle before k whose body is the drive away from the base
            i = next((x for x in range(k, max(k - 9, 0), -1) if body[x] >= yard[x] and (c[x] - o[x]) * d > 0
                      and (min(l[x - 1], o[x - 1]) <= near if d == 1 else max(h[x - 1], o[x - 1]) >= near)), None)
            gap = i is not None and ((o[i] > h[i - 1] + 0.1 * yard[i]) if d == 1 else (o[i] < l[i - 1] - 0.1 * yard[i]))
            # F / G: market entry at the close of the candle that confirms the zone
            e = c[k]; rk = (e - stop) * d
            p = path(h, l, c, k + 1, e, rk, d, MAXB[iv])
            f2, fs = fixed(p, 2), fixed(p, (target - e) * d / rk) if (target - e) * d > 0 else None
            res["F2"].append(f2); res["Fs"].append(fs)
            if sig[k] == d: res["F2_ema"].append(f2)
            if gap: res["G2"].append(f2); res["Gs"].append(fs)
            # R: the retest (current rule)
            for j in range(k + 1, min(k + 1 + MAXB[iv] * 2, len(c))):
                if (l[j] <= near if d == 1 else h[j] >= near):
                    e2 = near if (o[j] - near) * d > 0 else o[j]
                    if (e2 - stop) * d > 0:
                        r = fixed(path(h, l, c, j, e2, (e2 - stop) * d, d, MAXB[iv], True), 2 * risk / ((e2 - stop) * d))
                        res["R"].append(r)
                        if sig[j - 1] == d: res["R_ema"].append(r)
                        if gap:
                            res["Gr"].append(r)
                            if sig[j - 1] == d: res["Gr_ema"].append(r)
                    break
                if (c[j] - far) * d < 0: break
    print(f"  R   retest, any EMA                               {stats(res['R'])}")
    print(f"  R   retest + 9 EMA agrees (current rule)          {stats(res['R_ema'])}")
    print(f"  F   enter when the zone forms, 2R from entry      {stats(res['F2'])}")
    print(f"  F   same, only when 9 EMA already agrees          {stats(res['F2_ema'])}")
    print(f"  F'  enter when the zone forms, retest's target    {stats(res['Fs'])}")
    print(f"  G   gap-away zones, enter when formed, 2R         {stats(res['G2'])}")
    print(f"  G'  gap-away zones, enter when formed, R target   {stats(res['Gs'])}")
    print(f"  Gr  gap-away zones, wait for the retest           {stats(res['Gr'])}")
    print(f"  Gr  gap-away zones, retest + EMA                  {stats(res['Gr_ema'])}")

    # ---------------------------------------------------------------- 3. exit ideas from the books
    print(f"\n#### 3. Exits on the {iv} retest + 9 EMA trades (same entries, same stop, 2R measured from the fill)")
    P = {}; seq = []
    for s in SYMS:
        df = load(s, iv); o, h, l, c = [df[x].values for x in ("Open", "High", "Low", "Close")]; OPEN[0] = o
        yard = pd.Series(np.abs(c - o)).rolling(20).median().values
        sig, e9 = ema9_sig(c)
        for (k, sup, top, btm) in zones(o, h, l, c, yard):
            if k < 60: continue
            d = -1 if sup else 1
            near, far = (btm, top) if sup else (top, btm); hgt = top - btm
            stop = far - d * 0.1 * hgt
            for j in range(k + 1, min(k + 1 + MAXB[iv] * 2, len(c))):
                if (l[j] <= near if d == 1 else h[j] >= near):
                    e = near if (o[j] - near) * d > 0 else o[j]; rk = (e - stop) * d
                    if rk > 0 and sig[j - 1] == d:
                        fav, adv, cl = path(h, l, c, j, e, rk, d, MAXB[iv], True)
                        eb = ema_back(c, e9, j, MAXB[iv], d)
                        seq.append((df.index[j], (fav, adv, cl, eb), s))
                    break
                if (c[j] - far) * d < 0: break
    seq.sort(key=lambda x: x[0]); trades = [x[1] for x in seq]; tsym = [x[2] for x in seq]

    def be(t, fav, adv, cl, trig=1.0):
        st, hit = -1.0, False
        for i in range(len(fav)):
            if adv[i] <= st: return st
            if fav[i] >= t: return t
            if fav[i] >= trig: st = 0.0         # move to breakeven from the next candle on
        return None

    def partial(fav, adv, cl, t1=1.0, t2=3.0):
        st, half = -1.0, False
        for i in range(len(fav)):
            if adv[i] <= st: return (0.5 * t1 if half else 0) + (0.5 if half else 1) * st
            if not half and fav[i] >= t1: half = True; st_next = 0.0
            if half and fav[i] >= t2: return 0.5 * t1 + 0.5 * t2
            if half: st = 0.0
        return None

    def time_stop(fav, adv, cl, n, need=0.5, t=2.0):
        # Hougaard: a good trade works quickly. Out at the close of candle n if it never got need R in its favour
        best = -9
        for i in range(len(fav)):
            if adv[i] <= -1: return -1.0
            if fav[i] >= t: return t
            best = max(best, fav[i])
            if i == n - 1 and best < need: return cl[i]
        return None

    def pyramid(fav, adv, cl, add=1.0, t=3.0):
        # add a second unit at +1R, both stops to the first entry, both target 3R from the first entry
        added = False; st = -1.0
        for i in range(len(fav)):
            if adv[i] <= st: return (0.0 + (-add) if added else -1.0)
            if fav[i] >= t: return t + ((t - add) if added else 0)
            if not added and fav[i] >= add: added = True; st = 0.0
        return None

    rules = {
        "fixed 2R (current)": lambda f, a, c, e: fixed((f, a, c), 2),
        "fixed 1R": lambda f, a, c, e: fixed((f, a, c), 1),
        "fixed 3R": lambda f, a, c, e: fixed((f, a, c), 3),
        "2R, stop to breakeven at 1R": lambda f, a, c, e: be(2, f, a, c),
        "3R, stop to breakeven at 1R": lambda f, a, c, e: be(3, f, a, c),
        "half off at 1R, rest 3R at breakeven": lambda f, a, c, e: partial(f, a, c),
        "BE at 1R then ride until close over 9 EMA": lambda f, a, c, e: trail_ema(f, a, c, e),
        "time stop: out after 6 candles if < +0.5R": lambda f, a, c, e: time_stop(f, a, c, 6),
        "time stop: out after 12 candles if < +0.5R": lambda f, a, c, e: time_stop(f, a, c, 12),
        "add a unit at +1R, both to 3R, stops at entry": lambda f, a, c, e: pyramid(f, a, c),
    }
    for name, fn in rules.items():
        print(f"  {name:48s} {stats([fn(*t) for t in trades])}")
    for name in ("fixed 2R (current)", "BE at 1R then ride until close over 9 EMA"):
        out = [rules[name](*t) for t in trades]
        print(f"    {name} by symbol: " + " | ".join(f"{y} {np.mean([r for r, z in zip(out, tsym) if z == y and r is not None]):+.2f}" for y in SYMS))

    # Douglas: the edge only shows over a series. How bad do the streaks get on the current rule?
    v = np.array([x for x in (fixed((t[0], t[1], t[2]), 2) for t in trades) if x is not None])
    streak = mx = 0
    for x in v:
        streak = streak + 1 if x < 0 else 0; mx = max(mx, streak)
    w20 = np.array([v[i:i + 20].sum() for i in range(len(v) - 19)])
    print(f"\n  Current rule as a series of {len(v)} trades: longest losing streak {mx}, "
          f"20-trade windows: worst {w20.min():+.0f}R, best {w20.max():+.0f}R, {np.mean(w20 < 0) * 100:.0f}% of windows lose money")
    rng = np.random.default_rng(1)
    sims = [max((len(x) for x in "".join("L" if y < 0 else "W" for y in rng.choice(v, 100)).split("W")), default=0) for _ in range(5000)]
    print(f"  Shuffled 100-trade runs at this win rate: longest losing streak median {int(np.median(sims))}, 95th pct {int(np.percentile(sims, 95))}")
