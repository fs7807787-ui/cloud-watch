import re, json, sys, urllib.request, html as H, time
sys.path.insert(0, ".")
import trip
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=40).read().decode("utf-8", "replace")
# Trip.com 座標欄位
st, h = trip.get("https://tw.trip.com/hotels/list?city=7662&checkin=2026/12/03&checkout=2026/12/04&adult=2&crn=1&curr=TWD" + trip.STAR_FILTER)
text = "".join("".join(x for x in json.loads(m.group(1)) if isinstance(x, str)) for m in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)</script>", h, re.S))
i = text.find('"hotelId":"'); blk = text[i:i+8000]
print("TRIP coord:", re.findall(r'"(?:lat|lng|lon|latitude|longitude|coordinate\w*|enName|nameEn|address)"\s*:\s*[^,]{0,80}', blk)[:10])
# skygate 篩選選項
l2 = get("https://www.skygate.co.jp/hotel/LIST/6047811/?page=1")
for m in re.finditer(r'filterCategoryId[^>]*>', l2):
    print("FILTER:", H.unescape(m.group(0))[:200])
i = l2.find("stars4"); print("STARCTX:", re.sub(r"\s+", " ", l2[i-600:i+300]))
# 地區名稱
for rid in ["178307","178230","178231","178236","178237","178239","178241","178248","178252","178261","178262","178263","178265","178267","178276","178279","178280","178281","178283","178286","178293","178295","178297","178299","178302","178304","178305","178308","178311","178312","178314","178315","178316","178318","178320","179892","179893","179894","179896","179898","179899","179981","179992","179993","179998","179999","180001","180003","180008","180012","180013","180014","180020","180026","180027","180030","180064","180102","6034796","6046393","6049721","6140738","6177725"]:
    try:
        p = get(f"https://www.skygate.co.jp/hotel/LIST/{rid}/?page=1")
        m = re.search(r'&#34;regionId&#34;: &#34;' + rid + r'&#34;, &#34;name&#34;: \{&#34;short&#34;: \{&#34;en&#34;: &#34;([^&]+)&#34;', p)
        tot = re.findall(r'(\d[\d,]*)\s*件', p)[:2]
        print(rid, m.group(1) if m else "?", tot)
    except Exception as e:
        print(rid, "ERR", e)
    time.sleep(0.5)
