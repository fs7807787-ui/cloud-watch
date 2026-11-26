import json, urllib.request, collections
for url in ["https://media.taiwan.net.tw/XMLReleaseALL_public/hotel_C_f.json"]:
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
        print(url, len(raw))
        txt = raw.decode("utf-8-sig", "replace")
        d = json.loads(txt)
        info = d
        for k in ("XML_Head", "Infos", "Info"):
            if isinstance(info, dict) and k in info: info = info[k]
        print(type(info), len(info))
        print(json.dumps(info[0], ensure_ascii=False)[:800])
        keys = [k for k in info[0] if k.lower() in ("grade", "class", "star", "level")]
        for k in keys:
            print(k, collections.Counter(str(x.get(k)) for x in info).most_common(12))
        for x in info:
            if any(s in x.get("Name", "") for s in ("觀海樓", "板城璞旅", "傑仕堡", "希爾頓", "晶華", "煙波")):
                print("  ", x.get("Name"), {k: x.get(k) for k in keys}, x.get("Add", "")[:20])
    except Exception as e:
        print("ERR", url, repr(e))
