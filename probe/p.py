import urllib.request, gzip
u = "https://store.line.me/stickershop/showcase/top_creators/zh-Hant?page=3"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=30).read()
g = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA, "Accept-Encoding": "gzip"}), timeout=30)
gb = g.read()
print("plain", len(r), "gzip", len(gb), g.headers.get("Content-Encoding"))
