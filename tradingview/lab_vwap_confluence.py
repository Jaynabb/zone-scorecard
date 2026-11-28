# VWAP as confluence on the indicator's exact zones (jay_sd_lab.pine exports, same proper rules as lab_counter_trend.py).
# The lab exports have no volume, so volume comes from Yahoo (5m for Scalping, 1h for Day; NQ=F, YM=F for US30, CL=F
# for USOIL, NVDA, BTC-USD, ETH-USD) matched by bar time, and the VWAP is built on the export's own prices with those
# weights. Session VWAP like TradingView: crypto resets 00:00 UTC, NVDA each New York day, futures/CFDs at 18:00 ET.
# 1 and 2 standard deviation bands. Everything is read on the candle before entry, so nothing looks ahead.
# Confluence measured per trade:
#   z       entry distance from VWAP in band units, signed with the trade: negative = buying under VWAP / selling over
#           it (discount), positive = with VWAP (premium side)
#   band    a band line (VWAP, 1st or 2nd band) runs through the zone
# Exits: 2R, ZONE (the indicator's target), 9EMA (the indicator's 9 EMA exit), BAND2 (the 2nd band on the profit side
# at entry, as the target when there is no zone target, VWAP when it is closer in a discount entry is not used).
# GO = the trade the indicator calls (total at the GO line, or the v248 Scalping counter-trend touch at the line - 4).
# Usage: python lab_vwap_confluence.py <lab dir with SYMBOL_Style.csv> <dir with SYMBOL_5m.csv / SYMBOL_1h.csv>
import sys, glob, os, numpy as np, pandas as pd
D, V = sys.argv[1], sys.argv[2]; MAXB = 500
GO = {"Scalping": 16, "Day": 14}
VTF = {"Scalping": "5m", "Day": "1h"}

def sim(h, l, c, je, e, d, stop, tgt, fo, e9=None):
    risk = (e - stop) * d
    if risk <= 0 or je >= len(c) or np.isnan(tgt) or (tgt - e) * d <= 0: return np.nan
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
    return np.nan

def vwap_bands(x, sym, style):
    v = pd.read_csv(os.path.join(V, f"{sym}_{VTF[style]}.csv"), index_col=0)
    v.index = (pd.to_datetime(v.index, utc=True) - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)
    v = v[~v.index.duplicated(keep="last")]
    vol = x.t.map(v.Volume).fillna(0).values.astype(float)
    ts = pd.to_datetime(x.t, unit="s", utc=True)
    if sym in ("BTCUSD", "ETHUSD"): sess = ts.dt.date
    elif sym == "NVDA": sess = ts.dt.tz_convert("America/New_York").dt.date
    else: sess = (ts.dt.tz_convert("America/New_York") + pd.Timedelta(hours=6)).dt.date
    tp = (x.h + x.l + x.c) / 3
    g = pd.Series(sess.values)
    cv = pd.Series(vol).groupby(g).cumsum()
    w = (tp * vol).groupby(g).cumsum() / cv.replace(0, np.nan)
    sd = np.sqrt(((tp * tp * vol).groupby(g).cumsum() / cv.replace(0, np.nan) - w ** 2).clip(lower=0))
    covered = (x.t >= v.index.min()) & (x.t <= v.index.max())
    return w.where(covered).values, sd.where(covered & (sd > 0)).values

rows = []
for style in GO:
    for f in sorted(glob.glob(os.path.join(D, f"*_{style}.csv"))):
        sym = os.path.basename(f).split("_")[0]
        if not os.path.exists(os.path.join(V, f"{sym}_{VTF[style]}.csv")): continue
        x = pd.read_csv(f); o, h, l, c = (x[k].values for k in ("o", "h", "l", "c")); n = len(c)
        vw, vsd = vwap_bands(x, sym, style)
        e9 = pd.Series(c).ewm(span=9, adjust=False).mean().values
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
                if je >= n or je < 1: continue
                W, S = vw[je - 1], vsd[je - 1]
                if np.isnan(W) or np.isnan(S): continue
                stop = far - d * 0.1 * hgt; risk = (e - stop) * d
                if risk <= 0: continue
                go = total >= GO[style] or (style == "Scalping" and proper == "TOUCH" and trend == 0)
                band = any(btm <= W + k * S <= top for k in (-2, -1, 0, 1, 2))
                rows.append(dict(style=style, sym=sym, go=go, trend=trend, z=(e - W) / S * d, band=band,
                                 R2=sim(h, l, c, je, e, d, stop, e + d * 2 * risk, fo),
                                 ZONE=sim(h, l, c, je, e, d, stop, tgt, fo),
                                 EMA9=sim(h, l, c, je, e, d, stop, tgt if not np.isnan(tgt) else e + d * 50 * risk, fo, e9),
                                 BAND2=sim(h, l, c, je, e, d, stop, tgt if not np.isnan(tgt) else W + d * 2 * S, fo),
                                 has_tgt=not np.isnan(tgt)))
df = pd.DataFrame(rows); df.to_pickle(os.path.join(D, "lab_vwap_confluence.pkl"))

def cell(v):
    v = v.dropna()
    return f"{len(v):4d} | {np.mean(v > 0) * 100:3.0f}% | {v.mean():+.2f}R" if len(v) >= 15 else f"{len(v):4d} |   -  |   -   "
Z = [("far discount (z < -2)", lambda z: z < -2), ("discount (-2 to -1)", lambda z: (z >= -2) & (z < -1)),
     ("just under (-1 to 0)", lambda z: (z >= -1) & (z < 0)), ("just over (0 to 1)", lambda z: (z >= 0) & (z < 1)),
     ("premium (1 to 2)", lambda z: (z >= 1) & (z < 2)), ("far premium (z >= 2)", lambda z: z >= 2)]
for style in GO:
    for who, sel in (("GO trades", True), ("all candidates", None)):
        s = df[(df["style"] == style) & ((df.go == sel) if sel is not None else True)]
        if not len(s): continue
        print(f"\n=== {style} {who} ({', '.join(sorted(s.sym.unique()))}) | trades | win | avg ===")
        print(f"  {'':30s}{'fixed 2R':>22s}{'zone target':>22s}{'9 EMA exit':>22s}")
        for nm, m in [("all", s.z == s.z)] + [(a, fn(s.z)) for a, fn in Z] + \
                     [("band line inside the zone", s.band), ("no band line in the zone", ~s.band)]:
            q = s[m]; print(f"  {nm:30s}  {cell(q.R2)}  {cell(q.ZONE)}  {cell(q.EMA9)}")
        q = s[~s.has_tgt]
        print(f"  no zone target: 2nd band as the target  {cell(q.BAND2)}   (2R on the same trades {cell(q.R2)})")
