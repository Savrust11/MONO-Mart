import urllib.request
url="http://localhost:3000/api/period-report?product_code=sc1032&start=2026-05-01&end=2026-05-31&format=csv"
r=urllib.request.urlopen(url, timeout=120)
ct=r.headers.get("Content-Type"); disp=r.headers.get("Content-Disposition")
body=r.read()
print("Content-Type:", ct)
print("Content-Disposition:", disp)
print("先頭BOM:", body[:3]==b"\xef\xbb\xbf")
text=body.decode("utf-8-sig")
lines=text.splitlines()
print(f"総行数: {len(lines)}")
print("--- 先頭12行 ---")
for l in lines[:12]:
    print("  ", l)
