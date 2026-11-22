import pandas as pd, numpy as np, itertools, sys
SYMS=["EURUSD","GBPUSD","XAUUSD","BTCUSD","NQ"]
SETS=[(9,21),(20,50),(21,50),(50,200),(9,21,50),(8,21,55),(13,48,200),(20,50,200),(21,50,200),(10,20,50),(5,13,34),(34,89,200)]
def load(s,iv):
    df=pd.read_csv(f"data/{s}_{iv}.csv",index_col=0,parse_dates=True)
    df=df[["Open","High","Low","Close"]].dropna()
    return df[(df.High>df.Low)]
def outcome(h,l,c,atr,i,d,rr,maxb=60):
    e=c[i]; r=atr[i]
    if not r>0: return None
    sl=e-d*r; tp=e+d*rr*r
    for j in range(i+1,min(i+1+maxb,len(c))):
        if d==1:
            if l[j]<=sl: return -1
            if h[j]>=tp: return rr
        else:
            if h[j]>=sl: return -1
            if l[j]<=tp: return rr
    return None
def run(iv,mode):
    rows=[]
    for st in SETS:
        res={1:[],2:[]}; n=0
        for s in SYMS:
            df=load(s,iv)
            o,h,l,c=[df[k].values for k in ("Open","High","Low","Close")]
            emas=np.vstack([df.Close.ewm(span=p,adjust=False).mean().values for p in st])
            top=emas.max(0); bot=emas.min(0)
            tr=np.maximum(h-l,np.maximum(abs(h-np.roll(c,1)),abs(l-np.roll(c,1))))
            atr=pd.Series(tr).ewm(alpha=1/14,adjust=False).mean().values
            lo=np.minimum(o,c) if mode=="body" else l
            hi=np.maximum(o,c) if mode=="body" else h
            buy=lo>top; sell=hi<bot
            start=max(st)*2
            for i in range(start,len(c)-1):
                for d,sig in ((1,buy),(-1,sell)):
                    if sig[i] and not sig[i-1]:
                        n+=1
                        for rr in (1,2):
                            x=outcome(h,l,c,atr,i,d,rr)
                            if x is not None: res[rr].append(x)
        w1=np.mean([x>0 for x in res[1]]); w2=np.mean([x>0 for x in res[2]])
        rows.append(("/".join(map(str,st)),n,round(w1*100,1),round(w2*100,1),round(np.mean(res[2]),3)))
    t=pd.DataFrame(rows,columns=["emas","signals","win%_1R","win%_2R","exp_R_at_2R"]).sort_values("exp_R_at_2R",ascending=False)
    print(f"\n=== {iv} | {mode} ===");print(t.to_string(index=False))
if __name__=="__main__":
    for iv in ("1d","1h","5m"):
        for mode in ("body","full"):
            run(iv,mode)
