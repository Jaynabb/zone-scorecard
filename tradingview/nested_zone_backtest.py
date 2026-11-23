# Nested zones: a Low timeframe zone sitting inside a Mid timeframe zone of the same side (Daily inside Weekly, or
# 5m inside 30m). Price reaches the Mid zone first. Is it better to enter on that first touch of the Mid zone, or to
# wait for the Low zone inside it (the current rule)? Same zone pairs for every variant. Fills follow the candle path
# rule from ltf_rules_backtest.py (a retest candle only keeps its favourable extreme when it closed in our favour).
# Usage: python nested_zone_backtest.py <datadir> [--empty]  (--empty: the Mid zone touched before any Low zone sits inside it)
import sys, numpy as np, pandas as pd
DATA = sys.argv[1]
SYMS = ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD", "NQ"]
src = open(__file__.replace("nested_zone_backtest.py", "zone_ema_backtest.py")).read()
g = {"np": np}; exec("def zones" + src.split("\ndef zones")[1].split("\ndef sim")[0], g); zones = g["zones"]

def load(s, f):
    df = pd.read_csv(f"{DATA}/{s}_{f}.csv", index_col=0); df.index = pd.to_datetime(df.index, utc=True)
    df = df[["Open", "High", "Low", "Close"]].dropna(); return df[df.High > df.Low]

def sim(o, h, l, c, e9, j, e, stop, d, maxb, fill, mode):
    # mode "2R": fixed 2R. mode "ema": breakeven at +1R, then out on a close back across the 9 EMA
    risk = (e - stop) * d
    if risk <= 0: return None
    st, on = -1.0, False
    for i in range(j, min(j + maxb, len(c))):
        fav = ((h[i] - e) if d == 1 else (e - l[i])) / risk
        adv = ((l[i] - e) if d == 1 else (e - h[i])) / risk
        cl = (c[i] - e) * d / risk
        if fill and i == j and not ((c[i] > o[i]) if d == 1 else (c[i] < o[i])): fav = max(cl, 0.0)
        if adv <= st: return st
        if mode == "2R" and fav >= 2: return 2.0
        if mode == "ema" and on and ((c[i] < e9[i]) if d == 1 else (c[i] > e9[i])): return cl
        if fav >= 1 and mode == "ema": on = True; st = max(st, 0.0)
    return None

def run(lf, group, maxb, label):
    res = {k: [] for k in ("A", "B", "B2", "Aema", "Bema", "B2ema")}; n_pairs = n_missed = 0
    for s in SYMS:
        df = load(s, lf); o, h, l, c = [df[x].values for x in ("Open", "High", "Low", "Close")]
        e9 = pd.Series(c).ewm(span=9, adjust=False).mean().values
        gid = group(df.index)
        hdf = df.groupby(gid).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"})
        first_bar = pd.Series(np.arange(len(df)), index=df.index).groupby(gid).min().values   # first Low bar of each Mid bar
        ho, hh, hl, hc = [hdf[x].values for x in ("Open", "High", "Low", "Close")]
        hz = [(first_bar[k + 1], sup, top, btm) for (k, sup, top, btm) in
              zones(ho, hh, hl, hc, pd.Series(np.abs(hc - ho)).rolling(20).median().values) if k + 1 < len(first_bar)]
        lz = zones(o, h, l, c, pd.Series(np.abs(c - o)).rolling(20).median().values)
        for (kh, sup, ht, hb) in hz:
            d = -1 if sup else 1
            h_near, h_far = (hb, ht) if sup else (ht, hb)
            # Low zones of the same side inside this Mid zone, known by the time the Mid zone is
            inner = [(kl, t, b) for (kl, s2, t, b) in lz if s2 == sup and b >= hb - 1e-12 and t <= ht + 1e-12
                     and kh - maxb * 3 <= kl <= kh and (t - b) < (ht - hb) * 0.9]
            if not inner: continue
            kl, lt, lb = max(inner)                                   # the latest such Low zone
            l_near, l_far = (lb, lt) if sup else (lt, lb)
            if (l_near - h_near) * d >= 0 and abs(l_near - h_near) < 1e-12: continue   # same near edge: no difference
            start = max(kh, kl) + 1
            a0 = min(kl, kh) + 1
            if start >= len(c) or (start > a0 and (l[a0:start].min() <= h_near if d == 1 else h[a0:start].max() >= h_near)): continue
            n_pairs += 1
            jB = jA = None
            for j in range(start, min(start + maxb * 3, len(c))):
                if jB is None and (l[j] <= h_near if d == 1 else h[j] >= h_near): jB = j
                if jB is not None and (l[j] <= l_near if d == 1 else h[j] >= l_near): jA = j; break
                if (c[j] - h_far) * d < 0: break
                if jB is not None and (c[j] - l_far) * d < 0: break
            if jB is None: continue
            eB = h_near if (o[jB] - h_near) * d > 0 else o[jB]
            sB = h_far - d * 0.1 * (ht - hb); sL = l_far - d * 0.1 * (lt - lb)
            res["B"].append(sim(o, h, l, c, e9, jB, eB, sB, d, maxb, True, "2R")); res["Bema"].append(sim(o, h, l, c, e9, jB, eB, sB, d, maxb, True, "ema"))
            res["B2"].append(sim(o, h, l, c, e9, jB, eB, sL, d, maxb, True, "2R")); res["B2ema"].append(sim(o, h, l, c, e9, jB, eB, sL, d, maxb, True, "ema"))
            if jA is None: n_missed += 1; continue
            eA = l_near if (o[jA] - l_near) * d > 0 else o[jA]
            res["A"].append(sim(o, h, l, c, e9, jA, eA, sL, d, maxb, True, "2R")); res["Aema"].append(sim(o, h, l, c, e9, jA, eA, sL, d, maxb, True, "ema"))
    def f(v):
        v = np.array([x for x in v if x is not None])
        return f"{len(v):5d} trades | win {np.mean(v > 0) * 100:5.1f}% | avg {v.mean():+.2f}R | total {v.sum():+7.1f}R" if len(v) else "no trades"
    print(f"\n=== {label}: {n_pairs} nested zone pairs; the Low zone was never reached after the Mid touch in {n_missed} ===")
    print(f"  A   wait for the Low zone (current)          2R {f(res['A'])}")
    print(f"                                       9 EMA exit {f(res['Aema'])}")
    print(f"  B   enter on the Mid zone, Mid stop          2R {f(res['B'])}")
    print(f"                                       9 EMA exit {f(res['Bema'])}")
    print(f"  B2  enter on the Mid zone, Low zone stop     2R {f(res['B2'])}")
    print(f"                                       9 EMA exit {f(res['B2ema'])}")

def ema9_sig(c):
    e9 = pd.Series(c).ewm(span=9, adjust=False).mean().values
    up = c > e9; dn = c < e9; sig = np.zeros(len(c), int); st = 0
    for i in range(1, len(c)):
        if up[i] and not up[i - 1]: st = 1
        if dn[i] and not dn[i - 1]: st = -1
        sig[i] = st
    return sig

# Jay's case (PEP, 2026-11-23): the first touch of a fresh Mid zone comes before any Low zone sits inside it, and the
# Low zone forms from that bounce. E = enter on the Mid touch (Mid stop). W = wait for the Low zone that forms from
# the bounce and take its first retest (current rule); when that retest never comes, W has no trade (counted as missed).
# "EMA ok" keeps only entries where the standing 9 EMA signal points the trade's way.
def run_empty(lf, group, maxb, label):
    keys = ("E", "Eema", "E_ok", "Eema_ok", "W", "Wema", "W_ok", "Wema_ok", "N", "N_ok")
    res = {k: [] for k in keys}; n_ev = n_missed = 0
    for s in SYMS:
        df = load(s, lf); o, h, l, c = [df[x].values for x in ("Open", "High", "Low", "Close")]
        e9 = pd.Series(c).ewm(span=9, adjust=False).mean().values; sig = ema9_sig(c)
        gid = group(df.index)
        hdf = df.groupby(gid).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"})
        first_bar = pd.Series(np.arange(len(df)), index=df.index).groupby(gid).min().values
        ho, hh, hl, hc = [hdf[x].values for x in ("Open", "High", "Low", "Close")]
        hz = [(first_bar[k + 1], sup, top, btm) for (k, sup, top, btm) in
              zones(ho, hh, hl, hc, pd.Series(np.abs(hc - ho)).rolling(20).median().values) if k + 1 < len(first_bar)]
        lz = zones(o, h, l, c, pd.Series(np.abs(c - o)).rolling(20).median().values)
        for (kh, sup, ht, hb) in hz:
            d = -1 if sup else 1
            h_near, h_far = (hb, ht) if sup else (ht, hb)
            jB = None
            for j in range(kh, min(kh + maxb * 6, len(c))):
                if (l[j] <= h_near if d == 1 else h[j] >= h_near): jB = j; break
                if (c[j] - h_far) * d < 0: break
            if jB is None: continue
            inside = [1 for (kl, s2, t, b) in lz if s2 == sup and kl < jB and t >= hb and b <= ht and kl >= kh - maxb * 6]
            eB = h_near if (o[jB] - h_near) * d > 0 else o[jB]
            sB = h_far - d * 0.1 * (ht - hb)
            ok = sig[jB - 1] == d
            if inside:
                r = sim(o, h, l, c, e9, jB, eB, sB, d, maxb, True, "2R"); res["N"].append(r)
                if ok: res["N_ok"].append(r)
                continue
            n_ev += 1
            r2 = sim(o, h, l, c, e9, jB, eB, sB, d, maxb, True, "2R"); re = sim(o, h, l, c, e9, jB, eB, sB, d, maxb, True, "ema")
            res["E"].append(r2); res["Eema"].append(re)
            if ok: res["E_ok"].append(r2); res["Eema_ok"].append(re)
            # W: the first Low zone of this side that forms from the bounce (known within maxb bars after the touch,
            # overlapping the Mid zone), then its first retest while it and the Mid zone live
            born = [(kl, t, b) for (kl, s2, t, b) in lz if s2 == sup and jB <= kl <= jB + maxb and t >= hb and b <= ht]
            if not born: n_missed += 1; res["W"].append(0.0); res["Wema"].append(0.0); continue
            kl, lt, lb = min(born)
            l_near, l_far = (lb, lt) if sup else (lt, lb)
            jA = None
            for j in range(kl + 1, min(kl + 1 + maxb * 3, len(c))):
                if (l[j] <= l_near if d == 1 else h[j] >= l_near): jA = j; break
                if (c[j] - l_far) * d < 0 or (c[j] - h_far) * d < 0: break
            if jA is None: n_missed += 1; res["W"].append(0.0); res["Wema"].append(0.0); continue
            eA = l_near if (o[jA] - l_near) * d > 0 else o[jA]; sA = l_far - d * 0.1 * (lt - lb)
            w2 = sim(o, h, l, c, e9, jA, eA, sA, d, maxb, True, "2R"); we = sim(o, h, l, c, e9, jA, eA, sA, d, maxb, True, "ema")
            res["W"].append(w2); res["Wema"].append(we)
            if sig[jA - 1] == d: res["W_ok"].append(w2); res["Wema_ok"].append(we)
    def f(v):
        v = np.array([x for x in v if x is not None])
        return f"{len(v):5d} | win {np.mean(v > 0) * 100:5.1f}% | avg {v.mean():+.2f}R | total {v.sum():+7.1f}R" if len(v) else "no trades"
    print(f"\n=== {label}: {n_ev} first touches of a Mid zone with no Low zone inside; waiting missed the trade in {n_missed} ===")
    print(f"  E  enter on the Mid touch         2R  {f(res['E'])}")
    print(f"                             9 EMA exit {f(res['Eema'])}")
    print(f"     same, EMA agrees               2R  {f(res['E_ok'])}")
    print(f"                             9 EMA exit {f(res['Eema_ok'])}")
    print(f"  W  wait for the Low zone retest   2R  {f(res['W'])}   (missed = 0R)")
    print(f"                             9 EMA exit {f(res['Wema'])}")
    print(f"     same, EMA agrees               2R  {f(res['W_ok'])}")
    print(f"                             9 EMA exit {f(res['Wema_ok'])}")
    print(f"  for contrast, Mid touches that DID have a Low zone inside, 2R: {f(res['N'])} | EMA agrees {f(res['N_ok'])}")

if "--empty" in sys.argv:
    run_empty("1d", lambda ix: ix.tz_convert(None).to_period("W").start_time, 120, "Daily inside Weekly")
    run_empty("5m", lambda ix: ix.floor("30min"), 288, "5m inside 30m")
    run_empty("1h", lambda ix: ix.floor("4h"), 120, "1H inside 4H")
    sys.exit()
run("1d", lambda ix: ix.tz_convert(None).to_period("W").start_time, 120, "Daily inside Weekly")
run("5m", lambda ix: ix.floor("30min"), 288, "5m inside 30m")
run("1h", lambda ix: ix.floor("4h"), 120, "1H inside 4H")
