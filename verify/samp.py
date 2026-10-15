exec(open('verify.py').read().split("head=")[0])
import random,concurrent.futures as cf
head=52629471
TR="0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
SW3="0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
SWA="0xb3e2773606abfd36b5bd91394b3a54d1398336b65d7ef9fe2a8d1f58b1f7c2d7"
J=[("WETH Transfer","0x4200000000000000000000000000000000000006",TR,0,100),
("cbBTC Transfer","0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf",TR,18688094,200),
("GHST Transfer","0xcD2F22236DD9Dfe2356D7C543161D4d260FD9BcB",TR,12631572,2000),
("FUD Transfer","0x2028b4043e6722Ea164946c82fe806c4a43a0fF4",TR,34095837,2000),
("FOMO Transfer","0xA32137bfb57d2b6A9Fd2956Ba4B54741a6D54b58",TR,34095847,2000),
("ALPHA Transfer","0x15e7CaC885e3730ce6389447BC0f7AC032f31947",TR,34095858,2000),
("KEK Transfer","0xE52b9170fF4ece4C35E796Ffd74B57Dec68Ca0e5",TR,34095868,2000),
("GLTR Transfer","0x4D140CE792bEdc430498c2d219AfBC33e2992c9D",TR,34095879,2000),
("UNI WETH/USDC 0.05 Swap","0xd0b53d9277642d899df5c87a3966a349a798f224",SW3,3620407,500),
("UNI cbBTC/USDC 0.05 Swap","0xfbb6eed8e7aa03b138556eedaf5d271a5e1e43ef",SW3,19763050,1000),
("AERO WETH/USDC Swap","0xcdac0d6c6c59727a65f871236188350531885c43",SWA,3647441,1000),
("AERO GHST/WETH Swap","0x0dfb9cb66a18468850d6216fcc691aa20ad1e091",SWA,13295275,2000),
("AERO FUD/GHST Swap","0xeae2fb93e291c2eb69195851813de24f97f1ce71",SWA,34402583,2000)]
def one(j):
  name,a,t,s,w=j; tot=0;ok=0;random.seed(1)
  for i in range(12):
    b=random.randint(s,head-w)
    r=rpc("eth_getLogs",[{"address":a,"topics":[t],"fromBlock":hex(b),"toBlock":hex(b+w-1)}])
    if r is None: continue
    tot+=len(r);ok+=1
  est=tot/(ok*w)*(head-s) if ok else None
  return name,ok,tot,est
with cf.ThreadPoolExecutor(4) as ex:
  for r in ex.map(one,J): print(r[0],"samples",r[1],"logs",r[2],"est_total %.3g"%r[3] if r[3] else "n/a")
