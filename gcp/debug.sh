#!/bin/bash
# 在 Cloud Shell 執行：用 Google Cloud 台灣機房檢查 LINE 排行（不會改任何設定）
REGION=asia-east1; JOB=line-rank
echo "檢查中，約 3～5 分鐘，請稍等…"
gcloud run jobs execute "$JOB" --region="$REGION" --update-env-vars=DEBUG=1 --wait --quiet >/dev/null 2>&1 || echo "（執行時有錯誤，下面的結果還是有參考價值）"
sleep 15
echo "------ 檢查結果 ------"
gcloud logging read "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"$JOB\"" \
  --freshness=10m --order=asc --limit=60 --format='value(textPayload)' | grep -v '^$' | grep -vE 'Container called exit'
echo "----------------------"
echo "請把「檢查結果」截圖給 Claude。"
