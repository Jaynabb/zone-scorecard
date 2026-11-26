# Structural zone reader (no preset candle sizes), tested against Jay's marked zones in zone_fixtures.csv.
# A zone is leg in, base, leg out, read only from where candles sit relative to each other:
#   move out  a candle that closes beyond the whole base (supply: below its lowest low, demand: above its highest high)
#   base      walking back from the move out, each earlier candle stays in the base while the candle after it closed
#             inside its range (the candles sit side by side)
#             (their ranges overlap by at least half); a candle whose body is several times the base's bodies, or that
#             opened outside the base and travelled into it without engulfing it, is the move in
#   first     the first base candle must not itself break out in the move out's direction (then it is the move)
#   edges     wick to body (supply: highest wick to lowest body, demand: lowest wick to highest body)
#   departure price must leave the base by its own body span (or half its average candle range, whichever is bigger)
#             and by 1.5 normal candles (median body of the last 20) within 8 candles of the move out
#   pause     the base holds at least one candle whose body is under half its range
# Usage: python zone_struct.py <lab data dir>   (prints each fixture: expected vs found)
import sys, os, csv, glob, re, numpy as np, pandas as pd
D = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))

def candles(sym, tf):
    if tf == "1M":
        src = open(os.path.join(HERE, "base_rules_monthly_check.py")).read()
        raw = re.search(r'raw="""(.*?)"""', src, re.S).group(1)
        rows = [r.split(",") for r in raw.split(";")]
        df = pd.DataFrame([[pd.Timestamp(r[0] + "-01", tz="America/New_York")] + [float(x) for x in r[1:]] for r in rows], columns=["dt", "o", "h", "l", "c"])
        return df
    sub = {"5m": "scalp", "1h": "day"}[tf]; style = {"5m": "Scalping", "1h": "Day"}[tf]
    df = pd.read_csv(os.path.join(D, sub, f"{sym}_{style}.csv"))[["t", "o", "h", "l", "c"]]
    extra = os.path.join(D, f"{sym}_{tf}_ohlc.csv")
    if os.path.exists(extra):
        df = pd.concat([df, pd.read_csv(extra)]).drop_duplicates("t", keep="last").sort_values("t")
    df["dt"] = pd.to_datetime(df.t, unit="s", utc=True).dt.tz_convert("America/New_York")
    return df.reset_index(drop=True)

def zones(df, max_base=12, dep_bars=8):
    o, h, l, c = (df[k].values for k in "ohlc"); n = len(c); out = []
    body = np.abs(c - o); bhi = np.maximum(o, c); blo = np.minimum(o, c); rng = np.maximum(h - l, 1e-12)
    for sup in (True, False):
        for i in range(2, n):
            # the move out: closes beyond the body of the candle before it
            if not (c[i] < blo[i - 1] if sup else c[i] > bhi[i - 1]): continue
            b = [i - 1]; j = i - 1
            while j - 1 >= 0 and len(b) < max_base:
                k = j - 1
                # side by side: the two candles' ranges overlap by at least half of the smaller one
                ov = min(h[k], h[j]) - max(l[k], l[j])
                if ov < 0.5 * min(rng[k], rng[j]): break
                # a travelling candle (body most of its range) well bigger than the base's bodies is the move in
                if body[k] >= 0.45 * rng[k] and body[k] > 1.5 * np.median(body[b]): break
                j = k; b.insert(0, j)
            # the base starts at the turn: the candle with the most extreme body, or an earlier one holding the extreme
            # wick; candles stepping toward it before that are the move in
            bb = np.array(b)
            e = int(np.argmax(bhi[bb])) if sup else int(np.argmin(blo[bb]))
            w = int(np.argmax(h[bb])) if sup else int(np.argmin(l[bb]))
            b = list(bb[min(e, w):])
            # the candle right before the move out is base only if it is not itself travelling against the rest of the
            # base (then the move out started there)
            if len(b) >= 2:
                lst = b[-1]
                rest = b[:-1]
                same_way = c[lst] < blo[rest].min() if sup else c[lst] > bhi[rest].max()
                # ... unless the move out candle is over twice its size: then the real move starts there and the
                # last candle is still part of the pause (BTC 5M 19:05 under the 19:10 leg out)
                if same_way and body[lst] >= 0.45 * rng[lst] and body[lst] > 1.5 * np.median(body[rest]) and body[i] <= 2 * body[lst]: continue
            # the move out closes beyond the base's bodies
            if not (c[i] < blo[b].min() if sup else c[i] > bhi[b].max()): continue
            # the first base candle is not itself a breakout in the move out's direction (then it is part of the move)
            f = b[0]
            if f - 1 >= 0 and (c[f] < l[f - 1] if sup else c[f] > h[f - 1]): continue
            top = h[b].max() if sup else bhi[b].max(); btm = blo[b].min() if sup else l[b].min()
            # spike wicks on a base of 2+ candles: reach past the bodies over 3x the median reach and longer than its body
            if len(b) >= 2:
                reach = np.maximum((h[b] - bhi[b].max()) if sup else (blo[b].min() - l[b]), 0)
                wick = (h[b] - bhi[b]) if sup else (blo[b] - l[b])
                thr = max(3 * np.median(reach), 0.25 * (bhi[b].max() - blo[b].min()))
                keep = ~((reach > thr) & (wick > body[b]))
                if keep.any():
                    if sup: top = h[np.array(b)[keep]].max()
                    else: btm = l[np.array(b)[keep]].min()
            # one candle doji (body at most a quarter of its range) whose far side wick is shorter than its body:
            # long wick to the body's far side
            if len(b) == 1:
                k = b[0]; far_w = (h[k] - bhi[k]) if sup else (blo[k] - l[k]); near_w = (blo[k] - l[k]) if sup else (h[k] - bhi[k])
                if body[k] <= 0.25 * rng[k] and far_w <= body[k] and near_w > far_w:
                    top, btm = (bhi[k], l[k]) if sup else (h[k], blo[k])
            # departure: price leaves the base by its own body span (at least half its average candle range)
            span = max(bhi[b].max() - blo[b].min(), 0.5 * np.mean(rng[b]))
            seg = slice(i, min(i + dep_bars, n))
            if not (l[seg].min() <= btm - span if sup else h[seg].max() >= top + span): continue
            yard = np.median(body[max(0, i - 20):i])
            dep = (btm - l[seg].min()) if sup else (h[seg].max() - top)
            pause = bool((body[b] < 0.5 * rng[b]).any())
            # a real move: price leaves by at least 1.5 normal candles (median body of the last 20), and the base has a
            # pause candle (body under half its range): a turn made only of travelling candles is not a base
            if dep < 1.5 * yard or not pause: continue
            out.append(dict(sup=sup, t0=df.dt[b[0]], t1=df.dt[b[-1]], top=top, btm=btm, n=len(b), imp=df.dt[i], dep_y=dep / max(yard, 1e-12), pause=pause))
    return out

fx = [r for r in csv.reader(l for l in open(os.path.join(HERE, "zone_fixtures.csv")) if not l.startswith("#"))]
cache = {}; ok = 0
for sym, tf, side, bt, eb, et, tol, note in fx:
    key = (sym, tf)
    try:
        if key not in cache: cache[key] = zones(candles(sym, tf))
    except FileNotFoundError:
        print(f"  ??   {sym} {tf} {side} {bt}: no candle data"); continue
    eb, et = float(eb), float(et); t = pd.Timestamp(bt, tz="America/New_York"); hgt = et - eb
    cand = [z for z in cache[key] if z["sup"] == (side == "supply") and z["t0"] - pd.Timedelta(hours=1 if tf == "5m" else 24 if tf == "1h" else 24 * 70) <= t <= z["t1"] + pd.Timedelta(hours=1 if tf == "5m" else 24 if tf == "1h" else 24 * 70)
            and z["top"] >= eb and z["btm"] <= et]
    best = max(cand, key=lambda z: (min(z["top"], et) - max(z["btm"], eb)) / (max(z["top"], et) - min(z["btm"], eb)), default=None)
    tol = float(tol)
    good = best is not None and abs(best["btm"] - eb) <= tol * hgt and abs(best["top"] - et) <= tol * hgt
    ok += good
    got = "nothing" if best is None else f"{best['btm']:.2f}-{best['top']:.2f} base {best['t0']:%m-%d %H:%M}..{best['t1']:%H:%M} ({best['n']}) out {best['imp']:%H:%M} dep {best['dep_y']:.1f}x pause {best['pause']}"
    print(f"  {'PASS' if good else 'FAIL'} {sym:6s} {tf:3s} {side:6s} {bt}: want {eb}-{et} | got {got}")
print(f"\n{ok} of {len(fx)} pass")
