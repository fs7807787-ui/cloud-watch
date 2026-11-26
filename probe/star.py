import re, urllib.request, time
for b in ("Lifeismoney", "Japan_Travel", "Tour-Agency"):
    x = urllib.request.urlopen(urllib.request.Request(f"https://www.ptt.cc/atom/{b}.xml?t={int(time.time())}", headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode()
    up = re.findall(r"<updated>([^<]+)</updated>", x)[:4]
    ti = re.findall(r"<title[^>]*>([^<]+)</title>", x)[1:4]
    print(b, up, ti)
