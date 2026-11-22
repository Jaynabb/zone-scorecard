import pandas as pd, numpy as np
from ema_backtest import load, outcome, SYMS
import sys
iv=sys.argv[1]; sets=[(9,21,50),(10,20,50),(5,13,34),(21,50),(21,50,200),(50,200)]
def stats(xs): return (len(xs), round(np.mean([x>0 for x in xs])*100,1) if xs else None, round(np.mean(xs),3) if xs else None)
for s in SYMS:
    df=load(s,iv); o,h,l,c=[df[k].values for k in ("Open","High","Low","Close")]
    tr=np.maximum(h-l,np.maximum(abs(h-np.roll(c,1)),abs(l-np.roll(c,1))))
    atr=pd.Series(tr).ewm(alpha=1/14,adjust=False).mean().values
    base={1:[],-1:[]}
    for i in range(400,len(c)-1,3):
        for d in (1,-1):
            x=outcome(h,l,c,atr,i,d,2)
            if x is not None: base[d].append(x)
    line=f"{s:7s} baseline buy {stats(base[1])} sell {stats(base[-1])}"
    print(line)
    for st in sets:
        emas=np.vstack([df.Close.ewm(span=p,adjust=False).mean().values for p in st])
        top=emas.max(0); bot=emas.min(0)
        buy=l>top; sell=h<bot; r={1:[],-1:[]}
        for i in range(400,len(c)-1):
            for d,sig in ((1,buy),(-1,sell)):
                if sig[i] and not sig[i-1]:
                    x=outcome(h,l,c,atr,i,d,2)
                    if x is not None: r[d].append(x)
        print(f"   {'/'.join(map(str,st)):10s} buy {stats(r[1])} sell {stats(r[-1])}")
