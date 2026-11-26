import re, urllib.request, html as H
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
p = urllib.request.urlopen(urllib.request.Request("https://www.skygate.co.jp/hotel/LIST/6177725/", headers={"User-Agent": UA}), timeout=90).read().decode("utf-8", "replace")
u = H.unescape(p)
for m in re.finditer(r"Taiwan", u):
    print("TW:", re.sub(r"\s+", " ", u[max(0, m.start()-200):m.start()+60]))
    break
print(sorted(set(re.findall(r'"regionId":\s*"(\d+)"[^{}]{0,80}?"en":\s*"([^"]+)"', u)))[:40])
for m in list(re.finditer(r"viewport", u))[:6]:
    print("VP:", re.sub(r"\s+", " ", u[max(0, m.start()-150):m.start()+200]))
