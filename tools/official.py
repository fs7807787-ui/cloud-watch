"""下載交通部觀光署「旅館民宿」開放資料，存成精簡的 tw_official.json（名稱、縣市、官方星級、類別）。
類別：1 國際觀光旅館、2 一般觀光旅館、3 一般旅館、4 民宿。星級 0＝沒有參加或沒有通過評鑑，6＝卓越五星。"""
import io, json, urllib.request, zipfile
URL = "https://media.taiwan.net.tw/XMLReleaseAll_public/v2.0/Zh_tw/Hotel-json.zip"
raw = urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=900).read()
z = zipfile.ZipFile(io.BytesIO(raw))
H = json.loads(z.read([n for n in z.namelist() if n.lower().endswith(".json")][0]).decode("utf-8-sig"))["Hotels"]
out = [{"n": h.get("HotelName", ""), "c": (h.get("PostalAddress") or {}).get("City", ""),
        "s": h.get("HotelStars") or 0, "k": (h.get("HotelClasses") or [0])[0]} for h in H]
json.dump(out, open("tw_official.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("官方旅宿", len(out), "家，有星級", sum(1 for x in out if x["s"]), "家")
