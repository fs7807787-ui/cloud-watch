"""把 Trip.com 追蹤中的飯店，跟觀光署官方旅館資料（星級、類別）比對，結果存成 stars-check.json。"""
import collections, datetime as dt, difflib, io, json, re, sys, urllib.request, zipfile
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, ".")
import trip

# 1. Trip.com：所有城市、所有日期，記下每家飯店的星級標示
today = dt.datetime.now(trip.TZ).date()
jobs = [(c, d) for c in trip.CITIES for d in trip.dates(today)]
def f(job):
    c, d = job
    ci = dt.date.fromisoformat(d)
    url = (f"https://tw.trip.com/hotels/list?city={c}&checkin={ci:%Y/%m/%d}&checkout={ci + dt.timedelta(1):%Y/%m/%d}"
           f"&adult=2&crn=1&curr=TWD{trip.STAR_FILTER}")
    return c, trip.parse(trip.get(url)[1])
T = {}
with ThreadPoolExecutor(3) as ex:
    for c, items in ex.map(f, jobs):
        for hid, name, price, bed, star in items:
            T[hid] = {"hid": hid, "name": name, "city": trip.CITIES[c], "tw": c in trip.TAIWAN, "trip_star": star[0], "trip_type": star[1]}
print("Trip.com 飯店數", len(T))

# 2. 觀光署官方資料
raw = urllib.request.urlopen(urllib.request.Request("https://media.taiwan.net.tw/XMLReleaseAll_public/v2.0/Zh_tw/Hotel-json.zip",
                             headers={"User-Agent": "Mozilla/5.0"}), timeout=300).read()
z = zipfile.ZipFile(io.BytesIO(raw))
O = json.loads(z.read([n for n in z.namelist() if n.lower().endswith(".json")][0]).decode("utf-8-sig"))["Hotels"]
print("官方資料筆數", len(O), collections.Counter(x.get("HotelStars") for x in O).most_common(),
      collections.Counter(tuple(x.get("HotelClasses") or []) for x in O).most_common(6))
CITY = {"台北": ["臺北市"], "新北": ["新北市"], "桃園": ["桃園市"], "台中": ["臺中市"], "台南": ["臺南市"], "高雄": ["高雄市"],
        "宜蘭": ["宜蘭縣"], "花蓮": ["花蓮縣"], "台東": ["臺東縣"], "屏東墾丁": ["屏東縣"], "南投": ["南投縣"], "嘉義": ["嘉義市", "嘉義縣"]}
def norm(s):
    s = s.replace("臺", "台").replace("酒店", "飯店").replace("大飯店", "飯店").replace("旅店", "飯店")
    s = re.sub(r"[（(].*?[）)]", "", s)
    return re.sub(r"[^\w]", "", s).lower()
byc = collections.defaultdict(list)
for x in O:
    byc[(x.get("PostalAddress") or {}).get("City", "")].append(x)
for h in T.values():
    if not h["tw"]:
        continue
    best, score = None, 0
    n = norm(h["name"])
    for cty in CITY[h["city"]]:
        for x in byc[cty]:
            m = norm(x.get("HotelName", ""))
            r = 1.0 if (n and (n in m or m in n) and min(len(n), len(m)) >= 4) else difflib.SequenceMatcher(None, n, m).ratio()
            if r > score:
                best, score = x, r
    if best and score >= 0.75:
        h.update(off_name=best["HotelName"], off_star=best.get("HotelStars"), off_class=best.get("HotelClasses"), match=round(score, 2))
    else:
        h.update(off_name=None, match=round(score, 2), off_guess=best["HotelName"] if best else None)
open("stars-check.json", "w").write(json.dumps(list(T.values()), ensure_ascii=False, indent=0))
tw = [h for h in T.values() if h["tw"]]
print("台灣", len(tw), "對到官方", sum(1 for h in tw if h.get("off_name")),
      "官方有星級", sum(1 for h in tw if h.get("off_star")))
