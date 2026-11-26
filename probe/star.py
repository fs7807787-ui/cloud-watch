import json, re, sys, collections, urllib.request, zipfile, io
sys.path.insert(0, ".")
import trip
url = ("https://tw.trip.com/hotels/list?city=7662&checkin=2026/12/03&checkout=2026/12/04&adult=2&crn=1&curr=TWD" + trip.STAR_FILTER)
st, html = trip.get(url)
text = ""
for m in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)</script>", html, re.S):
    try: text += "".join(x for x in json.loads(m.group(1)) if isinstance(x, str))
    except Exception: pass
i = text.find('"hotelId":"25195615"')
blk = text[i:i+9000]
for m in re.finditer(r'"(?:[a-zA-Z]*(?:[Ll]at|[Ll]on|[Cc]oordinate|[Aa]ddress|[Pp]osition)[a-zA-Z]*)":[^\]}]{0,120}', blk):
    print("  ", m.group(0)[:160])
raw = urllib.request.urlopen(urllib.request.Request("https://media.taiwan.net.tw/XMLReleaseAll_public/v2.0/Zh_tw/Hotel-json.zip", headers={"User-Agent": "Mozilla/5.0"}), timeout=300).read()
z = zipfile.ZipFile(io.BytesIO(raw)); L = json.loads(z.read("HotelList.json").decode("utf-8-sig"))["Hotels"]
print(len(L))
print("stars", collections.Counter(x.get("HotelStars") for x in L))
print("classes", collections.Counter(tuple(x.get("HotelClasses") or []) for x in L).most_common(8))
print("marks", collections.Counter(json.dumps(x.get("HotelCertificationMarks"), ensure_ascii=False)[:80] for x in L).most_common(8))
for x in L:
    if x.get("HotelStars") in (4, 5) and len([1]) and x["PostalAddress"]["City"] == "新北市":
        print("  新北", x["HotelStars"], x["HotelName"])
