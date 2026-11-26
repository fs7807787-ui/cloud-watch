import re, urllib.request, time, sys
sys.path.insert(0, ".")
import ptt
for name, h, q in [("ptt 原本", {"User-Agent": ptt.UA, "Cookie": "over18=1"}, True),
                   ("不帶 cookie", {"User-Agent": ptt.UA}, True),
                   ("簡單 UA", {"User-Agent": "Mozilla/5.0"}, True),
                   ("簡單 UA 無參數", {"User-Agent": "Mozilla/5.0"}, False)]:
    u = "https://www.ptt.cc/atom/Lifeismoney.xml" + (f"?t={int(time.time())}" if q else "")
    r = urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=30)
    x = r.read().decode()
    print(name, re.findall(r"<updated>([^<]+)</updated>", x)[:3], r.headers.get("Age"), r.headers.get("X-Cache"), r.headers.get("CF-Cache-Status"))
