# Counter-trend trades on the indicator's exact zones (jay_sd_lab.pine exports, see make_lab.py / lab_backtest.py).
# Proper rules: the entry type the indicator calls for (purity 4 Touch, purity 2 with trend Zone, else Exit), never on a
# reaction, retired or superseded zone, One And Done on Scalping (first visit only, Touch on its first candle), and the
# score without its trend points at least the GO line minus 4 (16 Scalping, 14 elsewhere), so a setup counts when it
# would be valid if the trend agreed. Trend = the score's trend part on arrival: 4 with the Mid trend, 2 consolidation
# or the control point in the way, 0 against (counter-trend). 9 EMA confluence: the standing 9 EMA signal (a full
# candle closes above the 9 EMA = buy, below = sell, the indicator's EMA rule with all three EMAs at 9) points the
# zone's way on the candle before entry.
# Stop a tenth of the zone past the far edge (the indicator's stop). Exits:
#   2R      fixed 2R
#   ZONE    the indicator's target (nearest opposing fresh entry timeframe zone, else Mid, else High), near edge
#   9EMA    the indicator's 9 EMA exit: breakeven at +1R, out on a close back across the 9 EMA, ZONE as the cap
# ROOM: only trades with 2R of room before the nearest opposing zone, fresh or used (used = an entry timeframe zone
# already visited, alive until a close through its far edge).
# A candle hitting stop and target counts as the stop. Usage: python lab_counter_trend.py <dir with SYMBOL_Style.csv>
import sys, glob, os, numpy as np, pandas as pd
D = sys.argv[1]; MAXB = 500
GO = {"Scalping": 16, "Day": 14, "Swing": 14, "Longer": 14}

def sim(h, l, c, je, e, d, stop, tgt, fo, e9=None):
    risk = (e - stop) * d
    if risk <= 0 or je >= len(c) or (tgt - e) * d <= 0: return np.nan
    st, on = -1.0, False
    for i in range(je, min(je + MAXB, len(c))):
        fav = ((h[i] - e) if d == 1 else (e - l[i]))
        if i == je and fo is not None: fav = fo
        adv = ((l[i] - e) if d == 1 else (e - h[i])) / risk
        if adv <= st: return st
        if fav >= (tgt - e) * d: return (tgt - e) * d / risk
        if e9 is not None:
            if on and ((c[i] < e9[i]) if d == 1 else (c[i] > e9[i])): return (c[i] - e) * d / risk
            if fav / risk >= 1: on = True; st = max(st, 0.0)
    return np.nan                      # still open at the time limit: left out

rows = []
for f in sorted(glob.glob(os.path.join(D, "*_*.csv"))):
    sym, style = os.path.basename(f)[:-4].split("_")
    x = pd.read_csv(f); o, h, l, c = (x[k].values for k in ("o", "h", "l", "c")); n = len(c)
    e9 = pd.Series(c).ewm(span=9, adjust=False).mean().values
    sig = np.zeros(n, int); s_ = 0
    for i in range(n):
        if l[i] > e9[i]: s_ = 1
        elif h[i] < e9[i]: s_ = -1
        sig[i] = s_
    # used zones per side: first visit bar and the bar a candle closes through the far edge
    used = {}
    for side in ("s", "d"):
        sup = side == "s"; ev = x[side + "_ev"].values; zs = {}
        for j in np.nonzero(~np.isnan(ev))[0]:
            key = (x[side + "_top"].values[j], x[side + "_btm"].values[j])
            if key not in zs: zs[key] = j
        lst = []
        for (top, btm), j0 in zs.items():
            far = top if sup else btm
            dead = np.nonzero((c[j0:] > far) if sup else (c[j0:] < far))[0]
            lst.append((btm if sup else top, j0, j0 + dead[0] if len(dead) else n))
        used[side] = lst
    for side in ("s", "d"):
        sup = side == "s"; d = -1 if sup else 1; ev = x[side + "_ev"].values
        for j in np.nonzero(~np.isnan(ev))[0]:
            g = lambda k: x[f"{side}_{k}"].values[j]
            e_, top, btm = int(ev[j]), g("top"), g("btm"); hgt = top - btm
            if not hgt > 0: continue
            near, far = (btm, top) if sup else (top, btm)
            pur, trend, tgt, fl, vis = int(g("pur")), int(g("trend")), g("tgt"), int(g("flags")), int(g("vis"))
            if fl & 7 or (style == "Scalping" and vis != 1): continue
            rrr = (tgt - near) * d / hgt if not np.isnan(tgt) else np.nan
            s_rrr = 0 if np.isnan(rrr) else 4 if rrr >= 5 else 2 if rrr >= 3 else 0
            total = int(g("score")) + pur + s_rrr
            if total - trend < GO[style] - 4: continue
            proper = "TOUCH" if pur == 4 else "ZONE" if pur == 2 and trend == 4 else "EXIT"
            if proper == "TOUCH" and e_ % 2 == 1:
                e = near if (o[j] - near) * d > 0 else o[j]; je = j
                fo = None if ((c[j] > o[j]) if d == 1 else (c[j] < o[j])) else max((c[j] - e) * d, 0.0)
            elif proper == "ZONE" and e_ % 4 >= 2 and not np.isnan(g("zc")): e, je, fo = g("zc"), j + 1, None
            elif proper == "EXIT" and e_ >= 4 and not np.isnan(g("x")): e, je, fo = g("x"), j + 1, None
            else: continue
            if je >= n: continue
            stop = far - d * 0.1 * hgt; risk = (e - stop) * d
            if risk <= 0: continue
            opp = [ne for (ne, j0, jd) in used["d" if sup else "s"] if j0 < je <= jd and (ne - e) * d > 0]
            if not np.isnan(tgt) and (tgt - e) * d > 0: opp.append(tgt)
            room = (min(opp) - e) / risk if d == 1 and opp else (e - max(opp)) / risk if opp else np.inf
            rows.append(dict(style=style, sym=sym, trend=trend, ema9=sig[je - 1] == d, room2=room >= 2,
                             R2=sim(h, l, c, je, e, d, stop, e + d * 2 * risk, fo),
                             ZONE=sim(h, l, c, je, e, d, stop, tgt, fo) if not np.isnan(tgt) else np.nan,
                             EMA9=sim(h, l, c, je, e, d, stop, tgt if not np.isnan(tgt) else e + d * 50 * risk, fo, e9)))
df = pd.DataFrame(rows); df.to_pickle(os.path.join(D, "lab_counter_trend.pkl"))

def cell(v):
    v = v.dropna()
    return f"{len(v):4d} | {np.mean(v > 0) * 100:3.0f}% | {v.mean():+.2f}R" if len(v) >= 15 else f"{len(v):4d} |   -  |   -   "
TR = {4: "with trend", 2: "neutral", 0: "COUNTER"}
for style in ("Scalping", "Day", "Swing", "Longer"):
    s = df[df["style"] == style]
    if not len(s): continue
    print(f"\n=== {style} ({', '.join(sorted(s.sym.unique()))}) | trades | win | avg ===")
    print(f"  {'':32s}{'fixed 2R':>22s}{'to the zone target':>24s}{'9 EMA exit':>22s}")
    for tr in (4, 2, 0):
        for nm, m in (("all", s.trend == tr), ("9 EMA agrees", (s.trend == tr) & s.ema9), ("9 EMA against", (s.trend == tr) & ~s.ema9),
                      ("9 EMA agrees + 2R room", (s.trend == tr) & s.ema9 & s.room2)):
            q = s[m]; print(f"  {TR[tr] + ', ' + nm:32s}  {cell(q.R2)}    {cell(q.ZONE)}    {cell(q.EMA9)}")
