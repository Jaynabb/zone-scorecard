# Scored setups only: the indicator's 20 point score ported, then the entry timeframe (LOW) and the Mid timeframe
# first-touch (MID) methods compared, each in two versions:
#   FIXED 3R : every valid setup (score >= 16 on Scalping, with the 9 EMA agreeing; >= 14 elsewhere), target 3R.
#   ZONE2ZONE: valid setups with the Mid trend only, target the near edge of the opposing zone (the setup's own ratio).
# Score at the first touch (fresh zone, so purity 4):
#   range 0-2  zone middle in the High timeframe range of the last 20 closed High candles (demand: lower quarter 2,
#              middle 1; supply: upper quarter 2, middle 1)
#   time  0-2  base candles <= 3: 2, <= 6: 1
#   trend 0/2/4 Mid trend (EMA 20 over 50 on closed Mid candles): with 4, flat 2, against 0
#   move  0/2  price left the zone by at least 2 zone heights before the touch
#   OS    0/2  the move out closed through an opposing zone of the same timeframe
#   purity 4
#   rrr   0/2/4 nearest unbroken opposing zone of the same timeframe: >= 5 zone heights away 4, >= 3: 2
# Entries: limit at the near edge on the first touch, stop a tenth of the zone past the far edge, path fill rule, a
# candle that hits stop and target counts as the stop. One trade at a time per symbol. $1000, 2% of equity per trade,
# compounding. MID skips a Mid zone that already had a Low zone of its side inside it before the touch.
# Usage: python scored_entry_backtest.py <datadir>
import sys, numpy as np, pandas as pd
DATA = sys.argv[1]
SYMS = ["NVDA", "BTCUSD", "NQ", "USOIL", "ETHUSD", "US30"]
STYLES = [("Scalping", "5m", "15m", "1h", 16, True), ("Day Trading", "1h", "4h", "1d", 14, False),
          ("Swing Trading", "4h", "1d", "1w", 14, False), ("Longer Swing", "1d", "1w", "1M", 14, False)]
BASE = {"5m": "5m", "15m": "5m", "1h": "1h", "4h": "1h", "1d": "1d", "1w": "1d", "1M": "1d"}
RULE = {"15m": "15min", "4h": "4h", "1w": "W", "1M": "MS"}
MAXB = 500

def load(s, iv):
    df = pd.read_csv(f"{DATA}/{s}_{BASE[iv]}.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    if iv in RULE:
        df = df.resample(RULE[iv]).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    return df[df.High > df.Low]

def zones(o, h, l, c, yard):
    # same finder as zone_ema_backtest.zones, also returning the impulse bar and base count
    out = []; body = np.abs(c - o)
    for i in range(25, len(c) - 8):
        imp = body[i]
        if not yard[i] > 0 or imp < yard[i]: continue
        up = c[i] > o[i]; n = 0; j = i - 1
        while j >= 0 and n < 4 and body[j] <= 0.5 * imp: n += 1; j -= 1
        if n == 0: continue
        b0, b1 = i - n, i - 1
        if up: btm = l[b0:b1 + 1].min(); top = np.maximum(o, c)[b0:b1 + 1].max()
        else: top = h[b0:b1 + 1].max(); btm = np.minimum(o, c)[b0:b1 + 1].min()
        hgt = top - btm
        if hgt <= 0 or hgt > 4 * yard[i]: continue
        k_end = min(i + 8, len(c) - 1)
        ok = h[i:k_end + 1].max() >= top + hgt if up else l[i:k_end + 1].min() <= btm - hgt
        if not ok: continue
        k = next(k for k in range(i, k_end + 1) if (h[k] >= top + hgt if up else l[k] <= btm - hgt))
        out.append(dict(k=k, sup=not up, top=top, btm=btm, i=i, n=n))
    return out

def broken_at(z, c, start):
    # first bar from start whose close goes through the zone's far edge
    far = z["top"] if z["sup"] else z["btm"]
    idx = np.nonzero(c[start:] > far)[0] if z["sup"] else np.nonzero(c[start:] < far)[0]
    return start + idx[0] if len(idx) else len(c)

def first_touch(z, o, h, l, c, start):
    near = z["btm"] if z["sup"] else z["top"]; far = z["top"] if z["sup"] else z["btm"]
    for j in range(start, min(start + MAXB * 4, len(c))):
        if (h[j] >= near) if z["sup"] else (l[j] <= near): return j
        if (c[j] > far) if z["sup"] else (c[j] < far): return None
    return None

def run_trade(z, o, h, l, c, j, target_px):
    d = -1 if z["sup"] else 1
    near = z["btm"] if z["sup"] else z["top"]; far = z["top"] if z["sup"] else z["btm"]
    stop = far - d * 0.1 * (z["top"] - z["btm"])
    e = near if (o[j] - near) * d > 0 else o[j]
    risk = (e - stop) * d
    if risk <= 0: return None
    tgt_r = 3.0 if target_px is None else (target_px - e) * d / risk
    if tgt_r <= 0: return None
    for i in range(j, min(j + MAXB, len(c))):
        fav = ((h[i] - e) if d == 1 else (e - l[i])) / risk
        adv = ((l[i] - e) if d == 1 else (e - h[i])) / risk
        if i == j and not ((c[i] > o[i]) if d == 1 else (c[i] < o[i])): fav = max((c[i] - e) * d / risk, 0.0)
        if adv <= -1: return (j, i, -1.0)
        if fav >= tgt_r: return (j, i, tgt_r)
    return None

def score(z, zs, zi, touch, tz, c_tf, trend_at, rng_at):
    # tz: the zone's own timeframe bar index of the touch (for its own zones list and closes)
    d = -1 if z["sup"] else 1; hgt = z["top"] - z["btm"]
    near = z["btm"] if z["sup"] else z["top"]
    rt, rb = rng_at
    s_range = 0
    if rt is not None and rt > rb:
        pos = ((z["top"] + z["btm"]) / 2 - rb) / (rt - rb)
        s_range = (2 if pos >= 0.75 else 1 if pos > 0.25 else 0) if z["sup"] else (2 if pos <= 0.25 else 1 if pos < 0.75 else 0)
    s_time = 2 if z["n"] <= 3 else 1 if z["n"] <= 6 else 0
    s_trend = 4 if trend_at == d else 0 if trend_at == -d else 2
    s_pur = 4
    # move and OS on the zone's own timeframe, from the impulse to the candle before the touch
    seg = slice(z["i"], max(tz, z["i"] + 1))
    hh, ll, cc = c_tf
    ext = (near - ll[seg].min()) if z["sup"] else (hh[seg].max() - near)
    s_move = 2 if hgt > 0 and ext / hgt >= 2 else 0
    s_os = 0
    for oz in zs:
        if oz["sup"] == z["sup"] or oz["k"] >= z["i"] or oz["brk"] <= z["i"]: continue
        if z["i"] <= oz["brk"] < tz: s_os = 2; break
    # nearest opposing zone ahead, known and unbroken at the touch
    opp = None
    for oz in zs:
        if oz["sup"] == z["sup"] or oz["k"] >= tz or oz["brk"] <= tz: continue
        o_near = oz["top"] if z["sup"] else oz["btm"]
        if (o_near - near) * d > 0 and (opp is None or (o_near - near) * d < (opp - near) * d): opp = o_near
    rrr = None if opp is None else (opp - near) * d / hgt
    s_rrr = 0 if rrr is None else 4 if rrr >= 5 else 2 if rrr >= 3 else 0
    return s_range + s_time + s_trend + s_move + s_os + s_pur + s_rrr, s_trend, opp

def one_at_a_time(tr):
    out, busy = [], None
    for x in sorted(tr):
        if busy is None or x[0] >= busy: out.append(x); busy = x[1]
    return out

def account(tr):
    eq, peak, mdd, open_ = 1000.0, 1000.0, 0.0, []
    for et, xt, r in sorted(tr):
        for t in sorted([x for x in open_ if x[0] <= et]):
            eq += t[1]; open_.remove(t); peak = max(peak, eq); mdd = max(mdd, (peak - eq) / peak)
        open_.append((xt, eq * 0.02 * r))
    for t in sorted(open_):
        eq += t[1]; peak = max(peak, eq); mdd = max(mdd, (peak - eq) / peak)
    return eq, mdd

def line(name, tr):
    if not tr: return f"    {name:5s}    no trades"
    r = np.array([x[2] for x in tr]); eq, mdd = account(tr)
    return (f"    {name:5s} {len(r):5d} trades | win {np.mean(r > 0) * 100:5.1f}% | avg win {r[r > 0].mean() if (r > 0).any() else 0:4.1f}R"
            f" | avg {r.mean():+.2f}R | total {r.sum():+7.1f}R | $1000 -> ${eq:,.0f} | max dd {mdd * 100:4.1f}%")

def mid_trend(t_index, M):
    step = M.index.to_series().diff().median()
    tr = np.sign(M.Close.ewm(span=20, adjust=False).mean() - M.Close.ewm(span=50, adjust=False).mean())
    tr.index = tr.index + step
    return tr.reindex(t_index, method="ffill").fillna(0).values.astype(int)

def high_range(t_index, H):
    step = H.index.to_series().diff().median()
    rt = H.High.rolling(20).max(); rb = H.Low.rolling(20).min()
    rt.index = rt.index + step; rb.index = rb.index + step
    return rt.reindex(t_index, method="ffill").values, rb.reindex(t_index, method="ffill").values

for style, lo, mid, hi, go_min, need_ema in STYLES:
    res = {(m, v): [] for m in ("LOW", "MID") for v in ("3R", "Z2Z")}
    span = []
    for s in SYMS:
        L, M, H = load(s, lo), load(s, mid), load(s, hi)
        if len(L) < 300 or len(M) < 60 or len(H) < 25: continue
        o, h, l, c = [L[x].values for x in ("Open", "High", "Low", "Close")]; t = L.index
        span.append(f"{s} {t[0]:%Y-%m}")
        trend = mid_trend(t, M); rT, rB = high_range(t, H)
        e9 = pd.Series(c).ewm(span=9, adjust=False).mean().values
        sig = np.where(c > e9, 1, np.where(c < e9, -1, 0))
        # Low zones
        yl = pd.Series(np.abs(c - o)).rolling(20).median().values
        lz = zones(o, h, l, c, yl)
        for z in lz: z["brk"] = broken_at(z, c, z["k"] + 1)
        mo, mh, ml, mc = [M[x].values for x in ("Open", "High", "Low", "Close")]
        ym = pd.Series(np.abs(mc - mo)).rolling(20).median().values
        mz = zones(mo, mh, ml, mc, ym)
        for z in mz: z["brk"] = broken_at(z, mc, z["k"] + 1)
        mstep = M.index.to_series().diff().median()
        out = {(m, v): [] for m in ("LOW", "MID") for v in ("3R", "Z2Z")}
        # LOW
        for z in lz:
            j = first_touch(z, o, h, l, c, z["k"] + 1)
            if j is None or j < 1: continue
            d = -1 if z["sup"] else 1
            rng = (None, None) if np.isnan(rT[j - 1]) else (rT[j - 1], rB[j - 1])
            total, s_tr, opp = score(z, lz, None, j, j, (h, l, c), trend[j - 1], rng)
            if total < go_min or (need_ema and sig[j - 1] != d): continue
            r = run_trade(z, o, h, l, c, j, None)
            if r: out[("LOW", "3R")].append((t[r[0]], t[r[1]], r[2]))
            if s_tr == 4 and opp is not None:
                r = run_trade(z, o, h, l, c, j, opp)
                if r: out[("LOW", "Z2Z")].append((t[r[0]], t[r[1]], r[2]))
        # MID: first touch of a Mid zone, traded on the entry timeframe's candles
        for z in mz:
            s0 = t.searchsorted(M.index[z["k"]] + mstep)
            if s0 >= len(c): continue
            j = first_touch(z, o, h, l, c, s0)
            if j is None or j < 1: continue
            if any(lzz["sup"] == z["sup"] and lzz["k"] < j and lzz["top"] >= z["btm"] and lzz["btm"] <= z["top"] for lzz in lz): continue
            d = -1 if z["sup"] else 1
            tz = M.index.searchsorted(t[j], side="right") - 1
            rng = (None, None) if np.isnan(rT[j - 1]) else (rT[j - 1], rB[j - 1])
            total, s_tr, opp = score(z, mz, None, j, max(tz, z["i"] + 1), (mh, ml, mc), trend[j - 1], rng)
            if total < go_min or (need_ema and sig[j - 1] != d): continue
            r = run_trade(z, o, h, l, c, j, None)
            if r: out[("MID", "3R")].append((t[r[0]], t[r[1]], r[2]))
            if s_tr == 4 and opp is not None:
                r = run_trade(z, o, h, l, c, j, opp)
                if r: out[("MID", "Z2Z")].append((t[r[0]], t[r[1]], r[2]))
        for key in out: res[key].extend(one_at_a_time(out[key]))
    print(f"\n#### {style}: entry {lo}, Mid {mid}, High {hi}, valid score >= {go_min}{' + 9 EMA' if need_ema else ''}   (data from: {', '.join(span)})")
    print("  FIXED 3:1"); print(line("LOW", res[("LOW", "3R")])); print(line("MID", res[("MID", "3R")]))
    print("  ZONE TO ZONE, with trend only"); print(line("LOW", res[("LOW", "Z2Z")])); print(line("MID", res[("MID", "Z2Z")]))
