import sys, numpy as np
sys.argv=[sys.argv[0], sys.argv[1], sys.argv[2]]
import importlib.util
spec=importlib.util.spec_from_file_location("z","/Users/jay/Desktop/Trade Cheat Sheet/tradingview/zone_ema_backtest.py")
src=open(spec.origin).read().split("\nr = run()")[0]
g={}; exec(src,g)
import pandas as pd
for SY in g["SYMS"]+["ALL"]:
    A=[];B2=[];pairA=[];pairB=[]
    for s in (g["SYMS"] if SY=="ALL" else [SY]):
        df=g["load"](s); o,h,l,c=[df[x].values for x in ("Open","High","Low","Close")]
        yard=pd.Series(np.abs(c-o)).rolling(20).median().values
        em=np.vstack([df.Close.ewm(span=p,adjust=False).mean().values for p in g["EMAS"]])
        up=l>em.max(0); dn=h<em.min(0); sig=np.zeros(len(c),int); st=0
        for i in range(1,len(c)):
            if up[i] and not up[i-1]: st=1
            if dn[i] and not dn[i-1]: st=-1
            sig[i]=st
        bb=np.r_[False, up[1:]&~up[:-1]]; sb=np.r_[False, dn[1:]&~dn[:-1]]
        for (k,sup,top,btm) in g["zones"](o,h,l,c,yard):
            if k<60: continue
            d=-1 if sup else 1; near,far=(btm,top) if sup else (top,btm); hgt=top-btm
            stop=far-d*0.1*hgt; target=near+d*2*abs(near-stop)
            ra=rb=None; fb=False
            for j in range(k+1,min(k+1+g["MAXB"]*2,len(c))):
                if not fb and ((d==1 and bb[j]) or (d==-1 and sb[j])) and (c[j]-near)*d>0:
                    fb=True; rb=g["sim"](h,l,c,j+1,c[j],stop,c[j]+d*2*abs(c[j]-stop),d)
                if (l[j]<=near if d==1 else h[j]>=near):
                    e=near if (o[j]-near)*d>0 else o[j]
                    if (e-stop)*d>0 and sig[j-1]==d: ra=g["sim"](h,l,c,j,e,stop,target,d)
                    break
                if (c[j]-far)*d<0: break
            if ra is not None: A.append(ra)
            if rb is not None: B2.append(rb)
            if ra is not None and rb is not None: pairA.append(ra); pairB.append(rb)
    f=lambda v: f"{len(v):4d} trades, win {np.mean(np.array(v)>0)*100:4.1f}%, avg {np.mean(v):+.2f}R" if v else "none"
    print(f"{SY:7s} A retest+EMA: {f(A)} | B2 EMA candle: {f(B2)} | same zones: A {np.mean(pairA) if pairA else 0:+.2f}R vs B2 {np.mean(pairB) if pairB else 0:+.2f}R (n={len(pairA)})")
