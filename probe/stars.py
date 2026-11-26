import re, time, urllib.request, html as H
from concurrent.futures import ThreadPoolExecutor
P = lambda *a: print(*a, flush=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
def head(u, n=400000):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=30)
        return r.read(n).decode("utf-8", "replace")
    except Exception as e:
        return ""
p = urllib.request.urlopen(urllib.request.Request("https://www.skygate.co.jp/hotel/LIST/180030/", headers={"User-Agent": UA}), timeout=60).read().decode("utf-8", "replace")
pairs = set(re.findall(r'&#34;regionId&#34;: &#34;(\d+)&#34;, &#34;name&#34;: \{&#34;short&#34;: \{&#34;en&#34;: &#34;([^&]+)&#34;', p))
P("Xinyi page regions:", sorted(pairs, key=lambda x: x[1])[:60])
ids = "1026 1428 178230 178231 178237 178239 178241 178248 178252 178261 178262 178263 178265 178267 178276 178279 178280 178281 178283 178286 178295 178297 178299 178302 178304 178305 178308 178311 178312 178314 178315 178316 178318 178320 179892 179893 179894 179896 179899 179981 179992 179993 179998 179999 180001 180003 180008 180012 180013 180014 180020 180026 180027 180064 180102 2062 2766 602 6034796 6046393 6049721 6177725 771 8724 890".split()
def nm(i):
    h = head(f"https://www.skygate.co.jp/hotel/LIST/{i}/")
    t = re.findall(r"<title>([^<]+)", h)
    return i, t[0][:40] if t else "?"
with ThreadPoolExecutor(4) as ex:
    for i, t in ex.map(nm, ids):
        P(i, t)
