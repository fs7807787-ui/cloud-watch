"""把機票監控的 ntfy 通知轉寄成 email。

機票監控是另一個排程（Claude 定時任務）發的 ntfy，它自己沒辦法寄信，
所以這裡跟著每 10 分鐘的愛心記錄一起跑。
- 機票監控會發通知的時段（台灣時間 10、11、12、17、23 點）：持續連著 ntfy 約 9 分鐘，
  一收到新通知就馬上寄 email（和 ntfy 幾乎同時）。下一輪接著連，所以整個小時都有人在聽。
- 其他時間：只快速檢查一次有沒有漏掉的。
需要 secret：NTFY_FLIGHT_TOPIC（機票 topic 名稱），以及 mailer.py 的兩個 Gmail secret。
第一次執行只記下目前最新的一則，不寄舊通知。
"""
import datetime as dt
import json
import os
import socket
import time
import urllib.request

from mailer import send_mail

TOPIC = os.environ.get("NTFY_FLIGHT_TOPIC", "").strip()
DATA = "data/flightmail.json"
LIVE_HOURS = {10, 11, 12, 17, 23}   # 機票監控在這幾個小時的 :05 執行
LISTEN_SECONDS = int(os.environ.get("LISTEN_SECONDS", "540"))
TPE = dt.timezone(dt.timedelta(hours=8))


def log(*a):
    print(dt.datetime.now(TPE).strftime("%H:%M:%S"), *a, flush=True)


def save(D):
    D["sent"] = D.get("sent", [])[-300:]
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(D, f, ensure_ascii=False)


def forward(D, e):
    """寄出一則；成功回傳 True。"""
    if e.get("event") != "message" or e["id"] in D["sent"]:
        return True
    title = e.get("title") or "機票通知"
    if not send_mail(title, e.get("message", ""), e.get("click") or None, "打開機票通知紀錄（訂票、即時查價）"):
        return False
    D["sent"].append(e["id"])
    D["lastTime"] = max(int(D["lastTime"]), int(e["time"]))
    save(D)
    return True


def poll(D, since):
    url = f"https://ntfy.sh/{TOPIC}/json?poll=1&since={since}"
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "cloud-watch"}), timeout=30) as r:
                out = [json.loads(x) for x in r.read().decode("utf-8").splitlines() if x.strip()]
            return sorted((e for e in out if e.get("event") == "message"), key=lambda e: e.get("time", 0))
        except Exception as ex:
            log("讀 ntfy 失敗：", repr(ex))
            time.sleep(5 * (i + 1))
    return None


def listen(D, seconds):
    """連著 ntfy 串流，收到就寄。斷線會自動重連，直到時間到。"""
    end = time.time() + seconds
    n = 0
    while time.time() < end - 5:
        since = str(max(int(D["lastTime"]) - 60, 1))
        url = f"https://ntfy.sh/{TOPIC}/json?since={since}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "cloud-watch"}), timeout=90) as r:
                while time.time() < end:
                    line = r.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    e = json.loads(line)
                    if e.get("event") == "message" and e["id"] not in D["sent"]:
                        log("收到新的機票通知：", e.get("title", ""))
                        if forward(D, e):
                            n += 1
                        else:
                            log("寄信失敗，下一輪再試")
                            return n
        except (socket.timeout, TimeoutError):
            pass
        except Exception as ex:
            log("連線中斷：", repr(ex))
            time.sleep(5)
    return n


def main():
    if not TOPIC:
        log("還沒設定 NTFY_FLIGHT_TOPIC，這次不轉寄")
        return
    try:
        with open(DATA, encoding="utf-8") as f:
            D = json.load(f)
    except Exception:
        D = {}
    D.setdefault("sent", [])
    if "lastTime" not in D:
        msgs = poll(D, "12h")
        if msgs is None:
            return
        D["lastTime"] = msgs[-1]["time"] if msgs else int(time.time())
        D["sent"].extend(e["id"] for e in msgs)
        save(D)
        log(f"第一次執行：略過現有 {len(msgs)} 則，之後的新通知才轉寄")
        return
    # 先補寄漏掉的
    msgs = poll(D, str(max(int(D["lastTime"]) - 60, 1)))
    n = 0
    for e in msgs or []:
        if e["id"] in D["sent"]:
            continue
        if not forward(D, e):
            log("寄信失敗，下一輪再試")
            save(D)
            return
        n += 1
    hour = dt.datetime.now(TPE).hour
    if hour in LIVE_HOURS or os.environ.get("FORCE_LISTEN") == "1":
        log(f"機票通知時段，即時監聽 {LISTEN_SECONDS // 60} 分鐘")
        n += listen(D, LISTEN_SECONDS)
    log(f"轉寄 {n} 則機票通知" if n else "沒有新的機票通知")
    save(D)


if __name__ == "__main__":
    main()
