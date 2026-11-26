# Does a Low timeframe trend against the Mid trend hurt a Touch entry? (Jay, US30 5m demand under a 5m downtrend
# while the 30m is up, trend score 4.)
# Both trends are the indicator's trend_pack ported: alternating zig zag swings (pivot length 10, 2 confirmation bars),
# break of structure on the close, control point = last lower high (down) / higher low (up), consolidation scored flat.
# Trend score as the indicator: Mid with the zone and the near edge not past the control point 4, flat or consolidating
# 2, against 0. Touch GO = trend score 4 and the 9 EMA agreeing (indicator v233), fresh zones, first touch, limit at the
# near edge, stop a tenth of the zone past the far edge, path fill rule.
#   NOW   : current rule (the Low trend is ignored)
#   SPLIT : the GO setups whose Low trend points against the Mid (these are the ones the change would drop)
#   NEW   : the change (Low against Mid scores 2, so no Touch GO)
# Usage: python split_trend_backtest.py <datadir>
import sys, numpy as np, pandas as pd
DATA = sys.argv[1]
src = open(__file__.replace("split_trend_backtest.py", "scored_entry_backtest.py")).read()
g = {"__name__": "lib"}; sys.argv = [sys.argv[0], DATA]
exec(src.split("for style, lo, mid, hi, go_min, need_ema in STYLES:")[0], g)
zones, broken_at, first_touch, account, one_at_a_time, MAXB = (g[x] for x in ("zones", "broken_at", "first_touch", "account", "one_at_a_time", "MAXB"))
SYMS = ["US30", "NQ", "BTCUSD", "ETHUSD", "USOIL", "NVDA"]
STYLES = [("Scalping", "5m", "30m"), ("Day Trading", "1h", "4h"), ("Swing Trading", "4h", "1d")]
BASE = {"5m": "5m", "30m": "5m", "1h": "1h", "4h": "1h", "1d": "1d"}
RULE = {"30m": "30min", "4h": "4h"}
ZL, ZR = 10, 2

def load(s, iv):
    df = pd.read_csv(f"{DATA}/{s}_{BASE[iv]}.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    if iv in RULE: df = df.resample(RULE[iv]).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    return df[df.High > df.Low]

def trend_pack(h, l, c):
    n = len(c); st_o = np.zeros(n, int); cp_o = np.full(n, np.nan); cons_o = np.zeros(n, bool)
    up = False; sh1 = sh2 = sl1 = sl2 = np.nan; last = np.nan; state = 0; cp = np.nan; lo_s = hi_s = np.nan
    psh1 = psl1 = np.nan
    for i in range(n):
        p = i - ZR; ph = pl = np.nan
        if p - ZL >= 0:
            if h[p] > h[p - ZL:p].max() and h[p] >= h[p + 1:i + 1].max(): ph = h[p]
            if l[p] < l[p - ZL:p].min() and l[p] <= l[p + 1:i + 1].min(): pl = l[p]
        if np.isnan(last): last = c[i]
        ih, il = not np.isnan(ph), not np.isnan(pl)
        if up and ih:
            if ph > last: last = ph; sh1 = ph
        elif up and il: up = False; last = pl; sl2 = sl1; sl1 = pl
        elif not up and il:
            if pl < last: last = pl; sl1 = pl
        elif not up and ih: up = True; last = ph; sh2 = sh1; sh1 = ph
        if not (sl1 == psl1 or (np.isnan(sl1) and np.isnan(psl1))): lo_s = np.nan
        if not (sh1 == psh1 or (np.isnan(sh1) and np.isnan(psh1))): hi_s = np.nan
        psl1, psh1 = sl1, sh1
        lo_s = l[i] if np.isnan(lo_s) else min(lo_s, l[i]); hi_s = h[i] if np.isnan(hi_s) else max(hi_s, h[i])
        if state == -1 and ih and (np.isnan(cp) or ph < cp): cp = ph
        if state == 1 and il and (np.isnan(cp) or pl > cp): cp = pl
        res = cp if state == -1 and not np.isnan(cp) else sh1
        sup = cp if state == 1 and not np.isnan(cp) else sl1
        if state != 1 and not np.isnan(res) and c[i] > res: state = 1; cp = sl1
        elif state != -1 and not np.isnan(sup) and c[i] < sup: state = -1; cp = sh1
        new_lo = not np.isnan(sl1) and lo_s < sl1; new_hi = not np.isnan(sh1) and hi_s > sh1
        cons = (not np.isnan(sl2) and sl1 >= sl2 and not new_lo) if state == -1 else (not np.isnan(sh2) and sh1 <= sh2 and not new_hi) if state == 1 else False
        st_o[i], cp_o[i], cons_o[i] = state, cp, cons
    return st_o, cp_o, cons_o

def on_low(t, M, arr, fill):
    step = M.index.to_series().diff().median()
    s = pd.Series(arr, index=M.index + step)       # known once the Mid candle closes
    return s.reindex(t, method="ffill").fillna(fill).values

def trade(z, o, h, l, c, j, tgt):
    d = -1 if z["sup"] else 1; near = z["btm"] if z["sup"] else z["top"]; far = z["top"] if z["sup"] else z["btm"]
    stop = far - d * 0.1 * (z["top"] - z["btm"]); e = near if (o[j] - near) * d > 0 else o[j]; risk = (e - stop) * d
    if risk <= 0: return None
    for i in range(j, min(j + MAXB, len(c))):
        fav = ((h[i] - e) if d == 1 else (e - l[i])) / risk; adv = ((l[i] - e) if d == 1 else (e - h[i])) / risk
        if i == j and not ((c[i] > o[i]) if d == 1 else (c[i] < o[i])): fav = max((c[i] - e) * d / risk, 0.0)
        if adv <= -1: return (j, i, -1.0)
        if fav >= tgt: return (j, i, tgt)
    return None

def line(name, tr):
    if not tr: return f"    {name:6s}   no trades"
    r = np.array([x[2] for x in tr]); eq, mdd = account(tr)
    return f"    {name:6s} {len(r):5d} trades | win {np.mean(r > 0) * 100:5.1f}% | avg {r.mean():+.2f}R | total {r.sum():+7.1f}R | $1000 -> ${eq:,.0f} | max dd {mdd * 100:4.1f}%"

for style, lo, mid in STYLES:
    res = {(k, R): [] for k in ("NOW", "SPLIT", "NEW") for R in (2.0, 3.0)}; span = []; us30 = {}
    for s in SYMS:
        try: L, M = load(s, lo), load(s, mid)
        except FileNotFoundError: continue
        if len(L) < 300 or len(M) < 60: continue
        o, h, l, c = [L[x].values for x in ("Open", "High", "Low", "Close")]; t = L.index
        span.append(f"{s} {t[0]:%Y-%m-%d}")
        lst, lcp, lcons = trend_pack(h, l, c)
        ms, mcp, mcons = trend_pack(M.High.values, M.Low.values, M.Close.values)
        mst, mcpl, mconsl = on_low(t, M, ms, 0).astype(int), on_low(t, M, mcp, np.nan), on_low(t, M, mcons, False).astype(bool)
        e9 = pd.Series(c).ewm(span=9, adjust=False).mean().values
        sig = np.where(c > e9, 1, np.where(c < e9, -1, 0))
        yl = pd.Series(np.abs(c - o)).rolling(20).median().values
        cand = {k: {R: [] for R in (2.0, 3.0)} for k in ("NOW", "SPLIT", "NEW")}
        for z in zones(o, h, l, c, yl):
            j = first_touch(z, o, h, l, c, z["k"] + 1)
            if j is None or j < 1: continue
            d = -1 if z["sup"] else 1; near = z["btm"] if z["sup"] else z["top"]
            ts, tc, tcn = mst[j - 1], mcpl[j - 1], mconsl[j - 1]
            ok_cp = np.isnan(tc) or (near > tc if d == 1 else near < tc)
            s_tr = 2 if tcn else (4 if ok_cp else 2) if ts == d else 0 if ts == -d else 2
            if s_tr != 4 or sig[j - 1] != d: continue
            split = lst[j - 1] == -d
            for R in (2.0, 3.0):
                r = trade(z, o, h, l, c, j, R)
                if not r: continue
                x = (t[r[0]], t[r[1]], r[2])
                cand["NOW"][R].append(x)
                cand["SPLIT" if split else "NEW"][R].append(x)
        for k in cand:
            for R in (2.0, 3.0): res[(k, R)].extend(one_at_a_time(cand[k][R]))
        if s == "US30": us30 = {k: one_at_a_time(cand[k][3.0]) for k in cand}
    print(f"\n#### {style}: entry {lo}, trend {mid}   (data from: {', '.join(span)})")
    for R in (2.0, 3.0):
        print(f"  target {R:.0f}R")
        for k in ("NOW", "SPLIT", "NEW"): print(line(k, res[(k, R)]))
    if us30:
        print("  US30 only, 3R"); [print(line(k, us30[k])) for k in ("NOW", "SPLIT", "NEW")]
