import re, time, urllib.request, urllib.parse, html as H
P = lambda *a: print(*a, flush=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
def get(u):
    try:
        return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=40).read().decode("utf-8", "replace")
    except Exception as e:
        return "ERR " + repr(e)[:60]
def stars(p):
    return re.findall(r'ホテルランク:\s*([\d.]+)つ星\s*ホテルID:\s*(\d+)', re.sub(r"<[^>]+>", " ", H.unescape(p)))[:4]
for rid in ["216", "214", "215", "110", "213", "212", "217", "6177725", "6047811"]:
    for q in ["觀海樓", "Lakeshore Hotel", "Shinjuku"]:
        p = get("https://www.skygate.co.jp/hotel/list?" + urllib.parse.urlencode({"regionId": rid, "hotelName": q, "form": "research_form", "rooms": 1}))
        cr = re.search(r'&#34;regionId&#34;: &#34;' + rid + r'&#34;, &#34;name&#34;: \{&#34;short&#34;: \{&#34;en&#34;: &#34;([^&]+)', p)
        P(rid, q, p[:20] if p.startswith("ERR") else "", stars(p), cr.group(1) if cr else "")
        time.sleep(0.3)
