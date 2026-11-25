# Mid timeframe first-touch entry against the Low (entry) timeframe entry, per trade style, on the watchlist.
#   LOW: every fresh Low timeframe zone, limit at the near edge on its first touch (what the indicator trades).
#   MID: the first touch of a Mid timeframe zone with no Low timeframe zone of the same side inside it from before the
#        touch (the removed "Enter On First Mid TF Touch" rule), limit at the Mid zone's near edge.
# Both: stop a tenth of the zone height past the far edge, target 3R, a candle that hits both counts as the stop, the
# touch candle only keeps its favourable extreme when it closed in our favour (path rule). Zones come from the same
# simple finder (zone_ema_backtest.zones) for both, without the indicator's score filter.
# One trade at a time per symbol and method (a new touch is skipped while that symbol's trade is open); symbols trade
# side by side. "filtered" keeps only setups the indicator could call a GO: with the Mid trend (EMA 20 over 50 on closed
# Mid candles) and with the 9 EMA signal (last close above / below the 9 EMA on the entry timeframe).
# Account: $1000, 2% of equity risked per trade, compounding; a trade's result is booked when it closes and a new trade
# risks 2% of the equity booked so far.
# Usage: python mid_vs_low_entry_backtest.py <datadir>
import sys, numpy as np, pandas as pd
DATA = sys.argv[1]
SYMS = ["NVDA", "BTCUSD", "NQ", "USOIL", "ETHUSD", "US30"]
STYLES = [("Scalping", "5m", "15m"), ("Day Trading", "1h", "4h"), ("Swing Trading", "4h", "1d"), ("Longer Swing", "1d", "1w")]
BASE = {"5m": "5m", "15m": "5m", "1h": "1h", "4h": "1h", "1d": "1d", "1w": "1d"}
RULE = {"15m": "15min", "4h": "4h", "1w": "W"}
MAXB = 500
src = open(__file__.replace("mid_vs_low_entry_backtest.py", "zone_ema_backtest.py")).read()
g = {"np": np}; exec("def zones" + src.split("\ndef zones")[1].split("\ndef sim")[0], g); zones = g["zones"]

def load(s, iv):
    df = pd.read_csv(f"{DATA}/{s}_{BASE[iv]}.csv", index_col=0)
    df.index = pd.to_datetime(df.index, utc=True)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    if iv in RULE:
        df = df.resample(RULE[iv]).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    return df[df.High > df.Low]

def trade(o, h, l, c, start, near, far, d, end):
    # first touch from start; None if the zone is closed through first or never touched
    hgt = abs(near - far); stop = far - d * 0.1 * hgt
    for j in range(start, end):
        if (c[j] - far) * d < 0 and not ((l[j] <= near) if d == 1 else (h[j] >= near)):
            return None
        if (l[j] <= near) if d == 1 else (h[j] >= near):
            e = near if (o[j] - near) * d > 0 else o[j]
            if (e - stop) * d <= 0: return None
            risk = (e - stop) * d
            for i in range(j, min(j + MAXB, len(c))):
                fav = ((h[i] - e) if d == 1 else (e - l[i])) / risk
                adv = ((l[i] - e) if d == 1 else (e - h[i])) / risk
                if i == j and not ((c[i] > o[i]) if d == 1 else (c[i] < o[i])): fav = max((c[i] - e) * d / risk, 0.0)
                if adv <= -1: return (j, i, -1.0)
                if fav >= 3: return (j, i, 3.0)
            return None
    return None

def one_at_a_time(tr):
    out, busy = [], None
    for x in sorted(tr):
        if busy is None or x[0] >= busy:
            out.append(x); busy = x[1]
    return out

def account(tr):
    # tr: list of (entry_time, exit_time, R)
    eq, peak, mdd = 1000.0, 1000.0, 0.0
    open_ = []
    for et, xt, r in sorted(tr):
        for t in sorted([x for x in open_ if x[0] <= et]):
            eq += t[1]; open_.remove(t); peak = max(peak, eq); mdd = max(mdd, (peak - eq) / peak)
        open_.append((xt, eq * 0.02 * r))
    for t in sorted(open_):
        eq += t[1]; peak = max(peak, eq); mdd = max(mdd, (peak - eq) / peak)
    return eq, mdd

def line(name, tr):
    if not tr: return f"  {name:5s}   no trades"
    r = np.array([x[2] for x in tr]); eq, mdd = account(tr)
    return f"  {name:5s} {len(r):5d} trades | win {np.mean(r > 0) * 100:5.1f}% | avg {r.mean():+.2f}R | total {r.sum():+7.1f}R | $1000 -> ${eq:,.0f} | max drawdown {mdd * 100:4.1f}%"

for style, lo, mid in STYLES:
    LOW, MID, LOWf, MIDf, span = [], [], [], [], []
    for s in SYMS:
        L = load(s, lo); M = load(s, mid)
        if len(L) < 300 or len(M) < 60: continue
        o, h, l, c = [L[x].values for x in ("Open", "High", "Low", "Close")]; t = L.index
        span.append(f"{s} {t[0]:%Y-%m-%d}")
        yl = pd.Series(np.abs(c - o)).rolling(20).median().values
        lz = zones(o, h, l, c, yl)
        e9 = pd.Series(c).ewm(span=9, adjust=False).mean().values
        sig = np.zeros(len(c)); sig[c > e9] = 1; sig[c < e9] = -1
        Mtr = load(s, mid); step0 = Mtr.index.to_series().diff().median()
        tr_m = np.sign(Mtr.Close.ewm(span=20, adjust=False).mean() - Mtr.Close.ewm(span=50, adjust=False).mean())
        tr_m.index = tr_m.index + step0
        trend = tr_m.reindex(t, method="ffill").fillna(0).values
        ok = lambda j, d: trend[j - 1] == d and sig[j - 1] == d
        sL, sM, sLf, sMf = [], [], [], []
        for (k, sup, top, btm) in lz:
            d = -1 if sup else 1; near, far = (btm, top) if sup else (top, btm)
            r = trade(o, h, l, c, k + 1, near, far, d, min(k + 1 + MAXB * 4, len(c)))
            if r:
                sL.append((t[r[0]], t[r[1]], r[2]))
                if ok(r[0], d): sLf.append((t[r[0]], t[r[1]], r[2]))
        mo, mh, ml, mc = [M[x].values for x in ("Open", "High", "Low", "Close")]
        ym = pd.Series(np.abs(mc - mo)).rolling(20).median().values
        step = M.index.to_series().diff().median()
        for (k, sup, top, btm) in zones(mo, mh, ml, mc, ym):
            known = M.index[k] + step
            s0 = t.searchsorted(known)
            if s0 >= len(c): continue
            d = -1 if sup else 1; near, far = (btm, top) if sup else (top, btm)
            r = trade(o, h, l, c, s0, near, far, d, min(s0 + MAXB * 4, len(c)))
            if not r: continue
            touch = r[0]
            # skip when a Low zone of the same side already sat inside the Mid zone before the touch (that case is the LOW trade)
            inner = any(sp == sup and kk < touch and tp >= btm and bt <= top for (kk, sp, tp, bt) in lz)
            if not inner:
                sM.append((t[r[0]], t[r[1]], r[2]))
                if ok(r[0], d): sMf.append((t[r[0]], t[r[1]], r[2]))
        for dst, srcl in ((LOW, sL), (MID, sM), (LOWf, sLf), (MIDf, sMf)):
            dst.extend(one_at_a_time(srcl))
    print(f"\n#### {style}: entry {lo}, Mid {mid}   (data from: {', '.join(span)})")
    print("  all setups");  print(line("LOW", LOW)); print(line("MID", MID))
    print("  filtered (with Mid trend and 9 EMA)"); print(line("LOW", LOWf)); print(line("MID", MIDf))
