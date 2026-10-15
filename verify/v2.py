exec(open('verify.py').read().split("F=")[0])
F="0x33128a8fC17869897dcE68Ed026d694621f6FDfD"; AF="0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
for k in ["FUD","FOMO","ALPHA","KEK","GLTR"]:
  a,b=T[k],T["GHST"]
  for fee in [500,3000,10000]:
    p="0x"+call(F,"0x1698ee82"+pad(a)+pad(b)+hex(fee)[2:].rjust(64,"0"))[-40:]
    if int(p,16): print("UNI",k,"GHST",fee,p,bal(a,p)/1e18,bal(b,p)/1e18,"deploy",deploy(p,head))
  for st in [0,1]:
    p="0x"+call(AF,"0x79bc57d5"+pad(a)+pad(b)+hex(st)[2:].rjust(64,"0"))[-40:]
    if int(p,16): print("AERO",k,"GHST",st,p,bal(a,p)/1e18,bal(b,p)/1e18,"deploy",deploy(p,head))
