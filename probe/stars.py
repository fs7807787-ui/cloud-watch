import re, urllib.request, urllib.robotparser, html as H
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=40).read().decode("utf-8", "replace")
h = get("https://www.skygate.co.jp/hotel/")
links = sorted(set(re.findall(r'href="(/hotel/[^"]+)"', h)))
print(len(links)); print([l for l in links if not l.startswith("/hotel/HTLITM")][:80])
l2 = get("https://www.skygate.co.jp/hotel/LIST/6047811/?page=2")
print("form names:", sorted(set(re.findall(r'name="([^"]+)"', l2)))[:60])
print("rank opts:", re.findall(r'(?:rank|Rank|star)[^<>]{0,120}', l2)[:12])
print("total:", re.findall(r'(\d+)\s*件', l2)[:5])
