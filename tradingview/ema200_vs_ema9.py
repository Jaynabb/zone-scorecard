# "Super secret 200 EMA" (buy while the candle closes above the 200 EMA, sell while it closes below) versus the
# indicator's 9 EMA signal (default: the whole candle above / below the 9 EMA flips it; also the close-only variant).
#   PART A  signal on its own: trade every flip, held until the opposite flip (stop and reverse), and with a fixed
#           stop of 1 ATR(14) and a 2R target. R is in ATR(14) at entry. Data: <datadir>/<SYM>_<iv>.csv (5m, 1h, 1d).
#   PART B  as the zone filter: Touch GO setups from the lab (first visit, purity 4, Mid trend 4, no reaction / retired /
#           superseded zone, EMA not required), split by whether the 9 EMA, the 200 EMA, both or neither point the
#           zone's way on the candle before the touch. Exits as split_trend_lab.py.
# Usage: python ema200_vs_ema9.py <datadir> <lab dir with lab_candidates.pkl>... (Scalping and Day labs have pkl files)
import sys, os, numpy as np, pandas as pd
DATA, LABS = sys.argv[1], sys.argv[2:]
SYMS = ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD", "NQ"]

def signals(o, h, l, c):
    e9 = pd.Series(c).ewm(span=9, adjust=False).mean().values
    e200 = pd.Series(c).ewm(span=200, adjust=False).mean().values
    out = {}
    for nm, up, dn in (("9 EMA full candle (current)", l > e9, h < e9), ("9 EMA close", c > e9, c < e9),
                       ("200 EMA close (secret)", c > e200, c < e200)):
        s = np.zeros(len(c), int); st = 0
        for i in range(len(c)):
            if up[i]: st = 1
            elif dn[i]: st = -1
            s[i] = st
        s[:400] = 0   # warm up the 200
        out[nm] = s
    return out

def f(v):
    v = np.array(v)
    return f"{len(v):6d} trades | win {np.mean(v > 0) * 100:5.1f}% | avg {v.mean():+.3f}R | total {v.sum():+8.1f}R" if len(v) else "no trades"

print("PART A  each signal on its own")
for iv in ("5m", "1h", "1d"):
    res = {}
    for s in SYMS:
        df = pd.read_csv(f"{DATA}/{s}_{iv}.csv", index_col=0, parse_dates=True)[["Open", "High", "Low", "Close"]].dropna()
        df = df[df.High > df.Low]; o, h, l, c = (df[k].values for k in ("Open", "High", "Low", "Close"))
        tr = np.maximum(h - l, np.maximum(abs(h - np.roll(c, 1)), abs(l - np.roll(c, 1))))
        atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
        for nm, sg in signals(o, h, l, c).items():
            r = res.setdefault(nm, {"sar": [], "2r": [], "sym": {}})
            flips = [i for i in range(1, len(c) - 1) if sg[i] != 0 and sg[i] != sg[i - 1]]
            sym_r = []
            for a, b in zip(flips, flips[1:] + [len(c) - 1]):
                d = sg[a]; x = (c[b] - c[a]) * d / atr[a]; r["sar"].append(x); sym_r.append(x)
                sl, tp = c[a] - d * atr[a], c[a] + 2 * d * atr[a]
                for j in range(a + 1, min(a + 300, len(c))):
                    if (l[j] <= sl) if d == 1 else (h[j] >= sl): r["2r"].append(-1.0); break
                    if (h[j] >= tp) if d == 1 else (l[j] <= tp): r["2r"].append(2.0); break
            r["sym"][s] = np.mean(sym_r) if sym_r else np.nan
    print(f"\n=== {iv} | {', '.join(SYMS)} ===")
    for nm, r in res.items():
        print(f"  {nm}")
        print(f"    hold to opposite flip  {f(r['sar'])}")
        print(f"    1 ATR stop, 2R target  {f(r['2r'])}")
        print("    hold avg by symbol     " + "  ".join(f"{k} {v:+.2f}" for k, v in r["sym"].items()))

print("\n\nPART B  as the filter on Touch GO zone setups")
EX = [("Z0.1", "to opposing zone"), ("R2", "2R"), ("EMA9", "9 EMA exit")]
def row(name, s):
    out = f"    {name:28s} {len(s):5d}"
    for k, _ in EX:
        v = s[k].dropna(); out += f" | {k:4s} win {np.mean(v > 0) * 100:4.1f}% avg {v.mean():+.2f}R" if len(v) else ""
    return out
for D in LABS:
    df = pd.read_pickle(os.path.join(D, "lab_candidates.pkl"))
    df = df[(df.et == "TOUCH") & (df.pur == 4) & (df.trend == 4) & ~df.rr & ~df.retired & ~df.sup_].copy()
    sig = {}
    for (sym, style) in df[["sym", "style"]].drop_duplicates().itertuples(index=False):
        x = pd.read_csv(os.path.join(D, f"{sym}_{style}.csv"))
        e200 = x.c.ewm(span=200, adjust=False).mean().values
        s200 = np.where(x.c.values > e200, 1, np.where(x.c.values < e200, -1, 0)); s200[:400] = 0
        sig[(sym, style)] = (x.t.values, s200)
    def at(r):
        t, s = sig[(r.sym, r.style)]; j = np.searchsorted(t, r.t)
        return s[j - 1] if j >= 1 else 0
    df["s200"] = df.apply(at, axis=1); df["d"] = np.where(df.side == "s", -1, 1)
    df = df[df.s200 != 0]
    w9, w200 = df.ema == 1, df.s200 == df.d
    for style in df["style"].unique():
        m = df["style"] == style; s0 = df[m]
        print(f"\n#### {style}  ({', '.join(sorted(s0.sym.unique()))})")
        print(row("all (no EMA filter)", s0))
        print(row("9 EMA with zone (current)", s0[w9[m]]))
        print(row("200 EMA with zone (secret)", s0[w200[m]]))
        print(row("both agree", s0[(w9 & w200)[m]]))
        print(row("9 yes, 200 no", s0[(w9 & ~w200)[m]]))
        print(row("200 yes, 9 no", s0[(~w9 & w200)[m]]))
        print(row("neither", s0[(~w9 & ~w200)[m]]))
        for h in (0, 1):
            sh = s0[s0.half == h]; mh = (s0.half == h)
            print(f"  {'first' if h == 0 else 'second'} half: 9 EMA {row('', sh[w9[m][mh]])[34:]}")
            print(f"  {'first' if h == 0 else 'second'} half: 200   {row('', sh[w200[m][mh]])[34:]}")
