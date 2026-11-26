import json, urllib.request
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
for ds in (73281, 7780):
    try:
        d = json.loads(get(f"https://data.gov.tw/api/v2/rest/dataset/{ds}"))
        r = d.get("result", d)
        print(ds, r.get("title"))
        for x in r.get("distribution", []):
            print("   ", x.get("resourceFormat"), x.get("resourceDownloadUrl"))
    except Exception as e:
        print("ERR", ds, repr(e))
