"""LINE 貼圖愛心監控（雲端版）

每次執行：
1. 讀 data/hearts.json（之前的紀錄）
2. 看作者頁有沒有新作品，有就加入
3. 查每一組作品目前的愛心數，只記下有變化的
4. 每小時查一次 LINE STORE 熱門個人原創排行（前 1,800 名）
5. 寫回 data/hearts.json

只用 Python 標準函式庫。
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser

AUTHOR = "5974419"
DATA = os.environ.get("HEARTS_FILE", "data/hearts.json")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
BASE = "https://store.line.me"
RANK_EVERY_MS = 55 * 60 * 1000   # 排行每小時查一次
# GitHub 的伺服器在美國，讀到的是美國的排行，跟台灣不同，所以先關掉（設 RANKS=1 才會查）
RANK_ENABLED = os.environ.get("RANKS") == "1"
CLOUD_START = 1795658000000      # 雲端版開始的時間（2026/11/26 10:00 左右）
RANK_DEPTH = 1800                # 排行查到第幾名
RANK_KEEP = 300                  # 排行紀錄最多保留幾筆
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
PAGE_URL = "https://fs7807787-ui.github.io/cloud-watch/"
Q = "query W($i:ID!,$t:ShopProductType!){wishStatus(input:{id:$i,productType:$t}){wishCount}}"
RANK_URLS = {
    "S": ["/stickershop/showcase/top_creators/zh-Hant?page={p}"],
    "E": ["/emojishop/showcase/top_creators/zh-Hant?page={p}"],
}


def log(*a):
    print(*a, flush=True)


def http(path, body=None, headers=None, tries=3):
    h = {"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"}
    h.update(headers or {})
    last = None
    for i in range(tries):
        req = urllib.request.Request(BASE + path, data=body, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, ""
            last = (e.code, "")
        except Exception as e:  # 網路問題，稍等再試
            last = (0, repr(e))
        time.sleep(2 * (i + 1))
    return last


class Items(HTMLParser):
    """從作品列表頁找出每組作品的類型、編號、名稱（照網頁順序）。"""

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
    st, html = http(path)
    if st != 200:
        return st, []
    p = Items()
    p.feed(html)
    out, seen = [], set()
    for kind, pid, name in p.items:
        if pid not in seen:
            seen.add(pid)
            out.append((kind, pid, name))
    if not out:  # 萬一網頁結構變了，至少抓連結
        for kind, pid in re.findall(r'href="[^"]*?/(sticker|emoji)shop/product/([^/?#"]+)', html):
            if pid not in seen:
                seen.add(pid)
                out.append((kind, pid, ""))
    return st, out


def key(kind, pid):
    return ("s" if kind == "sticker" else "e") + str(pid)[:12]


def pid_of(s):
    m = re.search(r"/(sticker|emoji)shop/product/([^/?#]+)", s.get("url", ""))
    return (m.group(1), m.group(2)) if m else None


def wish(kind, pid):
    body = json.dumps({"query": Q, "variables": {"i": pid, "t": "STICKER" if kind == "sticker" else "EMOJI"}}).encode()
    st, txt = http("/graphql", body, {"Content-Type": "application/json", "Origin": BASE,
                                      "Referer": f"{BASE}/stickershop/author/{AUTHOR}/zh-Hant"})
    try:
        return int(json.loads(txt)["data"]["wishStatus"]["wishCount"])
    except Exception:
        return None


def ntfy(title, message, priority=3):
    """用 JSON 發 ntfy（中文標題不會出問題），確認真的送到才算成功；失敗會重試。"""
    if not NTFY_TOPIC:
        log("還沒設定 NTFY_TOPIC，這次不發通知")
        return False
    body = json.dumps({"topic": NTFY_TOPIC, "title": title, "message": message,
                       "priority": priority, "click": PAGE_URL}).encode()
    for i in range(4):
        try:
            req = urllib.request.Request("https://ntfy.sh/", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                if json.loads(r.read().decode()).get("id"):
                    log("通知已送出：", title)
                    return True
        except urllib.error.HTTPError as e:
            log(f"ntfy 回應 HTTP {e.code}，稍後重試")
        except Exception as e:
            log("ntfy 連線失敗：", repr(e))
        time.sleep(5 * (i + 1))
    return False


def tw_midnight_ms(now):
    """台灣時間今天 00:00 的時間戳（毫秒）。"""
    day = (now // 1000 + 8 * 3600) // 86400
    return (day * 86400 - 8 * 3600) * 1000


def heart_message(S, before, after, now):
    """照原本電腦版的格式：標題「♥ +N　總共 X」，內容逐組列出，最後一行今天累計。"""
    names = {s["id"]: s["name"] for s in S["sets"]}
    diffs = sorted(((k, after[k] - before[k], after[k]) for k in after
                    if k in before and after[k] != before[k]), key=lambda x: -x[1])
    if not diffs:
        return None
    total = sum(after.values())
    n = sum(d for _, d, _ in diffs)
    snaps = sorted(S["snaps"], key=lambda x: x["t"])
    base = {}
    for sn in snaps:
        if sn["t"] < tw_midnight_ms(now):
            base.update(sn["c"])
    today = total - sum(base.values()) if base else n
    sign = lambda d: f"+{d}" if d >= 0 else f"−{-d}"
    title = f"♥ {sign(n)}　總共 {total:,}"
    lines = [f"{names.get(k, k)}　{sign(d)}（共 {v:,}）" for k, d, v in diffs[:12]]
    if len(diffs) > 12:
        lines.append(f"……另外 {len(diffs) - 12} 組也有變化")
    lines.append(f"—— 今天累計 {sign(today)} ♥")
    return title, "\n".join(lines)


def carried(snaps):
    acc = {}
    for s in sorted(snaps, key=lambda x: x["t"]):
        acc.update(s["c"])
    return acc


def compact_old(S, now):
    """30 天以前的紀錄，每天合併成一筆。"""
    cutoff = now - 30 * 86400000
    snaps = sorted(S["snaps"], key=lambda x: x["t"])
    if not snaps or snaps[0]["t"] >= cutoff:
        return
    out, acc, day = [], None, None
    for sn in snaps:
        if sn["t"] >= cutoff:
            if acc:
                out.append(acc)
                acc = None
            out.append(sn)
            continue
        d = time.strftime("%Y-%m-%d", time.gmtime(sn["t"] / 1000 + 8 * 3600))
        if acc and d == day:
            acc["c"].update(sn["c"])
            acc["t"] = sn["t"]
        else:
            if acc:
                out.append(acc)
            day, acc = d, {"t": sn["t"], "c": dict(sn["c"])}
    if acc:
        out.append(acc)
    S["snaps"] = out


def check_ranks(S, now, ids):
    last = (S.get("ranks") or [{}])[-1].get("t", 0)
    if now - last < RANK_EVERY_MS and os.environ.get("FORCE_RANK") != "1":
        return "排行：這次不用查"
    r, depth, notes = {}, {}, []
    for t, urls in RANK_URLS.items():
        pos, got = 0, False
        for u in urls:
            seen = set()
            for p in range(1, RANK_DEPTH // 36 + 2):
                st, items = list_page(u.format(p=p))
                if st != 200 or not items:
                    if p == 1:
                        notes.append(f"{t} {u} 第 1 頁：HTTP {st}，{len(items)} 組")
                    break
                for kind, pid, _ in items:
                    if pid in seen:
                        continue
                    seen.add(pid)
                    pos += 1
                    k = key(kind, pid)
                    if k in ids and k not in r:
                        r[k] = pos
                if pos >= RANK_DEPTH:
                    break
                time.sleep(0.4)
            if pos:
                got = True
                break
        depth[t] = min(pos, RANK_DEPTH)
        if not got:
            notes.append(f"{t} 排行讀不到")
    if not any(depth.values()):
        S.setdefault("cloud", {})["rankError"] = "；".join(notes)
        return "排行：讀不到（" + "；".join(notes) + "）"
    S.setdefault("ranks", []).append({"t": now, "depth": depth, "r": r})
    if len(S["ranks"]) > RANK_KEEP:
        S["ranks"] = S["ranks"][-RANK_KEEP:]
    S.setdefault("cloud", {}).pop("rankError", None)
    return f"排行：貼圖查到 {depth.get('S', 0)} 名、表情貼 {depth.get('E', 0)} 名，你的作品有 {len(r)} 組在榜上：" + \
        "、".join(f"{k} 第{v}名" for k, v in sorted(r.items(), key=lambda x: x[1]))


TW_RANKS = os.environ.get("TW_RANKS_FILE", "data/ranks-phone.json")
TOP = 1000


def merge_tw_ranks(S, now):
    """讀 iPhone 存的台灣排行（ranks 分支 ranks-phone.json），加進紀錄；進出前 1,000 名就發通知。"""
    cl = S.setdefault("cloud", {})
    try:
        with open(TW_RANKS, encoding="utf-8") as f:
            rec = json.load(f)
    except Exception:
        rec = None
    ranks = S.setdefault("ranks", [])
    last = ranks[-1] if ranks else None
    # 台灣排行還在確認是不是讀對排行頁，確認前不採用、不發通知（設 TW_RANKS_OK=1 才採用）
    if os.environ.get("TW_RANKS_OK") != "1":
        rec = None
    if rec and rec.get("r") is not None and (not last or rec["t"] > last["t"]):
        ranks.append({"t": rec["t"], "depth": rec.get("depth", {}), "r": rec["r"], "src": "phone"})
        if len(ranks) > 300:
            del ranks[:len(ranks) - 300]
        log(f"加入台灣排行（{len(rec['r'])} 組在榜上）")
        if last:
            names = {x["id"]: x["name"] for x in S["sets"]}
            p0 = {k: v for k, v in last["r"].items() if v <= TOP}
            p1 = {k: v for k, v in rec["r"].items() if v <= TOP}
            lines = [f"⬆ 進入前 {TOP}：{names.get(k, k)}（第 {v} 名）" for k, v in sorted(p1.items(), key=lambda x: x[1]) if k not in p0]
            lines += [f"⬇ 掉出前 {TOP}：{names.get(k, k)}" for k in p0 if k not in p1]
            if lines:
                pend = cl.setdefault("pending", [])
                ok = ntfy("🏆 人氣排行變動", "\n".join(lines))
                if not ok and NTFY_TOPIC:
                    pend.append(["🏆 人氣排行變動", "\n".join(lines)])
    tw = [x for x in ranks if x.get("src") == "phone"]
    if not tw:
        cl["rankError"] = "雲端主機被 LINE 當成海外連線，台灣排行改由 iPhone 查（設定中）；下面顯示的是 11/26 早上以前電腦記錄的名次。"
    elif now - tw[-1]["t"] > 6 * 3600 * 1000:
        cl["rankError"] = "iPhone 超過 6 小時沒有查排行（半夜或手機沒網路時會暫停），下面是最後一次的名次。"
    else:
        cl.pop("rankError", None)


def main():
    with open(DATA, encoding="utf-8") as f:
        S = json.load(f)
    now = int(time.time() * 1000)
    sets = {s["id"]: s for s in S["sets"]}

    # 1. 作者頁：找新作品、更新名稱
    listed = []
    for p in range(1, 20):
        st, items = list_page(f"/stickershop/author/{AUTHOR}/zh-Hant?page={p}")
        if not items:
            break
        listed += items
        time.sleep(0.3)
    added = []
    for kind, pid, name in listed:
        k = key(kind, pid)
        if k not in sets:
            s = {"id": k, "name": name or pid, "type": "貼圖" if kind == "sticker" else "表情貼",
                 "url": f"{BASE}/{kind}shop/product/{pid}/zh-Hant"}
            S["sets"].append(s)
            sets[k] = s
            added.append(s["name"])
        elif name:
            sets[k]["name"] = name
    listed_keys = {key(k, p) for k, p, _ in listed}
    log(f"作者頁列出 {len(listed)} 組；新作品 {len(added)} 組 {added}")

    # 2. 查每一組的愛心數
    targets = [(s["id"], pid_of(s)) for s in S["sets"]]
    targets = [(k, x) for k, x in targets if x]
    with ThreadPoolExecutor(6) as ex:
        vals = list(ex.map(lambda t: wish(*t[1]), targets))
    cur = carried(S["snaps"])
    c, bad = {}, []
    for (k, _), v in zip(targets, vals):
        if v is None:
            bad.append(sets[k]["name"])
            continue
        if cur.get(k) != v:
            c[k] = v
    ok = len(targets) - len(bad)
    if ok == 0:
        S.setdefault("cloud", {}).update({"lastRun": now, "ok": 0, "error": "全部作品都讀不到愛心數"})
        save(S)
        log("全部作品都讀不到愛心數")
        sys.exit(1)
    before = dict(cur)
    if c:
        S["snaps"].append({"t": now, "c": c})
    compact_old(S, now)
    S["lastCheck"] = S["lastBeat"] = now
    total = sum(carried(S["snaps"]).values())
    hidden = [sets[k]["name"] for k in sets if k not in listed_keys] if listed else S.get("cloud", {}).get("notListed", [])
    S["cloud"] = dict(S.get("cloud", {}), lastRun=now, ok=ok, failed=bad, notListed=hidden, error="")
    log(f"讀到 {ok}/{len(targets)} 組，{len(c)} 組有變化，總愛心 {total}")
    if bad:
        log("讀不到：", bad)
    log(f"沒出現在作者頁的 {len(hidden)} 組：", hidden) if listed else log("作者頁這次讀不到（不影響愛心數）")

    # 通知：先補發上次沒送出去的，再發這次的
    cl = S.setdefault("cloud", {})
    pending = cl.get("pending") or []
    msg = heart_message(S, before, carried(S["snaps"]), now) if c else None
    if msg:
        pending.append(list(msg))
    if os.environ.get("TEST_NTFY") == "1":
        pending.append(["✅ 雲端愛心通知測試", f"雲端版已經可以發通知了。目前總愛心 {total:,}，讀到 {ok} 組。\n點這則通知會打開新的監控網頁。"])
    left = []
    for i, (t_, m_) in enumerate(pending[-10:]):
        if not ntfy(t_, m_):
            left = pending[-10:][i:]
            break
        time.sleep(1)
    cl["pending"] = left if NTFY_TOPIC else []
    if left and NTFY_TOPIC:
        log(f"有 {len(left)} 則通知沒送出，下次再送")

    # 3. 排行（目前暫停：雲端讀到的是美國排行）
    # 刪掉雲端第一次執行時存下的錯誤排行紀錄（美國排行，裡面沒有你的作品）
    S["ranks"] = [x for x in S.get("ranks", []) if x["t"] < CLOUD_START or x.get("src") == "phone"]
    if RANK_ENABLED:
        try:
            log(check_ranks(S, now, set(sets)))
        except Exception as e:
            log("排行發生錯誤：", repr(e))
    else:
        merge_tw_ranks(S, now)
    save(S)


def save(S):
    tmp = DATA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(S, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, DATA)


if __name__ == "__main__":
    main()
