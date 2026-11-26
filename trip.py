"""Trip.com 飯店 bug 價監控（GitHub 雲端執行）

每次執行：
1. 查每個城市、每個入住日期的飯店列表（Trip.com 台灣站，新台幣）
2. 記下每家飯店在每個日期的價格歷史（data/trip.json）
3. 價格異常就發 ntfy 到 bug 價 topic：
   - 比這家飯店同一日期自己的歷史中位數低 60% 以上（至少要有 3 筆紀錄）
   - 比這家飯店這一輪其他日期的中位數低 70% 以上（第一次看到也能抓）
   - 價格約是平常的 1/10（疑似少打一個 0）
4. 同一家飯店同一個日期 24 小時內只通知一次

設定在檔案最上面的 CITIES、DAYS_AHEAD、FIXED_DATES。只用 Python 標準函式庫。
"""
import datetime as dt
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

CITIES = {617: "台北", 720: "高雄", 228: "東京", 219: "大阪"}
DAYS_AHEAD = [7, 14, 30]                     # 幾天後入住（住 1 晚）
FIXED_DATES = ["2026-12-24", "2026-12-31", "2027-02-04", "2027-02-27", "2027-04-02"]  # 連假前一天
DATA = os.environ.get("TRIP_FILE", "data/trip.json")
NTFY_TOPIC = os.environ.get("NTFY_BUG_TOPIC", "").strip()
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
KEEP = 30            # 每家飯店每個日期最多保留幾筆價格
DROP_HIST = 0.40     # 低於自己歷史中位數的 40%（便宜 60%）
DROP_DATES = 0.30    # 低於其他日期中位數的 30%（便宜 70%）
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


def parse(html):
    """從 Next.js 的資料片段取出每家飯店：編號、名稱、價格（新台幣）。"""
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
        block = text[m.start():m.start() + 6000]
        nm = re.search(r'"nameInfo":\{"name":"((?:[^"\\]|\\.)*)"', block)
        pr = re.search(r'"price":(\d+(?:\.\d+)?),"currency":"TWD"', block)
        if not (nm and pr):
            continue
        seen.add(hid)
        try:
            name = json.loads('"' + nm.group(1) + '"')
        except Exception:
            name = nm.group(1)
        out.append((hid, name.strip("​ "), float(pr.group(1))))
    return out


def dates(today):
    ds = [(today + dt.timedelta(days=n)).isoformat() for n in DAYS_AHEAD]
    ds += [d for d in FIXED_DATES if d > today.isoformat()]
    return sorted(set(ds))


def ntfy(title, msg, click):
    if not NTFY_TOPIC:
        log("（還沒設定 NTFY_BUG_TOPIC，不發通知）", title)
        return False
    body = json.dumps({"topic": NTFY_TOPIC, "title": title, "message": msg, "priority": 5,
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
        for d in [d for d in h["p"] if d <= today.isoformat()]:
            del h["p"][d]
    alerts, seen_total = [], 0
    for cid, cname in CITIES.items():
        run = {}  # hid -> {date: price}
        for d in dates(today):
            ci = dt.date.fromisoformat(d)
            co = ci + dt.timedelta(days=1)
            url = (f"https://tw.trip.com/hotels/list?city={cid}&checkin={ci:%Y/%m/%d}&checkout={co:%Y/%m/%d}"
                   f"&adult=2&crn=1&curr=TWD")
            st, html = get(url)
            items = parse(html)
            seen_total += len(items)
            log(f"{cname} {d}：HTTP {st}，{len(items)} 家")
            for hid, name, price in items:
                run.setdefault(hid, {})[d] = price
                h = H.setdefault(hid, {"n": name, "c": cname, "p": {}})
                h["n"] = name
                hist = h["p"].get(d, [])
                why = None
                if len(hist) >= 3:
                    med = statistics.median(hist)
                    if price <= med * DROP_HIST:
                        why = f"比這天平常的 TWD{med:,.0f} 便宜 {1 - price / med:.0%}"
                    if 0.08 <= price / med <= 0.12:
                        why = f"約是平常 TWD{med:,.0f} 的 1/10，疑似少打一個 0"
                if why:
                    alerts.append((hid, name, cname, d, price, why))
                hist.append(price)
                h["p"][d] = hist[-KEEP:]
            time.sleep(1.5)
        # 同一輪不同日期互相比較
        for hid, byd in run.items():
            if len(byd) < 3:
                continue
            for d, price in byd.items():
                others = [v for k, v in byd.items() if k != d]
                med = statistics.median(others)
                if price <= med * DROP_DATES and not any(a[0] == hid and a[3] == d for a in alerts):
                    alerts.append((hid, H[hid]["n"], cname, d, price, f"比同一家其他日期的 TWD{med:,.0f} 便宜 {1 - price / med:.0%}"))
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
        title = f"🚨 疑似 bug 價 {cname} TWD{price:,.0f}"
        msg = f"{name}\n入住 {ci.month}/{ci.day}（1 晚）\n{why}\n點通知開 Trip.com 確認"
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
