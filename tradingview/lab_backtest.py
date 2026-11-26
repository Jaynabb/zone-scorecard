# Backtest on the indicator's exact zones. Input: the CSV exports of jay_sd_lab.pine (one per symbol and style: the
# chart's own candles plus, per bar, the entry timeframe zone visit events with the zone, its score parts, purity,
# trend, EMA signal and opposing zone target; see make_lab.py). Every visit is a candidate for all three entry types:
#   TOUCH  limit at the near edge on the bar the visit starts
#   ZONE   at the close of the first candle that closes inside the zone on this visit
#   EXIT   at the close of the candle that closes back out
# "Proper" is the entry type the indicator calls for (purity 4 Touch, purity 2 with trend Zone, else Exit).
# Score = exported score parts + purity + rrr points from the target. Valid like the indicator: score >= 16 and EMA
# with the zone on Scalping, >= 14 elsewhere; never on a reaction (rr), retired or superseded zone.
# Each candidate is simulated against stop rules (Z<k>: k zone heights past the far edge, Z0 is the far edge itself,
# T<m>: m times the target distance) with target = the opposing zone's near edge, plus the 9 EMA exit
# (breakeven at +1R, out on a close back across the 9 EMA), and target bends with the far edge + 0.1 stop: P33/P50/P75
# a third, half, three quarters of the way to the opposing zone, R1/R2 fixed 1R and 2R. A candle that hits stop and
# target counts as the stop.
# Usage: python lab_backtest.py <dir with SYMBOL_Style.csv files>   -> writes lab_candidates.pkl in that dir
import sys, glob, os, numpy as np, pandas as pd
D = sys.argv[1]; MAXB = 500
STOPS = ["Z0", "Z0.1", "Z0.5", "Z1", "Z2", "Z3", "T1", "T2", "T3"]
GO = {"Scalping": (16, True), "Day": (14, False), "Swing": (14, False), "Longer": (14, False)}

def sim(h, l, c, je, e, d, stop, tgt, fill_open, e9=None):
    risk = (e - stop) * d
    if risk <= 0 or je >= len(c): return np.nan, -1
    end = min(je + MAXB, len(c))
    if e9 is None:
        rew = (tgt - e) * d
        if rew <= 0: return np.nan, -1
        fav = (h[je:end] - e) if d == 1 else (e - l[je:end]); adv = (l[je:end] - e) if d == 1 else (e - h[je:end])
        if fill_open is not None: fav = fav.copy(); fav[0] = fill_open
        s = np.nonzero(adv <= -risk)[0]; t = np.nonzero(fav >= rew)[0]
        s = s[0] if len(s) else 10**9; t = t[0] if len(t) else 10**9
        if s == t == 10**9: return (c[end - 1] - e) * d / risk, end - 1
        return (-1.0, je + s) if s <= t else (rew / risk, je + t)
    st, on = -1.0, False
    for i in range(je, end):
        fav = ((h[i] - e) if d == 1 else (e - l[i])) / risk
        if i == je and fill_open is not None: fav = fill_open / risk
        adv = ((l[i] - e) if d == 1 else (e - h[i])) / risk
        if adv <= st: return st, i
        if on and ((c[i] < e9[i]) if d == 1 else (c[i] > e9[i])): return (c[i] - e) * d / risk, i
        if fav >= 1: on = True; st = max(st, 0.0)
    return (c[end - 1] - e) * d / risk, end - 1

rows = []
for f in sorted(glob.glob(os.path.join(D, "*_*.csv"))):
    sym, style = os.path.basename(f)[:-4].split("_")
    x = pd.read_csv(f)
    o, h, l, c, t = (x[k].values for k in ("o", "h", "l", "c", "t"))
    e9 = pd.Series(c).ewm(span=9, adjust=False).mean().values
    half = t[len(t) // 2]
    go_min, need_ema = GO[style]
    for side in ("s", "d"):
        sup = side == "s"; d = -1 if sup else 1
        ev = x[side + "_ev"].values
        for j in np.nonzero(~np.isnan(ev))[0]:
            g = lambda k: x[f"{side}_{k}"].values[j]
            e_, top, btm = int(ev[j]), g("top"), g("btm"); hgt = top - btm
            if not hgt > 0: continue
            near = btm if sup else top; far = top if sup else btm
            pur, trend, ema, tgt, fl = int(g("pur")), int(g("trend")), int(g("ema")), g("tgt"), int(g("flags"))
            rrr = (tgt - near) * d / hgt if not np.isnan(tgt) else np.nan
            s_rrr = 0 if np.isnan(rrr) else 4 if rrr >= 5 else 2 if rrr >= 3 else 0
            total = int(g("score")) + pur + s_rrr
            proper = "TOUCH" if pur == 4 else "ZONE" if pur == 2 and trend == 4 else "EXIT"
            cands = []
            if e_ % 2 == 1:
                e = near if (o[j] - near) * d > 0 else o[j]
                fo = None if ((c[j] > o[j]) if d == 1 else (c[j] < o[j])) else max((c[j] - e) * d, 0.0)
                cands.append(("TOUCH", j, e, fo))
            if e_ % 4 >= 2 and not np.isnan(g("zc")): cands.append(("ZONE", j + 1, g("zc"), None))
            if e_ >= 4 and not np.isnan(g("x")): cands.append(("EXIT", j + 1, g("x"), None))
            for et, je, e, fo in cands:
                if np.isnan(tgt) or (tgt - e) * d <= 0 or je >= len(c): continue
                dist = (tgt - e) * d
                r = dict(sym=sym, style=style, t=t[min(je, len(t) - 1)], half=int(t[j] >= half), side=side, et=et, proper=et == proper,
                         vis=int(g("vis")), pur=pur, score=total, trend=trend, ema=ema, rr=fl & 1 > 0, retired=fl & 2 > 0,
                         sup_=fl & 4 > 0, gap_out=fl & 8 > 0, os=fl & 16 > 0, dist_h=dist / hgt, rrr=rrr,
                         valid=total >= go_min and (not need_ema or ema == 1) and not (fl & 7))
                for st in STOPS:
                    sp = far - d * float(st[1:]) * hgt if st[0] == "Z" else e - d * float(st[1:]) * dist
                    r[st], xi = sim(h, l, c, je, e, d, sp, tgt, fo); r["x_" + st] = t[xi] if xi >= 0 else np.nan
                # target bends with the indicator's stop (far edge + a tenth): part of the way to the opposing zone, or fixed R
                sp = far - d * 0.1 * hgt; risk = (e - sp) * d
                for nm, tp in (("P33", e + d * dist / 3), ("P50", e + d * dist / 2), ("P75", e + d * dist * 0.75), ("R1", e + d * risk), ("R2", e + d * 2 * risk)):
                    r[nm], xi = sim(h, l, c, je, e, d, sp, tp, fo); r["x_" + nm] = t[xi] if xi >= 0 else np.nan
                r["EMA9"], xi = sim(h, l, c, je, e, d, far, tgt, fo, e9); r["x_EMA9"] = t[xi] if xi >= 0 else np.nan
                rows.append(r)
df = pd.DataFrame(rows); df.to_pickle(os.path.join(D, "lab_candidates.pkl"))
print(len(df), "candidates"); print(df.groupby(["style", "et"]).size().unstack())
