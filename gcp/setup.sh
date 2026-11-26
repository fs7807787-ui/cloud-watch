#!/bin/bash
# LINE 台灣排行：Google Cloud 一鍵設定（在 Cloud Shell 執行）
# 會建立：一個 Cloud Run 工作（台灣機房 asia-east1）＋ 每小時觸發一次的 Cloud Scheduler
# 可以重複執行：已經存在的會直接更新。
set -uo pipefail

REGION=asia-east1
JOB=line-rank
SCHED=line-rank-hourly
SA_NAME=line-rank-invoker
REPO=fs7807787-ui/cloud-watch
IMAGE=docker.io/library/python:3.12-slim

say(){ printf '\n\033[1;32m== %s ==\033[0m\n' "$*"; }
fail(){ printf '\n\033[1;31m✗ %s\033[0m\n請把上面的畫面截圖給 Claude。\n' "$*"; exit 1; }

say "1/6 選擇專案"
PROJECT=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT" ] || [ "$PROJECT" = "(unset)" ]; then
  PROJECT=$(gcloud projects list --format='value(projectId)' --limit=1 2>/dev/null)
fi
if [ -z "$PROJECT" ]; then
  PROJECT="line-rank-$(head -c3 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  echo "建立新專案 $PROJECT"
  gcloud projects create "$PROJECT" --name="LINE rank" || fail "建立專案失敗"
fi
gcloud config set project "$PROJECT" >/dev/null 2>&1
echo "使用專案：$PROJECT"

say "2/6 確認帳單（綁信用卡）"
if [ "$(gcloud billing projects describe "$PROJECT" --format='value(billingEnabled)' 2>/dev/null)" != "True" ]; then
  BA=$(gcloud billing accounts list --filter=open=true --format='value(name)' --limit=1 2>/dev/null)
  [ -z "$BA" ] && fail "找不到帳單帳戶。請先到 https://console.cloud.google.com/billing 建立帳單帳戶（綁信用卡），再重新執行"
  gcloud billing projects link "$PROJECT" --billing-account="${BA##*/}" >/dev/null || fail "連結帳單失敗"
fi
echo "帳單：已啟用"

say "3/6 開啟需要的服務（第一次約 1～2 分鐘）"
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com logging.googleapis.com || fail "開啟服務失敗"

say "4/6 設定 GitHub token"
if [ -z "${GH_TOKEN:-}" ]; then
  read -rsp "貼上 GitHub token（github_pat_ 開頭，貼上後畫面不會顯示，直接按 Enter）：" GH_TOKEN </dev/tty; echo
fi
GH_TOKEN=$(printf '%s' "$GH_TOKEN" | tr -d '[:space:]')
echo "收到的 token：${GH_TOKEN:0:11}…（共 ${#GH_TOKEN} 個字）"
case "$GH_TOKEN" in
  github_pat_*|ghp_*) ;;
  "") fail "沒有收到 token（可能沒貼上）。在黑色視窗裡請用 Ctrl+Shift+V 或按滑鼠右鍵 →「貼上」，再按 Enter" ;;
  *) fail "token 格式不對，應該是 github_pat_ 開頭（上面顯示的是你貼進來的開頭）" ;;
esac
CODE='import urllib.request,time;exec(urllib.request.urlopen("https://raw.githubusercontent.com/'"$REPO"'/main/gcp/rank.py?t="+str(time.time())).read())'
gcloud run jobs deploy "$JOB" --region="$REGION" --image="$IMAGE" \
  --command=python3 --args="^|^-c|$CODE" \
  --set-env-vars="^|^GH_TOKEN=$GH_TOKEN|REPO=$REPO" \
  --cpu=1 --memory=512Mi --task-timeout=15m --max-retries=1 --quiet || fail "建立 Cloud Run 工作失敗"

say "5/6 第一次試跑（約 2～4 分鐘，請稍等）"
gcloud run jobs execute "$JOB" --region="$REGION" --update-env-vars=TESLA_TEST=1 --wait --quiet
sleep 15
echo "------ 執行結果 ------"
gcloud logging read "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"$JOB\"" \
  --freshness=15m --order=asc --limit=80 --format='value(textPayload)' | grep -v '^$'
echo "----------------------"

say "6/6 設定每小時自動執行"
SA="$SA_NAME@$PROJECT.iam.gserviceaccount.com"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$SA_NAME" --display-name="LINE rank scheduler" >/dev/null
sleep 5
gcloud run jobs add-iam-policy-binding "$JOB" --region="$REGION" \
  --member="serviceAccount:$SA" --role=roles/run.invoker >/dev/null || fail "設定執行權限失敗"
URI="https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/$JOB:run"
if gcloud scheduler jobs describe "$SCHED" --location="$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$SCHED" --location="$REGION" --schedule="17 * * * *" --time-zone="Asia/Taipei" \
    --uri="$URI" --http-method=POST --oauth-service-account-email="$SA" >/dev/null || fail "更新排程失敗"
else
  gcloud scheduler jobs create http "$SCHED" --location="$REGION" --schedule="17 * * * *" --time-zone="Asia/Taipei" \
    --uri="$URI" --http-method=POST --oauth-service-account-email="$SA" >/dev/null || fail "建立排程失敗"
fi
echo "排程：每小時 17 分執行一次（台灣時間）"

say "完成！"
echo "請把「執行結果」那一段截圖給 Claude 確認。"
echo "建議設定預算提醒：https://console.cloud.google.com/billing/budgets （金額填 50，幣別依帳戶）"
