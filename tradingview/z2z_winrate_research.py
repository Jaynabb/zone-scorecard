# Zone to zone win rate research: which entry type, filters and stop rule get the win rate to 75% while still making
# money. Every visit of every entry timeframe zone is a candidate (entry type as in entry_types_scored_backtest.py);
# target is always the near edge of the nearest unbroken opposing zone (entry timeframe, or entry + Mid timeframe).
# Each candidate is simulated against several stop rules:
#   Z<k>  : a k-th of the zone height past the far edge (Z0.1 is the indicator's stop)
#   T<m>  : stop m times the target distance from the entry (R per win = 1/m)
#   MID   : past the far edge of the Mid timeframe zone of the same side that holds the entry zone (nested only)
# A candle that hits stop and target counts as the stop. A trade that hits neither in 500 candles is closed at the close.
# Results are printed for the first and second half of each symbol's history separately, so a rule only counts if it
# holds in both.
# Usage: python z2z_winrate_research.py <datadir> [style]
import sys, itertools, numpy as np, pandas as pd
DATA = sys.argv[1]; ONLY = sys.argv[2] if len(sys.argv) > 2 else None
base = open(__file__.replace("z2z_winrate_research.py", "scored_entry_backtest.py")).read()
g = {"__name__": "lib"}; sys.argv = [sys.argv[0], DATA]
exec(base.split("for style, lo, mid, hi, go_min, need_ema in STYLES:")[0], g)
load, zones, broken_at, score = (g[x] for x in ("load", "zones", "broken_at", "score"))
mid_trend, high_range, SYMS, STYLES, MAXB = g["mid_trend"], g["high_range"], g["SYMS"], g["STYLES"], g["MAXB"]
ets = open(__file__.replace("z2z_winrate_research.py", "entry_types_scored_backtest.py")).read()
exec("def visits" + ets.split("\ndef visits")[1].split("\nORDER")[0], g); visits = g["visits"]
STOPS = ["Z0.1", "Z0.5", "Z1", "Z2", "Z3", "T0.5", "T1", "T2", "T3", "MID"]

def outcome(h, l, c, je, e, d, stop, tgt, fill_open):
    # returns R; stop and target as prices
    risk = (e - stop) * d; rew = (tgt - e) * d
    if risk <= 0 or rew <= 0: return np.nan
    end = min(je + MAXB, len(c))
    hh, ll = h[je:end], l[je:end]
    fav = (hh - e) * d if d == 1 else (e - ll)
    adv = (ll - e) * d if d == 1 else (e - hh)
    if fill_open is not None: fav = fav.copy(); fav[0] = fill_open
    hit_s = np.nonzero(adv <= -risk)[0]; hit_t = np.nonzero(fav >= rew)[0]
    s = hit_s[0] if len(hit_s) else 10**9; t = hit_t[0] if len(hit_t) else 10**9
    if s == 10**9 and t == 10**9: return (c[end - 1] - e) * d / risk
    return -1.0 if s <= t else rew / risk

rows = []
for style, lo, mid, hi, go_min, need_ema in STYLES:
    if ONLY and style != ONLY: continue
    for s in SYMS:
        L, M, H = load(s, lo), load(s, mid), load(s, hi)
        if len(L) < 300 or len(M) < 60 or len(H) < 25: continue
        o, h, l, c = [L[x].values for x in ("Open", "High", "Low", "Close")]; t = L.index
        half = t[len(t) // 2]
        trend = mid_trend(t, M); rT, rB = high_range(t, H)
        e9 = pd.Series(c).ewm(span=9, adjust=False).mean().values
        sig = np.where(c > e9, 1, np.where(c < e9, -1, 0))
        yl = pd.Series(np.abs(c - o)).rolling(20).median().values
        lz = zones(o, h, l, c, yl)
        for z in lz: z["brk"] = broken_at(z, c, z["k"] + 1)
        mo, mh, ml, mc = [M[x].values for x in ("Open", "High", "Low", "Close")]
        mz = zones(mo, mh, ml, mc, pd.Series(np.abs(mc - mo)).rolling(20).median().values)
        mstep = M.index.to_series().diff().median()
        for z in mz:
            z["brk"] = broken_at(z, mc, z["k"] + 1)
            z["kt"] = t.searchsorted(M.index[z["k"]] + mstep)                       # entry tf bar it is known from
            bi = np.nonzero((c[z["kt"]:] > z["top"]) if z["sup"] else (c[z["kt"]:] < z["btm"]))[0]
            z["brk_t"] = z["kt"] + (bi[0] if len(bi) else len(c))                     # approx: entry tf close through
        for z in lz:
            d = -1 if z["sup"] else 1; hgt = z["top"] - z["btm"]
            near = z["btm"] if z["sup"] else z["top"]; far = z["top"] if z["sup"] else z["btm"]
            for v in visits(z, o, h, l, c, z["k"] + 1):
                j = v["j"]
                if j < 1: continue
                rng = (None, None) if np.isnan(rT[j - 1]) else (rT[j - 1], rB[j - 1])
                total4, s_tr, opp = score(z, lz, None, j, j, (h, l, c), trend[j - 1], rng)
                total = total4 - 4 + v["pur"]
                # opposing Mid zones too: nearest of both
                opp2 = opp
                for mzz in mz:
                    if mzz["sup"] == z["sup"] or mzz["kt"] >= j or mzz["brk_t"] <= j: continue
                    on = mzz["top"] if z["sup"] else mzz["btm"]
                    if (on - near) * d > 0 and (opp2 is None or (on - near) * d < (opp2 - near) * d): opp2 = on
                # the Mid zone of the same side holding this zone, known and unbroken at the touch
                hold = [m for m in mz if m["sup"] == z["sup"] and m["kt"] <= j and m["brk_t"] > j
                        and m["btm"] <= z["btm"] + 0.5 * hgt and m["top"] >= z["top"] - 0.5 * hgt]
                mid_far = None
                if hold: mid_far = max(m["top"] for m in hold) if z["sup"] else min(m["btm"] for m in hold)
                for et in ("TOUCH", "ZONE", "EXIT"):
                    if et == "TOUCH":
                        je = j; e = near if (o[j] - near) * d > 0 else o[j]
                    elif et == "ZONE":
                        if v["zc"] is None or v["zc"] + 1 >= len(c): continue
                        je = v["zc"] + 1; e = c[v["zc"]]
                    else:
                        if v["x"] is None or v["x"] + 1 >= len(c): continue
                        je = v["x"] + 1; e = c[v["x"]]
                    fill_open = None
                    if et == "TOUCH" and not ((c[j] > o[j]) if d == 1 else (c[j] < o[j])): fill_open = max((c[j] - e) * d, 0.0)
                    for tk, tg in (("T", opp), ("T2", opp2)):
                        if tg is None or (tg - e) * d <= 0: continue
                        dist = (tg - e) * d
                        res = {}
                        for st in STOPS:
                            if st[0] == "Z": sp = far - d * float(st[1:]) * hgt
                            elif st[0] == "T": sp = e - d * float(st[1:]) * dist
                            else:
                                if mid_far is None: res[st] = np.nan; continue
                                sp = mid_far - d * 0.1 * hgt
                            res[st] = outcome(h, l, c, je, e, d, sp, tg, fill_open)
                        rows.append(dict(style=style, sym=s, half=int(t[j] >= half), et=et, tgt=tk, pur=v["pur"], visit=v["n"],
                                         score=total, trend=s_tr, ema=int(sig[je - 1] == d), nested=int(mid_far is not None),
                                         dist_h=dist / hgt, t0=t[je], **res))
df = pd.DataFrame(rows)
df.to_pickle(__file__.replace(".py", f"_{ONLY or 'all'}.pkl"))
print(len(df), "candidates")
