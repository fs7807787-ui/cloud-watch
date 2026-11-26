import re, json, sys, time, urllib.request, urllib.parse, html as H
sys.path.insert(0, ".")
import trip
P = lambda *a: print(*a, flush=True)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
def get(u):
    t = time.time()
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=25).read().decode("utf-8", "replace")
    except Exception as e:
        r = ""; P("   ERR", repr(e)[:100])
    P(f"   {time.time()-t:.1f}s {len(r)} {u[:110]}")
    return r
st, h = trip.get("https://tw.trip.com/hotels/list?city=7662&checkin=2026/12/03&checkout=2026/12/04&adult=2&crn=1&curr=TWD" + trip.STAR_FILTER)
text = "".join("".join(x for x in json.loads(m.group(1)) if isinstance(x, str)) for m in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)</script>", h, re.S))
i = text.find('"hotelId":"'); blk = text[i:i+8000]
P("TRIP fields:", re.findall(r'"(?:lat|lng|lon|latitude|longitude|enName|nameEn|address|positionInfo)"\s*:\s*[^,]{0,60}', blk)[:10])
P("TRIP nameInfo:", re.search(r'"nameInfo":\{[^}]{0,300}', blk).group(0))
def parse_sky(p):
    out = []
    for m in re.finditer(r'ホテルランク:\s*([\d.]+)つ星\s*ホテルID:\s*(\d+)', re.sub(r"<[^>]+>", " ", H.unescape(p))):
        out.append((m.group(2), m.group(1)))
    names = re.findall(r'&#34;hotelCode&#34;: &#34;(\d+)&#34;.{0,400}?&#34;name&#34;: \{&#34;en&#34;: &#34;([^&]*)&#34;, &#34;jp&#34;: &#34;([^&]*)&#34;', p)
    return out, [(a, b, c.encode().decode("unicode_escape", "ignore") if "\\u" in c else c) for a, b, c in names]
for q in ["觀海樓", "Hotel Cloud Riverside", "煙波", "Lakeshore"]:
    u = "https://www.skygate.co.jp/hotel/list?" + urllib.parse.urlencode({"regionId": "6047811", "hotelName": q, "form": "research_form", "rooms": 1})
    p = get(u); s, n = parse_sky(p); P(q, s[:6], n[:6])
