import re, json, sys
sys.path.insert(0, ".")
import trip
url = ("https://tw.trip.com/hotels/list?city=7662&checkin=2026/12/03&checkout=2026/12/04"
       "&adult=2&crn=1&curr=TWD" + trip.STAR_FILTER)
st, html = trip.get(url)
text = ""
for m in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)</script>", html, re.S):
    try:
        text += "".join(x for x in json.loads(m.group(1)) if isinstance(x, str))
    except Exception:
        pass
print("HTTP", st, "len", len(text))
# 篩選條件是否生效
for k in ("listFilters", "16~4", "filterId"):
    i = text.find(k); print(k, i, text[max(0,i-150):i+250].replace("\n"," ") if i >= 0 else "")
i = text.find('"hotelId":"95343288"')
print("=== 觀海樓 found at", i)
if i >= 0:
    seg = text[max(0, i - 4000): i + 6000]
    for m in re.finditer(r'"[A-Za-z]*(?:[Ss]tar|[Dd]iamond|level|Level|grade|Grade)[A-Za-z]*":[^,\]}]{0,80}', seg):
        print("  ", m.group(0))
# 每家飯店的星級欄位
print("=== all hotels")
for m in re.finditer(r'"hotelId":"(\d+)"', text):
    blk = text[m.start(): m.start() + 6000]
    nm = re.search(r'"nameInfo":\{"name":"((?:[^"\\]|\\.)*)"', blk)
    stars = re.findall(r'"(?:star|hotelStar|starLevel|diamond|isDiamond|starType)[A-Za-z]*":[^,\]}]{0,40}', blk)
    if nm:
        print(m.group(1), nm.group(1)[:20], stars[:6])
