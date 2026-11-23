# Zone entry backtest: retest + EMA (current rule) versus waiting for the lower timeframe swing trend to flip the
# zone's way after the retest. Zones use the simplified detection in zone_ema_backtest.py on the zone timeframe.
# The LTF trend follows the readout's 3 segment rule on pivot swings (higher highs and higher lows is UP, lower
# highs and lower lows is DOWN, a close through the control point ends it). Usage:
#   python ltf_flip_backtest.py <datadir>
import sys, numpy as np, pandas as pd
DATA = sys.argv[1]
SYMS = ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD", "NQ"]
EMAS = (9, 21, 50)
PIV = 3                      # pivot strength on the LTF, candles each side

src = open(__file__.replace("ltf_flip_backtest.py", "zone_ema_backtest.py")).read().split("\nr = run()")[0]
g = {}; sys.argv = [sys.argv[0], DATA, "1d"]; exec(src, g)
zones = g["zones"]

def load(s, iv):
    df = pd.read_csv(f"{DATA}/{s}_{iv}.csv", index_col=0)[["Open", "High", "Low", "Close"]].dropna()
    idx = pd.to_datetime(df.index, utc=True)
    if iv != "1d":
        idx = idx.tz_convert("America/New_York")
    df.index = idx.tz_localize(None)
    return df[df.High > df.Low]

def ltf_trend(h, l, c):
    # state after each candle closes: 1 up, -1 down, 0 neither; pivots known PIV candles after they print
    n = len(c); st = np.zeros(n, int)
    ph, pl = [], []
    s = 0; cp = np.nan
    for i in range(n):
        p = i - PIV
        if p >= PIV:
            if h[p] == h[p - PIV:p + PIV + 1].max(): ph.append(h[p])
            if l[p] == l[p - PIV:p + PIV + 1].min(): pl.append(l[p])
            if len(ph) >= 2 and len(pl) >= 2:
                if ph[-1] > ph[-2] and pl[-1] > pl[-2]: s, cp = 1, pl[-1]
                elif ph[-1] < ph[-2] and pl[-1] < pl[-2]: s, cp = -1, ph[-1]
        if s == 1 and c[i] < cp: s = 0
        if s == -1 and c[i] > cp: s = 0
        st[i] = s
    return st

def sim(h, l, start, entry, stop, target, d, maxb):
    risk = (entry - stop) * d
    if risk <= 0: return None
    for j in range(start, min(start + maxb, len(h))):
        if (l[j] <= stop if d == 1 else h[j] >= stop): return -1.0
        if (h[j] >= target if d == 1 else l[j] <= target): return (target - entry) * d / risk
    return None

def run(ziv, liv, maxb_z, maxb_l, resample=None):
    out = {k: [] for k in ("A", "F", "F_same_target", "pairA", "pairF", "never")}
    for s in SYMS:
        lt = load(s, liv)
        zt = lt.resample(resample, label="left", closed="left").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna() if resample else load(s, ziv)
        o, h, l, c = [zt[x].values for x in ("Open", "High", "Low", "Close")]
        yard = pd.Series(np.abs(c - o)).rolling(20).median().values
        em = np.vstack([zt.Close.ewm(span=p, adjust=False).mean().values for p in EMAS])
        up = l > em.max(0); dn = h < em.min(0); sig = np.zeros(len(c), int); stt = 0
        for i in range(1, len(c)):
            if up[i] and not up[i - 1]: stt = 1
            if dn[i] and not dn[i - 1]: stt = -1
            sig[i] = stt
        lh, ll, lc = lt.High.values, lt.Low.values, lt.Close.values
        lst = ltf_trend(lh, ll, lc); lidx = lt.index.values
        for (k, sup, top, btm) in zones(o, h, l, c, yard):
            if k < 60: continue
            d = -1 if sup else 1
            near, far = (btm, top) if sup else (top, btm); hgt = top - btm
            stop = far - d * 0.1 * hgt
            target = near + d * 2 * abs(near - stop)
            for j in range(k + 1, min(k + 1 + maxb_z * 2, len(c))):
                if (l[j] <= near if d == 1 else h[j] >= near):
                    if zt.index[j] < lt.index[0] + pd.Timedelta(days=3): break   # no LTF data yet
                    e = near if (o[j] - near) * d > 0 else o[j]
                    ra = sim(h, l, j, e, stop, target, d, maxb_z) if (e - stop) * d > 0 and sig[j - 1] == d else None
                    # LTF flip: from the retest candle on, first LTF close with the trend the zone's way while the
                    # zone is alive; entry at that close, same zone stop
                    a = np.searchsorted(lidx, zt.index.values[j])
                    rf = rfs = None; found = False
                    for m in range(a, min(a + maxb_l, len(lc))):
                        if (lc[m] - far) * d < 0: break
                        if lst[m] == d:
                            found = True
                            rf = sim(lh, ll, m + 1, lc[m], stop, lc[m] + d * 2 * abs(lc[m] - stop), d, maxb_l * 4)
                            if (target - lc[m]) * d > 0:
                                rfs = sim(lh, ll, m + 1, lc[m], stop, target, d, maxb_l * 4)
                            break
                    if ra is not None: out["A"].append(ra)
                    if rf is not None: out["F"].append(rf)
                    if rfs is not None: out["F_same_target"].append(rfs)
                    if ra is not None and rf is not None: out["pairA"].append(ra); out["pairF"].append(rf)
                    if ra is not None and not found: out["never"].append(ra)
                    break
                if (c[j] - far) * d < 0: break
    return out

def f(v):
    v = np.array(v)
    return f"{len(v):4d} trades | win {np.mean(v > 0) * 100:5.1f}% | avg {v.mean():+.2f}R | total {v.sum():+6.1f}R" if len(v) else "no trades"

for name, ziv, liv, mz, ml, rs in (("POSITION: Daily zones, 1H trend flip", "1d", "1h", 120, 24 * 20, None),
                                   ("DAY: 1H zones, 5M trend flip", None, "5m", 48, 12 * 24, "1h"),
                                   ("SCALP: 30M zones, 5M trend flip", None, "5m", 96, 12 * 24, "30min")):
    r = run(ziv, liv, mz, ml, rs)
    print(f"\n=== {name} | {', '.join(SYMS)} ===")
    print(f"  A  retest + EMA agrees (current rule)        {f(r['A'])}")
    print(f"  F  wait for LTF flip, 2R from the new entry   {f(r['F'])}")
    print(f"  F' wait for LTF flip, same price target as A  {f(r['F_same_target'])}")
    print(f"  same zones (both took it): A {f(r['pairA'])}")
    print(f"                             F {f(r['pairF'])}")
    print(f"  A trades where the LTF never flipped before the zone broke: {f(r['never'])}")
