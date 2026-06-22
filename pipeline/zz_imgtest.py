import urllib.request
goods="92598860"  # sc1032 の item_code
base=f"https://o.imgz.jp/{goods[-3:]}/{goods}/{goods}b_"
print(f"テストURL: {base}NN_d.jpg")
found=[]
for n in range(1,31):
    for cc in (f"{n:02d}", str(n)):
        url=f"{base}{cc}_d.jpg"
        try:
            req=urllib.request.Request(url, method="HEAD", headers={"User-Agent":"Mozilla/5.0"})
            r=urllib.request.urlopen(req, timeout=8)
            ct=r.headers.get("Content-Type","")
            if r.status==200 and "image" in ct:
                found.append((cc, r.headers.get("Content-Length")))
                print(f"  OK  色コード={cc}  ({ct}, {r.headers.get('Content-Length')}B)")
            break
        except Exception as e:
            code=getattr(e,'code',None)
            if code and code!=404:
                print(f"  色コード={cc}: HTTP {code}")
            break
print(f"\n有効な色コード数: {len(found)}  → 値: {[f[0] for f in found]}")
