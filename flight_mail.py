"""把機票監控的 ntfy 通知轉寄成 email。

機票監控是另一個排程（Claude 定時任務）發的 ntfy，它自己沒辦法寄信，
所以這裡跟著每 10 分鐘的愛心記錄一起跑：讀機票 topic 的新通知，逐則寄出。
需要 secret：NTFY_FLIGHT_TOPIC（機票 topic 名稱），以及 mailer.py 的兩個 Gmail secret。
第一次執行只記下目前最新的一則，不寄舊通知。
"""
import json
import os
import time
import urllib.request

from mailer import send_mail

TOPIC = os.environ.get("NTFY_FLIGHT_TOPIC", "").strip()
DATA = "data/flightmail.json"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def main():
    if not TOPIC:
        log("還沒設定 NTFY_FLIGHT_TOPIC，這次不轉寄")
        return
    try:
        with open(DATA, encoding="utf-8") as f:
            D = json.load(f)
    except Exception:
        D = {}
    first = "lastTime" not in D
    since = "12h" if first else str(max(int(D["lastTime"]) - 60, 1))
    url = f"https://ntfy.sh/{TOPIC}/json?poll=1&since={since}"
    msgs = []
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "cloud-watch"}), timeout=30) as r:
                for line in r.read().decode("utf-8").splitlines():
                    line = line.strip()
                    if line:
                        e = json.loads(line)
                        if e.get("event") == "message":
                            msgs.append(e)
            break
        except Exception as e:
            log("讀 ntfy 失敗：", repr(e))
            time.sleep(5 * (i + 1))
    else:
        return
    msgs.sort(key=lambda e: e.get("time", 0))
    sent_ids = D.get("sent", [])
    if first:
        D["lastTime"] = msgs[-1]["time"] if msgs else int(time.time())
        sent_ids.extend(e["id"] for e in msgs)
        log(f"第一次執行：略過現有 {len(msgs)} 則，之後的新通知才轉寄")
    else:
        n = 0
        for e in msgs:
            if e["id"] in sent_ids:
                continue
            title = e.get("title") or "機票通知"
            body = e.get("message", "")
            click = e.get("click") or ""
            if send_mail(title, body, click or None, "打開機票通知紀錄（訂票、即時查價）"):
                sent_ids.append(e["id"])
                D["lastTime"] = max(int(D["lastTime"]), int(e["time"]))
                n += 1
            else:
                break  # 寄失敗就停，下一輪再從這則開始
        log(f"轉寄 {n} 則機票通知" if n else "沒有新的機票通知")
    D["sent"] = sent_ids[-300:]
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(D, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
