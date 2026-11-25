# All three entry types, scored, on the watchlist, per trade style (entry timeframe zones only).
# Every visit of a zone is followed (a visit starts on a touch and ends when a candle closes back out past the near
# edge; a close through the far edge ends the zone). The entry type is the indicator's:
#   purity 4 (first visit)                               -> TOUCH: limit at the near edge on the touch
#   purity 2 (second visit, first under half deep), with the Mid trend -> ZONE: at the close of the visit's first candle
#                                                                         that closes inside the zone
#   anything else (purity 0, or counter trend)            -> EXIT: at the close of the candle that closes back out
# Score at each visit with that visit's purity (see scored_entry_backtest.py for the checks); valid at >= 14, or >= 16
# with the 9 EMA agreeing on Scalping, where One And Done also leaves only the first visit. Stop a tenth of the zone past
# the far edge; a Zone or Exit entry closer to the stop than a third of the zone height is skipped (tiny R).
# Versions: FIXED 3:1, and ZONE TO ZONE with the Mid trend only (target the opposing zone's near edge).
# One trade at a time per symbol, $1000, 2% of equity per trade, compounding.
# Usage: python entry_types_scored_backtest.py <datadir>
import sys, numpy as np, pandas as pd
DATA = sys.argv[1]
base = open(__file__.replace("entry_types_scored_backtest.py", "scored_entry_backtest.py")).read()
g = {"__name__": "lib"}; sys.argv = [sys.argv[0], DATA]
exec(base.split("for style, lo, mid, hi, go_min, need_ema in STYLES:")[0], g)
load, zones, broken_at, score, account, one_at_a_time = (g[x] for x in ("load", "zones", "broken_at", "score", "account", "one_at_a_time"))
mid_trend, high_range, SYMS, STYLES, MAXB = g["mid_trend"], g["high_range"], g["SYMS"], g["STYLES"], g["MAXB"]

def sim(o, h, l, c, j, e, stop, d, target_px, fill):
    risk = (e - stop) * d
    if risk <= 0: return None
    tgt_r = 3.0 if target_px is None else (target_px - e) * d / risk
    if tgt_r <= 0: return None
    for i in range(j, min(j + MAXB, len(c))):
        fav = ((h[i] - e) if d == 1 else (e - l[i])) / risk
        adv = ((l[i] - e) if d == 1 else (e - h[i])) / risk
        if fill and i == j and not ((c[i] > o[i]) if d == 1 else (c[i] < o[i])): fav = max((c[i] - e) * d / risk, 0.0)
        if adv <= -1: return (j, i, -1.0)
        if fav >= tgt_r: return (j, i, tgt_r)
    return None

def visits(z, o, h, l, c, start):
    # yields (visit_no, purity, j_touch, j_close_inside or None, j_close_out or None, dead_after)
    sup = z["sup"]; d = -1 if sup else 1
    near = z["btm"] if sup else z["top"]; far = z["top"] if sup else z["btm"]; hgt = z["top"] - z["btm"]
    inside, n, depth, out = False, 0, 0.0, []
    cur = None
    for j in range(start, min(start + MAXB * 4, len(c))):
        touching = (h[j] >= near) if sup else (l[j] <= near)
        closed_out = (c[j] < near) if sup else (c[j] > near)
        broken = (c[j] > far) if sup else (c[j] < far)
        if touching and not inside:
            n += 1
            before = n - 1
            pur = 4 if before == 0 else (2 if before == 1 and depth < 0.5 else 0)
            cur = dict(n=n, pur=pur, j=j, zc=None, x=None)
            out.append(cur)
        if touching:
            pen = ((h[j] - near) if sup else (near - l[j])) / hgt
            depth = max(depth, min(max(pen, 0.0), 1.0))
            if cur is not None and cur["zc"] is None and not closed_out and not broken: cur["zc"] = j
        if (inside or touching) and closed_out and cur is not None and cur["x"] is None: cur["x"] = j
        if broken: break
        inside = touching and not closed_out
    return out

ORDER = ("TOUCH", "ZONE", "EXIT")
def line(name, tr):
    if not tr: return f"    {name:6s}   no trades"
    r = np.array([x[2] for x in tr]); eq, mdd = account([x[:3] for x in tr])
    return (f"    {name:6s} {len(r):5d} trades | win {np.mean(r > 0) * 100:5.1f}% | avg win {r[r > 0].mean() if (r > 0).any() else 0:4.1f}R"
            f" | avg {r.mean():+.2f}R | total {r.sum():+7.1f}R | $1000 -> ${eq:,.0f} | max dd {mdd * 100:4.1f}%")

for style, lo, mid, hi, go_min, need_ema in STYLES:
    one_done = lo == "5m"
    res = {v: [] for v in ("3R", "Z2Z")}; span = []
    for s in SYMS:
        L, M, H = load(s, lo), load(s, mid), load(s, hi)
        if len(L) < 300 or len(M) < 60 or len(H) < 25: continue
        o, h, l, c = [L[x].values for x in ("Open", "High", "Low", "Close")]; t = L.index
        span.append(f"{s} {t[0]:%Y-%m}")
        trend = mid_trend(t, M); rT, rB = high_range(t, H)
        e9 = pd.Series(c).ewm(span=9, adjust=False).mean().values
        sig = np.where(c > e9, 1, np.where(c < e9, -1, 0))
        yl = pd.Series(np.abs(c - o)).rolling(20).median().values
        lz = zones(o, h, l, c, yl)
        for z in lz: z["brk"] = broken_at(z, c, z["k"] + 1)
        cand = {v: [] for v in ("3R", "Z2Z")}
        for z in lz:
            d = -1 if z["sup"] else 1; hgt = z["top"] - z["btm"]
            near = z["btm"] if z["sup"] else z["top"]; far = z["top"] if z["sup"] else z["btm"]
            stop = far - d * 0.1 * hgt
            for v in visits(z, o, h, l, c, z["k"] + 1):
                if one_done and v["n"] > 1: break
                j = v["j"]
                if j < 1: continue
                rng = (None, None) if np.isnan(rT[j - 1]) else (rT[j - 1], rB[j - 1])
                total4, s_tr, opp = score(z, lz, None, j, j, (h, l, c), trend[j - 1], rng)
                total = total4 - 4 + v["pur"]
                et = "TOUCH" if v["pur"] == 4 else ("ZONE" if v["pur"] == 2 and s_tr == 4 else "EXIT")
                if et == "TOUCH":
                    je = j; e = near if (o[j] - near) * d > 0 else o[j]; fill = True
                elif et == "ZONE":
                    if v["zc"] is None or v["zc"] + 1 >= len(c): continue
                    je = v["zc"] + 1; e = c[v["zc"]]; fill = False
                else:
                    if v["x"] is None or v["x"] + 1 >= len(c): continue
                    je = v["x"] + 1; e = c[v["x"]]; fill = False
                if et != "TOUCH" and (e - stop) * d < hgt / 3: continue
                if total < go_min or (need_ema and sig[je - 1] != d): continue
                r = sim(o, h, l, c, je, e, stop, d, None, fill)
                if r: cand["3R"].append((t[r[0]], t[r[1]], r[2], et))
                if s_tr == 4 and opp is not None:
                    r = sim(o, h, l, c, je, e, stop, d, opp, fill)
                    if r: cand["Z2Z"].append((t[r[0]], t[r[1]], r[2], et))
        for v in cand: res[v].extend(one_at_a_time(cand[v]))
    print(f"\n#### {style}: entry {lo}, Mid {mid}, High {hi}, valid score >= {go_min}{' + 9 EMA, one and done' if need_ema else ''}   (data from: {', '.join(span)})")
    for v, title in (("3R", "FIXED 3:1"), ("Z2Z", "ZONE TO ZONE, with trend only")):
        print(f"  {title}"); print(line("ALL", res[v]))
        for et in ORDER: print(line(et, [x for x in res[v] if x[3] == et]))
