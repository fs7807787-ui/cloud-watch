import json, urllib.request, zipfile, io, collections
raw = urllib.request.urlopen(urllib.request.Request("https://media.taiwan.net.tw/XMLReleaseAll_public/v2.0/Zh_tw/Hotel-json.zip", headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
z = zipfile.ZipFile(io.BytesIO(raw)); print(z.namelist(), len(raw))
d = json.loads(z.read(z.namelist()[0]).decode("utf-8-sig"))
def find_list(o):
    if isinstance(o, list): return o
    for v in o.values():
        r = find_list(v) if isinstance(v, (dict, list)) else None
        if r: return r
L = find_list(d); print(len(L)); print(json.dumps(L[0], ensure_ascii=False)[:700])
print(collections.Counter(json.dumps(x.get("HotelStars"), ensure_ascii=False) for x in L).most_common(10))
print(collections.Counter(json.dumps(x.get("HotelClasses"), ensure_ascii=False) for x in L).most_common(10))
for x in L:
    n = x.get("HotelName", "")
    if any(s in n for s in ("觀海樓", "璞旅", "傑仕堡", "新板希爾頓", "晶華", "煙波", "福容大飯店淡水", "觀日品月")):
        print("  ", n, x.get("HotelStars"), x.get("HotelClasses"), str(x.get("PostalAddress"))[:60])
