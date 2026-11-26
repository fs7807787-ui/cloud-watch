"""Trip.com 飯店 bug 價監控（GitHub 雲端執行）

每次執行：
1. 查每個城市、每個入住日期的飯店列表（Trip.com 台灣站，新台幣）
2. 記下每家飯店在每個日期的價格歷史（data/trip.json）
   只看四星、五星；台灣 12 個地區、日本 7 個城市、韓國 3 個城市
3. 價格異常就發 ntfy 到 bug 價 topic：
   - 比這家飯店同一日期自己的歷史中位數低 60% 以上（至少要有 3 筆紀錄）
   - 比這家飯店這一輪其他日期中最便宜的還便宜 65% 以上（第一次看到也能抓）
   - 價格約是平常的 1/10（疑似少打一個 0）
4. 同一家飯店同一個日期 24 小時內只通知一次

設定在檔案最上面的 CITIES、DAYS_AHEAD、FIXED_DATES。只用 Python 標準函式庫。
"""
import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

CITIES = {
    # 台灣
    617: "台北", 7662: "新北", 7570: "桃園", 3849: "台中", 3847: "台南", 720: "高雄",
    7614: "宜蘭", 6954: "花蓮", 3848: "台東", 5589: "屏東墾丁", 7524: "南投", 650358: "嘉義",
    # 日本
    228: "東京", 219: "大阪", 734: "京都", 248: "福岡", 360: "名古屋", 641: "札幌", 92573: "沖繩那霸",
    # 韓國
    274: "首爾", 253: "釜山", 737: "濟州",
}
STAR_FILTER = "&listFilters=16~4*16*4%2C16~5*16*5"   # 只看四星、五星
DAYS_AHEAD = [7, 14, 30]                     # 幾天後入住（住 1 晚）
FIXED_DATES = ["2026-12-24", "2026-12-31", "2027-02-04", "2027-02-27", "2027-04-02"]  # 連假前一天
DATA = os.environ.get("TRIP_FILE", "data/trip.json")
NTFY_TOPIC = os.environ.get("NTFY_BUG_TOPIC", "").strip()
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
KEEP = 30            # 每家飯店每個日期最多保留幾筆價格
DROP_HIST = 0.40     # 低於自己歷史中位數的 40%（便宜 60%）
DROP_DATES = 0.35    # 低於其他日期中「最便宜」的 35%（便宜 65%）
TZ = dt.timezone(dt.timedelta(hours=8))


def log(*a):
    print(*a, flush=True)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return e.code, ""
        except Exception:
            pass
        time.sleep(3 * (i + 1))
    return 0, ""


SKIP_BEDS = ("上下舖", "床位", "宿舍", "膠囊")


def parse(html):
    """從 Next.js 的資料片段取出每家飯店：編號、名稱、2 位大人的總價（新台幣）、床型。
    上下舖、床位、宿舍這類不算（不是一般客房，容易誤報）。"""
    text = ""
    for m in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)</script>", html, re.S):
        try:
            arr = json.loads(m.group(1))
            text += "".join(x for x in arr if isinstance(x, str))
        except Exception:
            continue
    out, seen = [], set()
    for m in re.finditer(r'"hotelId":"(\d+)"', text):
        hid = m.group(1)
        if hid in seen:
            continue
        nxt = text.find('"hotelId":"', m.end())
        block = text[m.start():(nxt if 0 < nxt < m.start() + 12000 else m.start() + 7000)]
        nm = re.search(r'"nameInfo":\{"name":"((?:[^"\\]|\\.)*)"', block)
        pr = re.search(r'"price":(\d+(?:\.\d+)?),"currency":"TWD"', block)
        if not (nm and pr):
            continue
        seen.add(hid)
        bed = re.search(r'"bedInfo":\{"list":\[[^\]]*\],"contentList":\["([^"]+)"', block)
        bed = bed.group(1) if bed else "?"
        if any(k in bed for k in SKIP_BEDS):
            continue
        sm = re.search(r'"hotelStar":\{"star":(\d+(?:\.\d+)?)[^{}]*?"starType":(\d+)', block)
        star = (float(sm.group(1)), int(sm.group(2))) if sm else (0.0, 0)
        tot = re.search(r'"priceExplanation":"總價：TWD([\d,]+)', block)
        price = float(tot.group(1).replace(",", "")) if tot else float(pr.group(1))
        try:
            name = json.loads('"' + nm.group(1) + '"')
        except Exception:
            name = nm.group(1)
        out.append((hid, name.strip("\u200b "), price, bed, star))
    return out


def dates(today):
    ds = [(today + dt.timedelta(days=n)).isoformat() for n in DAYS_AHEAD]
    ds += [d for d in FIXED_DATES if d > today.isoformat()]
    return sorted(set(ds))


def ntfy(title, msg, click):
    if not NTFY_TOPIC:
        log("（還沒設定 NTFY_BUG_TOPIC，不發通知）", title)
        return False
    body = json.dumps({"topic": NTFY_TOPIC, "title": title, "message": msg, "priority": 3,
                       "tags": ["rotating_light"], "click": click}).encode()
    for i in range(4):
        try:
            req = urllib.request.Request("https://ntfy.sh/", data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                if json.loads(r.read().decode()).get("id"):
                    log("通知已送出：", title)
                    return True
        except Exception as e:
            log("ntfy 失敗：", repr(e))
        time.sleep(5 * (i + 1))
    return False


def main():
    dry = "--dry" in sys.argv
    try:
        with open(DATA, encoding="utf-8") as f:
            D = json.load(f)
    except Exception:
        D = {"hotels": {}, "alerted": {}, "pending": []}
    now = dt.datetime.now(TZ)
    today = now.date()
    H = D.setdefault("hotels", {})
    # 過期的入住日期刪掉
    for h in H.values():
        for k in [k for k in h["p"] if k[:10] <= today.isoformat() or "|" not in k]:
            del h["p"][k]
    alerts, seen_total = [], 0
    jobs = [(cid, d) for cid in CITIES for d in dates(today)]

    def fetch(job):
        cid, d = job
        ci = dt.date.fromisoformat(d)
        co = ci + dt.timedelta(days=1)
        url = (f"https://tw.trip.com/hotels/list?city={cid}&checkin={ci:%Y/%m/%d}&checkout={co:%Y/%m/%d}"
               f"&adult=2&crn=1&curr=TWD{STAR_FILTER}")
        st, html = get(url)
        cn = re.search(r'\\?"cityName\\?":\\?"([^"\\]+)', html)
        return job, st, parse(html), (cn.group(1) if cn else "?")

    with ThreadPoolExecutor(3) as ex:
        results = list(ex.map(fetch, jobs))
    by_city = {}
    for (cid, d), st, items, cn in results:
        cname = CITIES[cid]
        if d == dates(today)[0]:
            log(f"{cname}（Trip.com 顯示：{cn}）")
        seen_total += len(items)
        if st != 200 or not items:
            log(f"  {cname} {d}：HTTP {st}，{len(items)} 家")
        run = by_city.setdefault(cid, {})
        for hid, name, price, bed in items:
            run.setdefault((hid, bed), {})[d] = price
            h = H.setdefault(hid, {"n": name, "c": cname, "p": {}})
            h["n"], h["c"] = name, cname
            key = f"{d}|{bed}"
            hist = h["p"].get(key, [])
            why = None
            if len(hist) >= 3:
                med = statistics.median(hist)
                if price <= med * DROP_HIST:
                    why = f"同房型（{bed}）這天平常 TWD{med:,.0f}，現在便宜 {1 - price / med:.0%}"
                if 0.08 <= price / med <= 0.12:
                    why = f"約是同房型平常 TWD{med:,.0f} 的 1/10，疑似少打一個 0"
            if why:
                alerts.append((hid, name, cname, d, price, why))
            hist.append(price)
            h["p"][key] = hist[-KEEP:]
    # 同一輪不同日期互相比較
    for cid, run in by_city.items():
        cname = CITIES[cid]
        for (hid, bed), byd in run.items():
            if len(byd) < 3:
                continue
            for d, price in byd.items():
                others = [v for k, v in byd.items() if k != d]
                low = min(others)
                # 同一種床型，要比其他所有日期中最便宜的還便宜 65% 以上，才當成異常
                if price <= low * DROP_DATES and not any(a[0] == hid and a[3] == d for a in alerts):
                    alerts.append((hid, H[hid]["n"], cname, d, price, f"同房型（{bed}）其他日期最便宜也要 TWD{low:,.0f}，這天便宜 {1 - price / low:.0%}"))
    if seen_total == 0:
        log("⚠ 這次一家飯店都沒讀到，可能是 Trip.com 改版或擋住了")
    # 通知（24 小時內同一家同一天不重複）
    A = D.setdefault("alerted", {})
    for k in [k for k, t in A.items() if time.time() - t > 86400]:
        del A[k]
    for hid, name, cname, d, price, why in alerts:
        k = f"{hid}-{d}"
        if k in A:
            continue
        ci = dt.date.fromisoformat(d)
        click = (f"https://tw.trip.com/hotels/detail/?hotelId={hid}&checkIn={d}"
                 f"&checkOut={(ci + dt.timedelta(days=1)).isoformat()}&adult=2&crn=1&curr=TWD")
        title = f"🚨 疑似 bug 價 {cname} TWD{price:,.0f}（總價）"
        msg = f"{name}\n入住 {ci.month}/{ci.day}（1 晚，2 位大人總價，四星以上）\n{why}\n點通知開 Trip.com 確認"
        log("異常：", title, "|", msg.replace("\n", " / "))
        if dry or ntfy(title, msg, click):
            A[k] = time.time()
    if not alerts:
        log("沒有異常價格")
    # 太久沒出現的飯店刪掉，控制檔案大小
    for hid in [h for h, v in H.items() if not v["p"]]:
        del H[hid]
    D["lastRun"] = int(time.time() * 1000)
    D["seen"] = seen_total
    if not dry:
        os.makedirs(os.path.dirname(DATA), exist_ok=True)
        with open(DATA, "w", encoding="utf-8") as f:
            json.dump(D, f, ensure_ascii=False, separators=(",", ":"))
    log(f"完成：共讀到 {seen_total} 筆飯店價格，追蹤中 {len(H)} 家")


if __name__ == "__main__":
    main()
