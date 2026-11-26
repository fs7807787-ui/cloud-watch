"""iPhone（a-Shell）用：從台灣的網路查 LINE 熱門個人原創排行，存回 GitHub。

第一次（在 a-Shell 裡手動執行）：
    python3 rank_phone.py --setup
  會請你貼上 GitHub token（只存在這支手機的 a-Shell 裡），然後試跑一次並顯示結果。

之後由「捷徑」定時執行：
    python3 rank_phone.py

其他：
    python3 rank_phone.py --test     只檢查、不存（看地區、排行、特斯拉）

只用 Python 標準函式庫。
"""
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser

REPO = "fs7807787-ui/cloud-watch"
TOKEN_FILE = os.path.expanduser("~/Documents/.cloudwatch_token")
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
BASE = "https://store.line.me"
PAGES = 28   # 每頁 36 組，28 頁 ≈ 前 1,000 名
RANK_URLS = {
    "S": "/stickershop/showcase/top_creators/zh-Hant?page={p}",
    "E": "/emojishop/showcase/top_creators/zh-Hant?page={p}",
}


def log(*a):
    print(*a, flush=True)


def get(url, tries=3, headers=None):
    h = {"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"}
    h.update(headers or {})
    last = (0, "")
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return e.code, ""
            last = (e.code, "")
        except Exception as e:
            last = (0, repr(e))
        time.sleep(2 * (i + 1))
    return last


class Items(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.items, self.href = [], None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            m = re.search(r"/(sticker|emoji)shop/product/([^/?#\"]+)", dict(attrs).get("href") or "")
            if m and (m.group(1), m.group(2)) not in self.items:
                self.items.append((m.group(1), m.group(2)))


def page_items(path):
    st, html = get(BASE + path)
    p = Items()
    p.feed(html)
    return st, p.items


def key(kind, pid):
    return ("s" if kind == "sticker" else "e") + str(pid)[:12]


def region_check():
    st, h = get(BASE + "/stickershop/product/37847748/zh-Hant")
    cur = sorted(set(re.findall(r"(NT\$|US\$|TWD|USD)", h)))
    tw = any(c in ("NT$", "TWD") for c in cur)
    log("LINE 看到的地區：" + ("台灣（價格顯示 NT$）✅" if tw else "不是台灣（%s）⚠" % (cur or "看不出來")))
    return tw


def ranks(ids):
    r, depth = {}, {}
    for t, url in RANK_URLS.items():
        with ThreadPoolExecutor(4) as ex:
            pages = list(ex.map(lambda p: page_items(url.format(p=p)), range(1, PAGES + 1)))
        pos, seen = 0, set()
        for st, items in pages:
            if not items:
                break
            for kind, pid in items:
                if pid in seen:
                    continue
                seen.add(pid)
                pos += 1
                k = key(kind, pid)
                if k in ids and k not in r:
                    r[k] = pos
        depth[t] = pos
    return r, depth


def github(token, method, path, body=None):
    req = urllib.request.Request(
        "https://api.github.com/repos/" + REPO + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "line-rank-phone"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def save(token, rec):
    st, _ = github(token, "GET", "/git/ref/heads/ranks")
    if st == 404:
        st, main = github(token, "GET", "/git/ref/heads/main")
        github(token, "POST", "/git/refs", {"ref": "refs/heads/ranks", "sha": main["object"]["sha"]})
    st, cur = github(token, "GET", "/contents/ranks-phone.json?ref=ranks")
    body = {"message": "手機台灣排行 " + time.strftime("%Y/%m/%d %H:%M"),
            "content": base64.b64encode(json.dumps(rec, ensure_ascii=False).encode()).decode(),
            "branch": "ranks"}
    if st == 200 and cur.get("sha"):
        body["sha"] = cur["sha"]
    st, res = github(token, "PUT", "/contents/ranks-phone.json", body)
    if st in (200, 201):
        return True
    log("存到 GitHub 失敗：HTTP %s %s" % (st, str(res.get("message", ""))[:120]))
    return False


def tesla():
    q = {"query": {"model": "m3", "condition": "new", "options": {}, "arrangeby": "Price", "order": "asc",
                   "market": "TW", "language": "zh", "super_region": "asia pacific"},
         "offset": 0, "count": 24, "outsideOffset": 0, "outsideSearch": False}
    import urllib.parse
    url = "https://www.tesla.com/inventory/api/v4/inventory-results?query=" + urllib.parse.quote(json.dumps(q, separators=(",", ":")))
    st, txt = get(url, tries=1, headers={"Accept": "application/json"})
    try:
        d = json.loads(txt)
        res = d.get("results") or []
        if isinstance(res, dict):
            res = res.get("exact") or []
        prices = [c.get("InventoryPrice") or c.get("Price") or c.get("PurchasePrice") for c in res[:3]]
        log("特斯拉測試：讀得到 ✅（Model 3 現車 %s 台，最低價 %s）" % (d.get("total_matches_found", len(res)), prices))
    except Exception:
        st2, html = get("https://www.tesla.com/zh_TW/inventory/new/m3", tries=1)
        log("特斯拉測試：資料介面 HTTP %s、網頁 HTTP %s %s" % (st, st2, "（被擋）" if st2 == 403 else ""))


def main():
    args = sys.argv[1:]
    if "--setup" in args:
        tok = input("貼上 GitHub token（github_pat_ 開頭）後按 Enter：").strip()
        m = re.search(r"github_pat_[A-Za-z0-9_]{82}", tok)
        if not m:
            log("token 格式不對，請重新執行 --setup")
            return
        with open(TOKEN_FILE, "w") as f:
            f.write(m.group(0))
        log("已存好 token（共 %d 個字）。接著試跑一次…\n" % len(m.group(0)))
    test = "--test" in args or "--setup" in args
    token = open(TOKEN_FILE).read().strip() if os.path.exists(TOKEN_FILE) else ""
    if not token and "--test" not in args:
        log("還沒設定 token，請先執行：python3 rank_phone.py --setup")
        return

    t0 = time.time()
    tw = region_check()
    st, raw = get("https://raw.githubusercontent.com/%s/data/hearts.json?t=%d" % (REPO, int(time.time())))
    S = json.loads(raw)
    names = {s["id"]: s["name"] for s in S["sets"]}
    r, depth = ranks(set(names))
    log("排行：貼圖查到 %d 名、表情貼查到 %d 名（%d 秒）" % (depth.get("S", 0), depth.get("E", 0), time.time() - t0))
    for k, v in sorted(r.items(), key=lambda x: x[1]):
        log("  第 %d 名：%s（%s）" % (v, names[k], "貼圖" if k[0] == "s" else "表情貼"))
    if not r:
        log("  你的作品都不在前 %d 名" % (PAGES * 36))
    if test:
        tesla()
    if not any(depth.values()):
        log("排行讀不到，這次不存")
        return
    if not tw:
        log("LINE 沒有把這支手機當成台灣，這次不存（請確認沒有開 VPN）")
        return
    if token and save(token, {"t": int(time.time() * 1000), "depth": depth, "r": r, "src": "phone"}):
        log("✅ 已存到 GitHub，雲端網頁 10 分鐘內會更新")


if __name__ == "__main__":
    main()
