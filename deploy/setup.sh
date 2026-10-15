#!/usr/bin/env bash
# GCP 리소스를 한 번 만든다: API, 서비스 계정, 버킷, Firestore, 비밀값.
# 여러 번 실행해도 이미 있는 것은 건너뛴다.
set -euo pipefail
cd "$(dirname "$0")"
source ./config.env

gcloud config set project "$PROJECT_ID" >/dev/null
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
SA="${SERVICE}@${PROJECT_ID}.iam.gserviceaccount.com"
BUCKET="${PROJECT_ID}-reels"
BASE_URL="https://${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"

echo "▶ API 사용 설정"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com storage.googleapis.com aiplatform.googleapis.com \
  secretmanager.googleapis.com iamcredentials.googleapis.com

echo "▶ 서비스 계정"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$SERVICE" --display-name="Reels Studio"
for role in roles/datastore.user roles/aiplatform.user roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role="$role" --condition=None >/dev/null
done
# 서명 URL 을 만들기 위해 자기 자신으로 서명할 수 있어야 한다
gcloud iam service-accounts add-iam-policy-binding "$SA" \
  --member="serviceAccount:$SA" --role=roles/iam.serviceAccountTokenCreator >/dev/null

echo "▶ Cloud Storage 버킷: gs://$BUCKET"
gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://$BUCKET" --location="$REGION" --uniform-bucket-level-access
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$SA" --role=roles/storage.objectAdmin >/dev/null
cat > /tmp/reels-cors.json <<JSON
[{"origin": ["$BASE_URL"], "method": ["PUT", "GET"], "responseHeader": ["Content-Type"], "maxAgeSeconds": 3600}]
JSON
cat > /tmp/reels-lifecycle.json <<JSON
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 7, "matchesPrefix": ["jobs/tmp/"]}}]}
JSON
gcloud storage buckets update "gs://$BUCKET" --cors-file=/tmp/reels-cors.json --lifecycle-file=/tmp/reels-lifecycle.json

echo "▶ Firestore"
gcloud firestore databases describe --database='(default)' >/dev/null 2>&1 || \
  gcloud firestore databases create --location="$REGION" --type=firestore-native
for coll in assets jobs; do
  gcloud firestore indexes composite create --collection-group="$coll" \
    --field-config=field-path=owner,order=ascending --field-config=field-path=created_at,order=descending \
    --async >/dev/null 2>&1 || true
done

echo "▶ JWT 서명 키 (Secret Manager)"
gcloud secrets describe reels-jwt-key >/dev/null 2>&1 || \
  openssl rand -hex 32 | gcloud secrets create reels-jwt-key --data-file=-

cat <<MSG

✅ 기본 리소스 준비 완료.

다음은 콘솔에서 직접 해야 합니다 (OAuth 클라이언트는 명령으로 만들 수 없음):
 1) OAuth 동의 화면 설정 (외부, 테스트 사용자에 본인 이메일 추가)
    https://console.cloud.google.com/auth/overview?project=$PROJECT_ID
 2) OAuth 클라이언트 ID 만들기 → 유형 '웹 애플리케이션'
    https://console.cloud.google.com/auth/clients/create?project=$PROJECT_ID
    승인된 리디렉션 URI:  $BASE_URL/auth/callback
 3) 만든 클라이언트 ID/보안 비밀을 저장:
    printf '%s' '<클라이언트ID>'   | gcloud secrets create reels-oauth-client-id --data-file=-
    printf '%s' '<클라이언트보안비밀>' | gcloud secrets create reels-oauth-client-secret --data-file=-
 그다음 ./deploy.sh 를 실행하세요.
MSG
