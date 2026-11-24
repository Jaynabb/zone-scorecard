# Stop placement backtest: how far past the far edge should the stop sit on a Touch entry (first touch, limit at the
# near edge)? A stop a tenth of the zone height past the far edge (the indicator's rule) gets wicked out on fast
# Low timeframes. Variants: a tenth of the zone (current), half and one ATR(14) past the far edge, and a close stop
# (out only when a candle CLOSES past the far edge, with a hard stop one ATR past it). R is always measured against
# the stop actually used, so a wider stop means a smaller position for the same dollar risk.
# Exits: fixed 2R, and breakeven at 1R then out on a close back across the 9 EMA. Usage: python stop_buffer_backtest.py <datadir>
import sys, numpy as np, pandas as pd
DATA = sys.argv[1]
SYMS = ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD", "NQ"]
MAXB = {"5m": 288, "15m": 192, "1h": 120, "4h": 60}
src = open(__file__.replace("stop_buffer_backtest.py", "ltf_rules_backtest.py")).read()
g = {"np": np, "pd": pd, "FILL": "path"}
exec("def ema9_sig" + src.split("\ndef ema9_sig")[1].split("\ndef stats")[0], g)
zsrc = open(__file__.replace("stop_buffer_backtest.py", "zone_ema_backtest.py")).read()
exec("def zones" + zsrc.split("\ndef zones")[1].split("\ndef sim")[0], g)
zones, path, fixed, trail_ema, ema_back, ema9_sig, OPEN = (g[x] for x in ("zones", "path", "fixed", "trail_ema", "ema_back", "ema9_sig", "OPEN"))

def load(s, iv):
    base = {"5m": "5m", "15m": "5m", "1h": "1h", "4h": "1h"}[iv]
    df = pd.read_csv(f"{DATA}/{s}_{base}.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    if base != iv:
        df = df.resample(iv.replace("m", "min")).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    return df[df.High > df.Low]

def close_stop(h, l, c, j, e, far, hard, d, n, first_close_only):
    # risk = entry to the hard stop. Out on a close past the far edge (at that close), or the hard stop on a wick
    risk = (e - hard) * d
    fav, adv, cl = path(h, l, c, j, e, risk, d, n, True)
    end = min(j + n, len(c))
    closes_out = ((c[j:end] - far) * d < 0)
    return fav, adv, cl, closes_out

def run_close(p, target, eb=None):
    fav, adv, cl, out = p
    st, on = -1.0, False
    for i in range(len(fav)):
        if adv[i] <= st: return st
        if out[i] and not on: return cl[i]
        if target and fav[i] >= target: return target
        if eb is not None:
            if on and eb[i]: return cl[i]
            if fav[i] >= 1.0: on = True; st = max(st, 0.0)
    return cl[-1] if (eb is not None and on) else None

def stats(v):
    v = np.array([x for x in v if x is not None])
    if not len(v): return "no trades"
    return f"{len(v):5d} | win {np.mean(v > 0) * 100:5.1f}% | stopped {np.mean(v <= -0.99) * 100:5.1f}% | avg {v.mean():+.3f}R | total {v.sum():+7.1f}R"

RULES = ["0.1 zone (now)", "0.5 ATR", "1.0 ATR", "close stop"]
for iv in ("5m", "15m", "1h"):
    R = {(r, x): [] for r in RULES for x in ("2R", "ema")}
    for s in SYMS:
        df = load(s, iv); o, h, l, c = [df[x].values for x in ("Open", "High", "Low", "Close")]; OPEN[0] = o
        atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - np.roll(c, 1)), abs(l - np.roll(c, 1))))).rolling(14).mean().values
        yard = pd.Series(np.abs(c - o)).rolling(20).median().values
        sig, e9 = ema9_sig(c)
        n = MAXB[iv]
        for (k, sup, top, btm) in zones(o, h, l, c, yard):
            if k < 60: continue
            d = -1 if sup else 1
            near, far = (btm, top) if sup else (top, btm); hgt = top - btm
            j = k + 1
            end = min(k + 1 + n * 4, len(c))
            while j < end and not (l[j] <= near if d == 1 else h[j] >= near): j += 1
            if j >= end: continue
            a = atr[j - 1]
            if not a > 0: continue
            e = near if (o[j] - near) * d > 0 else o[j]
            if (e - far) * d <= 0: continue
            eb = ema_back(c, e9, j, n, d)
            for r, buf in (("0.1 zone (now)", 0.1 * hgt), ("0.5 ATR", 0.5 * a), ("1.0 ATR", 1.0 * a)):
                stop = far - d * buf
                p = path(h, l, c, j, e, (e - stop) * d, d, n, True)
                R[(r, "2R")].append(fixed(p, 2.0)); R[(r, "ema")].append(trail_ema(*p, eb))
            p = close_stop(h, l, c, j, e, far, far - d * 1.0 * a, d, n, True)
            R[("close stop", "2R")].append(run_close(p, 2.0)); R[("close stop", "ema")].append(run_close(p, None, eb))
    print(f"\n#### {iv}: first touch, limit at the near edge")
    for x in ("2R", "ema"):
        for r in RULES: print(f"  {x:3s} {r:15s} {stats(R[(r, x)])}")
