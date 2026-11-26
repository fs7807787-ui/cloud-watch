"""PTT 優惠情報監控（GitHub 雲端執行，約每 10 分鐘）

讀 PTT 官方提供的 Atom 訂閱（網站允許程式讀取），新文章標題或內容有 bug 價相關關鍵字就發 ntfy。
使用者規則：價差低於 NT$3,000 的不通知；看不出價差的照樣通知，但標明「價差看不出來」。
第一次執行只記下現有文章，不發通知（避免一次湧入）。只用 Python 標準函式庫。
"""
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser

BOARDS = {"Lifeismoney": "省錢板", "Japan_Travel": "日旅板", "Tour-Agency": "國旅板"}
KEYWORDS = {"BUG": r"bug", "標錯": r"標錯", "錯價": r"錯價", "誤標": r"誤標", "價格錯誤": r"價格錯誤",
            "0元": r"(?<![\d.,])0\s?元", "1元": r"(?<![\d.,])1\s?元", "快搶": r"快搶", "神價": r"神價",
            "特斯拉": r"特斯拉|tesla"}
MIN_DIFF = 3000
DATA = os.environ.get("PTT_FILE", "data/ptt.json")
NTFY_TOPIC = os.environ.get("NTFY_BUG_TOPIC", "").strip()
UA = "Mozilla/5.0 (compatible; personal-deal-alert/1.0)"
RP = urllib.robotparser.RobotFileParser("https://www.ptt.cc/robots.txt")


def log(*a):
    print(*a, flush=True)


def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Cookie": "over18=1"}), timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        log("讀取失敗", url, repr(e))
        return ""


def entries(board):
    x = get(f"https://www.ptt.cc/atom/{board}.xml")
    out = []
    for e in re.findall(r"<entry>(.*?)</entry>", x, re.S):
        title = html.unescape(re.sub(r"<[^>]+>", "", (re.search(r"<title[^>]*>(.*?)</title>", e, re.S) or [None, ""])[1])).strip()
        link = (re.search(r'<link[^>]*href="([^"]+)"', e) or [None, ""])[1]
        body = html.unescape(re.sub(r"<[^>]+>", " ", html.unescape((re.search(r"<content[^>]*>(.*?)</content>", e, re.S) or [None, ""])[1])))
        if link:
            out.append((link, title, body))
    return out


PRICE = re.compile(r"(?:NT\$|NTD|TWD|\$|＄)\s?([\d,]{2,9})(?!\d)|([\d,]{2,9})\s?(?:元|塊)")


def prices(text):
    vals = []
    for a, b in PRICE.findall(text):
        v = (a or b).replace(",", "")
        if v.isdigit():
            n = int(v)
            if 1 <= n <= 5_000_000:
                vals.append(n)
    return vals


def price_diff(title, body, link):
    """回傳（價差, 說明）。找不到兩個以上價格時，讀文章頁再找一次（網站規則允許才讀）。"""
    vals = prices(title + " " + body)
    if len(vals) < 2 and RP.can_fetch("*", link):
        page = get(link)
        main = re.search(r'<div id="main-content"[^>]*>(.*?)<span class="f2">', page, re.S)
        text = html.unescape(re.sub(r"<[^>]+>", " ", main.group(1) if main else page))
        vals = prices(text[:4000])
    if len(vals) < 2:
        return None, "價差看不出來"
    hi, lo = max(vals), min(vals)
    return hi - lo, f"約 ${hi:,} → ${lo:,}，價差 ${hi - lo:,}"


def ntfy(title, msg, click, prio):
    if not NTFY_TOPIC:
        log("（還沒設定 NTFY_BUG_TOPIC）", title)
        return False
    body = json.dumps({"topic": NTFY_TOPIC, "title": title, "message": msg, "priority": prio,
                       "tags": ["loudspeaker"], "click": click}).encode()
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
        RP.read()
    except Exception:
        pass
    try:
        with open(DATA, encoding="utf-8") as f:
            D = json.load(f)
    except Exception:
        D = {"seen": [], "first": True}
    seen = set(D.get("seen", []))
    first = D.get("first", False) and not dry
    sent = 0
    for board, bname in BOARDS.items():
        if not RP.can_fetch("*", f"https://www.ptt.cc/atom/{board}.xml"):
            log(f"{bname}：網站規則不允許，跳過")
            continue
        es = entries(board)
        log(f"{bname}：{len(es)} 篇")
        for link, title, body in es:
            if link in seen:
                continue
            seen.add(link)
            if first:
                continue
            text = (title + " " + body).lower()
            hit = [k for k, pat in KEYWORDS.items() if re.search(pat, text)]
            if not hit or title.startswith("Re:"):
                continue
            diff, desc = price_diff(title, body, link)
            if diff is not None and diff < MIN_DIFF:
                log(f"  略過（價差 {diff} < {MIN_DIFF}）：{title}")
                continue
            prio = 4 if diff is not None else 3
            msg = f"{title}\n{desc}\n關鍵字：{'、'.join(hit)}\n點通知開 PTT 文章"
            log("  命中：", title, "|", desc)
            if not dry:
                ok = ntfy(f"📢 PTT {bname}：可能有 bug 價", msg, link, prio)
                sent += ok
            time.sleep(1)
    D["seen"] = list(seen)[-3000:]
    D["first"] = False
    D["lastRun"] = int(time.time() * 1000)
    if first:
        log(f"第一次執行：記下 {len(seen)} 篇現有文章，不發通知")
    if not dry:
        os.makedirs(os.path.dirname(DATA), exist_ok=True)
        with open(DATA, "w", encoding="utf-8") as f:
            json.dump(D, f, ensure_ascii=False)
    log(f"完成，發出 {sent} 則通知")


if __name__ == "__main__":
    main()
