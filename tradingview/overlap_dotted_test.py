# Do used (dotted) zones still hold, and do zones that overlap a higher timeframe zone do better?
# Zones come from the structural base reader (zone_struct.py, the indicator's v217 rules) on the TradingView candles in
# the lab exports. Mid timeframe candles are built from the entry timeframe ones (5m->30m, 1h->4h, 4h->1d, 1d->1w).
# Every visit of every entry timeframe zone is measured, until a close through its far edge:
#   held     price moved away 2 zone heights before closing through the far edge
#   2R / 3R  limit at the near edge, stop a tenth of the zone past the far edge, target 2R / 3R (a candle that hits both
#            counts as the stop; the touch candle keeps its favourable extreme only when it closed in our favour)
# Split by visit number (1 = fresh, 2+ = what the chart draws dotted) and by overlap with an active, unbroken Mid
# timeframe zone of the same side (known before the touch), in the first and second half of each history.
# Usage: python overlap_dotted_test.py <lab data dir>
import sys, os, glob, numpy as np, pandas as pd
D = sys.argv[1]; HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "zone_struct.py")).read().split("fx = [r for r")[0]
g = {"__file__": os.path.join(HERE, "zone_struct.py")}; exec(src.replace("D = sys.argv[1]", "D = ''"), g); zones = g["zones"]
STY = {"scalp": ("Scalping", "30min"), "day": ("Day", "4h"), "swing": ("Swing", "1D"), "longer": ("Longer", "W")}
MAXB = 300

def load(f):
    x = pd.read_csv(f)[["t", "o", "h", "l", "c"]]
    x["dt"] = pd.to_datetime(x.t, unit="s", utc=True).dt.tz_convert("America/New_York")
    return x.reset_index(drop=True)

def resample(x, rule):
    y = x.set_index("dt")[["o", "h", "l", "c"]].resample(rule).agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna().reset_index()
    return y

rows = []
for sub, (style, mid_rule) in STY.items():
    for f in sorted(glob.glob(os.path.join(D, sub, "*.csv"))):
        sym = os.path.basename(f).split("_")[0]
        L = load(f)
        if len(L) < 300: continue
        M = resample(L, mid_rule); mstep = M.dt.diff().median()
        lz = zones(L); mz = zones(M)
        o, h, l, c = (L[k].values for k in "ohlc"); t = L.dt; n = len(c); half = t.iloc[n // 2]
        tpos = {v: i for i, v in enumerate(t)}
        mo, mh, ml, mc = (M[k].values for k in "ohlc")
        # Mid zones: known from the close of the move out candle, alive until a Mid close through the far edge
        mlist = []
        for z in mz:
            k = M.index[M.dt == z["imp"]][0]
            known = M.dt[k] + mstep
            far = z["top"] if z["sup"] else z["btm"]
            br = np.nonzero((mc[k + 1:] > far) if z["sup"] else (mc[k + 1:] < far))[0]
            dead = M.dt[k + 1 + br[0]] + mstep if len(br) else pd.Timestamp("2200-01-01", tz="America/New_York")
            mlist.append((z["sup"], z["btm"], z["top"], known, dead))
        for z in lz:
            sup = z["sup"]; d = -1 if sup else 1; top, btm = z["top"], z["btm"]; hgt = top - btm
            if hgt <= 0: continue
            near = btm if sup else top; far = top if sup else btm; stop = far - d * 0.1 * hgt
            j0 = tpos[z["imp"]] + 1; inside = False; vis = 0
            for j in range(j0, min(j0 + 2000, n)):
                if (c[j] > far) if sup else (c[j] < far): break
                touch = (h[j] >= near) if sup else (l[j] <= near)
                if touch and not inside:
                    vis += 1
                    ov = any(ms == sup and mk <= t[j] < md and mt >= btm and mb <= top for ms, mb, mt, mk, md in mlist)
                    e = near if (o[j] - near) * d > 0 else o[j]; risk = (e - stop) * d
                    res = {}
                    if risk > 0:
                        end = min(j + MAXB, n)
                        fav = (h[j:end] - e) if d == 1 else (e - l[j:end]); adv = (l[j:end] - e) if d == 1 else (e - h[j:end])
                        if not ((c[j] > o[j]) if d == 1 else (c[j] < o[j])): fav = fav.copy(); fav[0] = max((c[j] - e) * d, 0)
                        cl = (c[j:end] - far) * d < 0
                        for R in (2, 3):
                            s_ = np.nonzero(adv <= -risk)[0]; w_ = np.nonzero(fav >= R * risk)[0]
                            s_ = s_[0] if len(s_) else 10**9; w_ = w_[0] if len(w_) else 10**9
                            res[f"r{R}"] = np.nan if s_ == w_ == 10**9 else (-1.0 if s_ <= w_ else float(R))
                        away = np.nonzero(fav >= 2 * hgt)[0]; brk = np.nonzero(cl)[0]
                        a_ = away[0] if len(away) else 10**9; b_ = brk[0] if len(brk) else 10**9
                        res["held"] = np.nan if a_ == b_ == 10**9 else float(a_ < b_)
                    rows.append(dict(style=style, sym=sym, vis=vis, ov=ov, half=int(t[j] >= half), **res))
                inside = touch and not ((c[j] < near) if sup else (c[j] > near))
df = pd.DataFrame(rows)
df.to_pickle(os.path.join(D, "overlap_dotted.pkl"))

def cell(x, col):
    r = x[col].dropna()
    if len(r) < 20: return f"{len(r):5d}   -    "
    a = x[x.half == 0][col].dropna(); b = x[x.half == 1][col].dropna()
    if col == "held": return f"{len(r):5d} {r.mean()*100:4.0f}% ({a.mean()*100:3.0f}/{b.mean()*100:3.0f})"
    return f"{len(r):5d} {r.mean():+.2f}R ({a.mean():+.2f}/{b.mean():+.2f})"

for style in ["Scalping", "Day", "Swing", "Longer"]:
    s = df[df["style"] == style]
    print(f"\n#### {style}   trades | held = moved 2 zone heights away before closing through | 2R and 3R avg result (older half / newer half)")
    for nm, m in [("fresh, 1st touch", s.vis == 1), ("dotted, 2nd touch", s.vis == 2), ("dotted, 3rd+ touch", s.vis >= 3),
                  ("1st touch, overlaps Mid zone", (s.vis == 1) & s.ov), ("1st touch, no Mid overlap", (s.vis == 1) & ~s.ov),
                  ("2nd+ touch, overlaps Mid zone", (s.vis >= 2) & s.ov), ("2nd+ touch, no Mid overlap", (s.vis >= 2) & ~s.ov)]:
        x = s[m]
        print(f"  {nm:30s} held {cell(x,'held')} | 2R {cell(x,'r2')} | 3R {cell(x,'r3')}")
