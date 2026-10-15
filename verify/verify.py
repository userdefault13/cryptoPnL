import json,urllib.request
R="https://mainnet.base.org"
def rpc(m,p):
    d=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for _ in range(5):
        try:
            r=json.load(urllib.request.urlopen(urllib.request.Request(R,d,{"content-type":"application/json","user-agent":"x"}),timeout=30))
            if "result" in r: return r["result"]
        except Exception as e: pass
        import time; time.sleep(1)
    return None
def code(a,b): return rpc("eth_getCode",[a,hex(b)]) not in ("0x",None)
def deploy(a,hi):
    lo=0
    while lo<hi:
        mid=(lo+hi)//2
        if code(a,mid): hi=mid
        else: lo=mid+1
    return lo
def call(to,data,b="latest"): return rpc("eth_call",[{"to":to,"data":data},b])
pad=lambda a:a[2:].lower().rjust(64,"0")
head=int(rpc("eth_blockNumber",[]),16); print("head",head)
T={"USDC":"0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913","WETH":"0x4200000000000000000000000000000000000006",
"cbBTC":"0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf","GHST":"0xcD2F22236DD9Dfe2356D7C543161D4d260FD9BcB",
"FUD":"0x2028b4043e6722Ea164946c82fe806c4a43a0fF4","FOMO":"0xA32137bfb57d2b6A9Fd2956Ba4B54741a6D54b58",
"ALPHA":"0x15e7CaC885e3730ce6389447BC0f7AC032f31947","KEK":"0xE52b9170fF4ece4C35E796Ffd74B57Dec68Ca0e5",
"GLTR":"0x4D140CE792bEdc430498c2d219AfBC33e2992c9D"}
def sym(a):
    r=call(a,"0x95d89b41")
    try: b=bytes.fromhex(r[2:]); n=int.from_bytes(b[32:64],"big"); return b[64:64+n].decode()
    except: return r
def dec(a): return int(call(a,"0x313ce567"),16)
def bal(t,a): r=call(t,"0x70a08231"+pad(a)); return int(r,16) if r and r!="0x" else 0
F="0x33128a8fC17869897dcE68Ed026d694621f6FDfD"; AF="0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
print("uni factory deploy",deploy(F,1371904))
print("aero factory code",code(AF,head))
for k,a in T.items():
    print(k,a,sym(a),dec(a),"deploy",deploy(a,head))
out=[]
for k in ["WETH","cbBTC","GHST","FUD","FOMO","ALPHA","KEK","GLTR"]:
    for q in ["USDC","WETH"]:
        if k==q: continue
        a,b=T[k],T[q]
        for fee in [100,500,3000,10000]:
            p=call(F,"0x1698ee82"+pad(a)+pad(b)+hex(fee)[2:].rjust(64,"0"))
            p="0x"+p[-40:]
            if int(p,16)==0: continue
            liq=int(call(p,"0x1a686502"),16)
            print("UNI",k,q,fee,p,"liq",liq,"bal",k,bal(a,p)/10**dec(a),q,bal(b,p)/10**dec(b),"deploy",deploy(p,head))
        for st in [0,1]:
            p=call(AF,"0x79bc57d5"+pad(a)+pad(b)+hex(st)[2:].rjust(64,"0"))
            if not p or p=="0x": print("aero call fail");break
            p="0x"+p[-40:]
            if int(p,16)==0: continue
            print("AERO",k,q,"stable" if st else "volatile",p,"bal",k,bal(a,p)/10**dec(a),q,bal(b,p)/10**dec(b),"deploy",deploy(p,head))
