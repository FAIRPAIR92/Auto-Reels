#!/usr/bin/env bash
# 서버를 Cloud Run 에 배포한다. (소스에서 바로 빌드)
set -euo pipefail
cd "$(dirname "$0")"
[ -f ./config.env ] || { echo "deploy/config.env 가 없습니다. README 의 배포하기 1번을 먼저 하세요."; exit 1; }
source ./config.env

# 터미널 탭이 바뀌어도 항상 이 프로젝트를 쓰도록 고정
gcloud config set project "$PROJECT_ID" >/dev/null

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
SA="${SERVICE}@${PROJECT_ID}.iam.gserviceaccount.com"
BASE_URL="https://${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"

gcloud run deploy "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" --source=../server \
  --service-account="$SA" --allow-unauthenticated \
  --memory=1Gi --max-instances=3 \
  --set-env-vars="^|^GOOGLE_CLOUD_PROJECT=$PROJECT_ID|REELS_BUCKET=${PROJECT_ID}-reels|BASE_URL=$BASE_URL|SIGNER_SERVICE_ACCOUNT=$SA|ALLOWED_EMAILS=$ALLOWED_EMAILS" \
  --set-secrets="JWT_SIGNING_KEY=reels-jwt-key:latest,GOOGLE_OAUTH_CLIENT_ID=reels-oauth-client-id:latest,GOOGLE_OAUTH_CLIENT_SECRET=reels-oauth-client-secret:latest"

echo
echo "✅ 배포 완료. 상태 확인: $BASE_URL/health"
echo "claude.ai 커스텀 커넥터 주소: $BASE_URL/mcp"
