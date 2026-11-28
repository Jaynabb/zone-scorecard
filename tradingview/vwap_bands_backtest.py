"""VWAP band strategy from the YouTube video UxTw6KHjp1U, tested on NQ 1m data.

Session VWAP (anchored 18:00 ET like TradingView futures) with 1 and 2 standard
deviation bands. Trades only in the New York session (9:30 to 16:00 ET), signals
on 5m closes, fills on the next 5m open, 1 point round trip cost.

  trend:    close crosses VWAP -> enter that way, target the 2nd band,
            stop when a 5m candle closes back across VWAP
  reversal: price was outside the 1st band, then a 5m candle closes back inside
            -> enter toward VWAP, target VWAP, stop at the extreme since leaving the band
"""
import sys
import numpy as np
import pandas as pd

path = sys.argv[1]
df = pd.read_csv(path)
df.index = pd.to_datetime(df["Datetime"], utc=True).dt.tz_convert("America/New_York")
df = df[["Open", "High", "Low", "Close", "Volume"]]

# session id: a new session starts at 18:00 ET
sess = (df.index - pd.Timedelta(hours=18)).date
tp = (df.High + df.Low + df.Close) / 3
v = df.Volume.astype(float)
g = pd.Series(sess, index=df.index)
cv = v.groupby(g).cumsum()
vwap = (tp * v).groupby(g).cumsum() / cv
var = (tp * tp * v).groupby(g).cumsum() / cv - vwap ** 2
sd = np.sqrt(var.clip(lower=0))
df["vwap"], df["sd"] = vwap, sd

b = df.resample("5min").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last",
                             "vwap": "last", "sd": "last"}).dropna()
t = b.index.time
ny = (t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("16:00").time())
O, H, L, C, W, S = (b[k].values for k in ["Open", "High", "Low", "Close", "vwap", "sd"])
COST = 1.0


def run_trend():
    out = []
    pos = 0
    for i in range(1, len(b) - 1):
        if pos:
            tgt = W[i] + 2 * S[i] * pos
            hit = H[i] >= tgt if pos > 0 else L[i] <= tgt
            if hit:
                out.append((tgt - ent) * pos - COST); pos = 0; continue
            if (C[i] - W[i]) * pos < 0 or not ny[i]:
                out.append((O[i + 1] - ent) * pos - COST); pos = 0; continue
        if not pos and ny[i] and ny[i + 1]:
            if C[i - 1] <= W[i - 1] and C[i] > W[i]:
                pos, ent = 1, O[i + 1]
            elif C[i - 1] >= W[i - 1] and C[i] < W[i]:
                pos, ent = -1, O[i + 1]
    return np.array(out)


def run_reversal():
    out, risk = [], []
    pos = 0
    up_ext = dn_ext = None
    for i in range(1, len(b) - 1):
        u1, d1 = W[i] + S[i], W[i] - S[i]
        if pos:
            if (pos < 0 and H[i] >= stop) or (pos > 0 and L[i] <= stop):
                out.append((stop - ent) * pos - COST); pos = 0
            elif (pos < 0 and L[i] <= W[i]) or (pos > 0 and H[i] >= W[i]):
                out.append((W[i] - ent) * pos - COST); pos = 0
            elif not ny[i]:
                out.append((O[i + 1] - ent) * pos - COST); pos = 0
            if pos:
                continue
        up_ext = max(up_ext, H[i]) if up_ext is not None else (H[i] if C[i] > u1 else None)
        dn_ext = min(dn_ext, L[i]) if dn_ext is not None else (L[i] if C[i] < d1 else None)
        if up_ext is not None and C[i] < u1:
            if ny[i] and ny[i + 1] and C[i] > W[i]:
                pos, ent, stop = -1, O[i + 1], up_ext
                risk.append(stop - ent)
            up_ext = None
        elif dn_ext is not None and C[i] > d1:
            if ny[i] and ny[i + 1] and C[i] < W[i]:
                pos, ent, stop = 1, O[i + 1], dn_ext
                risk.append(ent - stop)
            dn_ext = None
    return np.array(out), np.array(risk[:len(out)])


def show(name, p, risk=None):
    w = p[p > 0]; l = p[p <= 0]
    pf = w.sum() / -l.sum() if len(l) and l.sum() else float("inf")
    line = (f"{name:9s} trades {len(p):4d}  win {100*len(w)/max(len(p),1):4.0f}%  "
            f"avg {p.mean():+6.1f} pts  total {p.sum():+8.1f} pts  PF {pf:4.2f}  "
            f"avg win {w.mean() if len(w) else 0:6.1f}  avg loss {l.mean() if len(l) else 0:6.1f}")
    if risk is not None and len(risk):
        line += f"  avg R {np.mean(p / np.maximum(risk, 1)):+.2f}"
    print(line)


print(f"{path.split('/')[-1]}  {b.index[0].date()} to {b.index[-1].date()}  NY session 5m bars: {ny.sum()}")
show("trend", run_trend())
p, r = run_reversal()
show("reversal", p, r)
