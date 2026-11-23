# Which entry-candle assumption is right? Replays the 5m retest + 9 EMA trades (first touch, 2R) minute by minute
# using 1m data, and compares with the three 5m estimates in ltf_rules_backtest.py (--fill=wick|path|close).
# 5m candles are built from the same 1m data. Usage: python fill_check_1m.py <dir with SYMBOL_1m.csv>
import sys, numpy as np, pandas as pd
DATA = sys.argv[1]
SYMS = ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD", "NQ"]
src = open(__file__.replace("fill_check_1m.py", "zone_ema_backtest.py")).read()
g = {"np": np}; exec("def zones" + src.split("\ndef zones")[1].split("\ndef sim")[0], g); zones = g["zones"]
MAXB = 288

def walk(fav, adv, t):
    for i in range(len(fav)):
        if adv[i] <= -1: return -1.0
        if fav[i] >= t: return t
    return None

res = {k: [] for k in ("wick", "path", "close", "1m")}
for s in SYMS:
    m = pd.read_csv(f"{DATA}/{s}_1m.csv", index_col=0); m.index = pd.to_datetime(m.index, utc=True)
    m = m[["Open", "High", "Low", "Close"]].dropna()
    df = m.resample("5min").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    df = df[df.High > df.Low]
    o, h, l, c = [df[x].values for x in ("Open", "High", "Low", "Close")]
    mo, mh, ml, mc = [m[x].values for x in ("Open", "High", "Low", "Close")]; mt = m.index.values
    yard = pd.Series(np.abs(c - o)).rolling(20).median().values
    e9 = pd.Series(c).ewm(span=9, adjust=False).mean().values
    up = c > e9; dn = c < e9; sig = np.zeros(len(c), int); st = 0
    for i in range(1, len(c)):
        if up[i] and not up[i - 1]: st = 1
        if dn[i] and not dn[i - 1]: st = -1
        sig[i] = st
    for (k, sup, top, btm) in zones(o, h, l, c, yard):
        if k < 60: continue
        d = -1 if sup else 1
        near, far = (btm, top) if sup else (top, btm); hgt = top - btm
        stop = far - d * 0.1 * hgt
        for j in range(k + 1, min(k + 1 + MAXB * 2, len(c))):
            if (l[j] <= near if d == 1 else h[j] >= near):
                e = near if (o[j] - near) * d > 0 else o[j]; rk = (e - stop) * d
                if rk > 0 and sig[j - 1] == d:
                    sl = slice(j, min(j + MAXB, len(c)))
                    fav = ((h[sl] - e) if d == 1 else (e - l[sl])) / rk
                    adv = ((l[sl] - e) if d == 1 else (e - h[sl])) / rk
                    cl = ((c[sl] - e) if d == 1 else (e - c[sl])) / rk
                    res["wick"].append(walk(fav, adv, 2))
                    green = c[j] > o[j] if d == 1 else c[j] < o[j]
                    f2 = fav.copy(); f2[0] = max(cl[0], 0); res["close"].append(walk(f2, adv, 2))
                    res["path"].append(walk(fav if green else f2, adv, 2))
                    # 1m replay: first minute of candle j that reaches the entry, then minute by minute
                    a = np.searchsorted(mt, df.index.values[j]); b = np.searchsorted(mt, df.index.values[j] + np.timedelta64(5, "m"))
                    hit = [x for x in range(a, b) if (ml[x] <= e if d == 1 else mh[x] >= e)]
                    if not hit: res["1m"].append(None); break
                    q = slice(hit[0], min(hit[0] + MAXB * 5, len(mc)))
                    f1 = ((mh[q] - e) if d == 1 else (e - ml[q])) / rk
                    a1 = ((ml[q] - e) if d == 1 else (e - mh[q])) / rk
                    c1 = ((mc[q] - e) if d == 1 else (e - mc[q])) / rk
                    f1 = f1.copy(); f1[0] = max(c1[0], 0)     # inside the fill minute only its close counts
                    res["1m"].append(walk(f1, a1, 2))
                break
            if (c[j] - far) * d < 0: break

keep = [i for i in range(len(res["1m"])) if all(res[k][i] is not None for k in res)]
print(f"{len(keep)} trades, 5m retest + 9 EMA, first touch, 2R, last ~4 weeks")
for k, name in (("wick", "5m, whole entry candle counts (old backtests)"), ("path", "5m, candle path rule (new default)"),
                ("close", "5m, only entry candle close counts"), ("1m", "1m replay (closest to the truth)")):
    v = np.array([res[k][i] for i in keep])
    print(f"  {name:48s} win {np.mean(v > 0) * 100:5.1f}% | avg {v.mean():+.2f}R | total {v.sum():+7.1f}R")
