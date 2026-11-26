import sys, json, re, datetime as dt, subprocess
sys.path.insert(0, ".")
import ptt
seen = set(json.loads(subprocess.run(["git", "show", "origin/ptt:ptt.json"], capture_output=True, text=True).stdout)["seen"])
for b in ptt.BOARDS:
    es = ptt.entries(b)
    new = [l for l, t, _ in es if l not in seen]
    ep = sorted(int(re.search(r"M\.(\d+)", l).group(1)) for l, _, _ in es)
    print(b, len(es), "不在紀錄裡：", len(new), "最新文章時間：", dt.datetime.fromtimestamp(ep[-1], dt.timezone(dt.timedelta(hours=8))))
