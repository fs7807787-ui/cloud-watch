"""LINE STORE 台灣排行（在 Google Cloud 台灣機房執行）

每小時一次：
1. 從 GitHub 讀你的作品清單（data 分支的 hearts.json）
2. 查 LINE STORE 熱門個人原創排行（貼圖、表情貼各前 1,800 名）
3. 把你的作品名次寫到 GitHub 的 ranks 分支（ranks.json）
   GitHub 那邊每 10 分鐘的愛心記錄會讀它、加進網頁、有進出前 1,000 名就發通知

只用 Python 標準函式庫。需要環境變數 GH_TOKEN（只能寫 cloud-watch 的 Contents 權限）。
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser

REPO = os.environ.get("REPO", "fs7807787-ui/cloud-watch")
GH_TOKEN = os.environ.get("GH_TOKEN", "").strip()
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
BASE = "https://store.line.me"
DEPTH = 1800
RANK_URLS = {
    "S": "/stickershop/showcase/top_creators/zh-Hant?page={p}",
    "E": "/emojishop/showcase/top_creators/zh-Hant?page={p}",
}


def log(*a):
    print(*a, flush=True)


def get(url, tries=3):
    last = (0, "")
    for i in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, ""
            last = (e.code, "")
        except Exception as e:
            last = (0, repr(e))
        time.sleep(2 * (i + 1))
    return last


class Items(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items, self.href, self.grab, self.buf = [], None, False, ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            m = re.search(r"/(sticker|emoji)shop/product/([^/?#\"]+)", a["href"])
            self.href = (m.group(1), m.group(2)) if m else None
        if a.get("data-test") == "item-name" and self.href:
            self.grab, self.buf = True, ""

    def handle_data(self, d):
        if self.grab:
            self.buf += d

    def handle_endtag(self, tag):
        if self.grab and tag in ("p", "span", "div", "h3", "h4"):
            self.items.append((self.href[0], self.href[1], self.buf.strip()))
            self.grab = False
        if tag == "a":
            self.href = None


def list_page(path):
    st, html = get(BASE + path)
    if st != 200:
        return st, []
    p = Items()
    p.feed(html)
    out, seen = [], set()
    for kind, pid, name in p.items:
        if pid not in seen:
            seen.add(pid)
            out.append((kind, pid, name))
    if not out:
        for kind, pid in re.findall(r'href="[^"]*?/(sticker|emoji)shop/product/([^/?#"]+)', html):
            if pid not in seen:
                seen.add(pid)
                out.append((kind, pid, ""))
    return st, out


def key(kind, pid):
    return ("s" if kind == "sticker" else "e") + str(pid)[:12]


def github(method, path, body=None):
    req = urllib.request.Request(
        "https://api.github.com/repos/" + REPO + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + GH_TOKEN, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "line-rank"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def save_to_github(rec):
    st, ref = github("GET", "/git/ref/heads/ranks")
    if st == 404:
        st, main = github("GET", "/git/ref/heads/main")
        st, _ = github("POST", "/git/refs", {"ref": "refs/heads/ranks", "sha": main["object"]["sha"]})
        log("建立 ranks 分支：HTTP", st)
    st, cur = github("GET", "/contents/ranks.json?ref=ranks")
    body = {"message": "台灣排行 " + time.strftime("%Y/%m/%d %H:%M", time.gmtime(rec["t"] / 1000 + 8 * 3600)),
            "content": base64.b64encode(json.dumps(rec, ensure_ascii=False).encode()).decode(),
            "branch": "ranks"}
    if st == 200 and cur.get("sha"):
        body["sha"] = cur["sha"]
    st, res = github("PUT", "/contents/ranks.json", body)
    if st in (200, 201):
        log("已存到 GitHub（ranks 分支）")
        return True
    log("存到 GitHub 失敗：HTTP", st, str(res)[:300])
    return False


def tesla_probe():
    for url in ("https://www.tesla.com/zh_TW/inventory/new/m3",):
        st, html = get(url, tries=1)
        blocked = "Access Denied" in html
        log(f"特斯拉測試：HTTP {st}，{'被擋（Access Denied）' if blocked else str(len(html)) + ' 字元'}")


def main():
    if not GH_TOKEN:
        raise SystemExit("沒有設定 GH_TOKEN")
    # 自己的連線位置（確認是從台灣連出去）
    st, ipinfo = get("https://ipinfo.io/json", tries=1)
    try:
        j = json.loads(ipinfo)
        log(f"這台主機的連線位置：{j.get('country')} {j.get('region')} {j.get('city')}（{j.get('org')}）")
    except Exception:
        log("查不到連線位置")

    st, raw = get(f"https://raw.githubusercontent.com/{REPO}/data/hearts.json?t={int(time.time())}")
    S = json.loads(raw)
    ids = {s["id"]: s["name"] for s in S["sets"]}
    log(f"你的作品：{len(ids)} 組")

    now = int(time.time() * 1000)
    r, depth = {}, {}
    for t, url in RANK_URLS.items():
        pos, seen = 0, set()
        for p in range(1, DEPTH // 36 + 2):
            st, items = list_page(url.format(p=p))
            if st != 200 or not items:
                if p == 1:
                    log(f"{t} 排行第 1 頁讀不到：HTTP {st}")
                break
            for kind, pid, _ in items:
                if pid in seen:
                    continue
                seen.add(pid)
                pos += 1
                k = key(kind, pid)
                if k in ids and k not in r:
                    r[k] = pos
            if pos >= DEPTH:
                break
            time.sleep(0.4)
        depth[t] = min(pos, DEPTH)
    log(f"排行：貼圖查到 {depth.get('S', 0)} 名、表情貼查到 {depth.get('E', 0)} 名")
    for k, v in sorted(r.items(), key=lambda x: x[1]):
        log(f"  第 {v} 名：{ids[k]}（{'貼圖' if k[0] == 's' else '表情貼'}）")
    if not r:
        log("  你的作品都不在榜上")
    if not any(depth.values()):
        raise SystemExit("排行讀不到，這次不存")
    save_to_github({"t": now, "depth": depth, "r": r, "src": "tw"})
    if os.environ.get("TESLA_TEST") == "1":
        tesla_probe()


if __name__ == "__main__":
    main()
