import sys, collections
sys.path.insert(0, ".")
import trip, datetime as dt
from concurrent.futures import ThreadPoolExecutor
d = dt.date(2026, 12, 3)
def f(cid):
    url = (f"https://tw.trip.com/hotels/list?city={cid}&checkin={d:%Y/%m/%d}&checkout={d+dt.timedelta(1):%Y/%m/%d}"
           f"&adult=2&crn=1&curr=TWD{trip.STAR_FILTER}")
    return cid, trip.parse(trip.get(url)[1])
with ThreadPoolExecutor(3) as ex:
    for cid, items in ex.map(f, trip.CITIES):
        c = collections.Counter((x[4][1], x[4][0]) for x in items)
        print(trip.CITIES[cid], dict(c))
        for x in items:
            if x[4][1] != 1:
                print("    非官方星級：", x[1], x[4])
# 觀海樓
url = ("https://tw.trip.com/hotels/list?city=7662&checkin=2026/12/26&checkout=2026/12/27&adult=2&crn=1&curr=TWD" + trip.STAR_FILTER)
for x in trip.parse(trip.get(url)[1]):
    if "觀海" in x[1] or "璞旅" in x[1]: print("找到：", x)
