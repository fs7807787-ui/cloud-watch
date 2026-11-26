import re, urllib.request, urllib.robotparser
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
rp = urllib.robotparser.RobotFileParser("https://www.skygate.co.jp/robots.txt"); rp.read()
for u in ["https://www.skygate.co.jp/hotel/LIST/6047811/", "https://www.skygate.co.jp/hotel/HTLITM/2854642/",
          "https://www.skygate.co.jp/hotel/LIST/6047811/?page=2"]:
    print(u, "robots ok:", rp.can_fetch(UA, u))
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA, "Accept-Language": "ja"}), timeout=40)
        h = r.read().decode("utf-8", "replace")
        print("  HTTP", r.status, len(h), "つ星:", re.findall(r"[\d.]+つ星", h)[:15])
        print("  HTLITM links:", len(set(re.findall(r"/hotel/HTLITM/(\d+)/", h))))
        i = h.find("つ星"); print("  ctx:", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h[max(0, i-1500):i+200]))[-700:])
        print("  paging:", sorted(set(re.findall(r'href="([^"]*(?:page|PAGE|pg)[^"]*)"', h)))[:8])
    except Exception as e:
        print("  ERR", repr(e))
