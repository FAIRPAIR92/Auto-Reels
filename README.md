# Auto-Reels

Claude 대화 한 번으로 인스타그램 릴스를 **편집 → 확인 → 게시 → 댓글 DM 자동화**까지 하는 프로젝트입니다.
영상 분석·생성·편집은 GCP 위의 **Reels Studio MCP 서버**가, 게시와 DM 자동화는 uplika가 맡습니다.

- 기술스펙: [docs/tech-spec.md](docs/tech-spec.md)

## 구조

```
server/   Reels Studio MCP 서버 (Python, FastMCP, Cloud Run)
deploy/   GCP 리소스 준비(setup.sh)와 배포(deploy.sh) 스크립트
docs/     기술스펙
```

## 현재 단계: M1 (서버 뼈대)

| 도구 | 상태 |
|---|---|
| `reels_upload_source` | ✅ URL 가져오기 / 업로드 페이지 발급 |
| `reels_list_assets` | ✅ |
| `reels_status` | ✅ |
| `reels_export` | ✅ 완성본 서명 URL 발급 |
| `reels_plan` | 입력 검사만. 분석·견적은 M2 |
| `reels_render` | M3 |
| `reels_revise` | M4 |
| `reels_templates` | M5 |

## 배포하기

필요한 것: [gcloud CLI](https://cloud.google.com/sdk/docs/install), 결제가 연결된 GCP 프로젝트

1. 설정 파일 만들기
   ```bash
   cp deploy/config.env.example deploy/config.env   # PROJECT_ID, ALLOWED_EMAILS 채우기
   gcloud auth login
   ```
2. GCP 리소스 만들기: `./deploy/setup.sh`
3. 스크립트가 끝에 알려주는 대로 콘솔에서 OAuth 클라이언트를 만들고 비밀값 2개를 저장
   - [OAuth 동의 화면](https://console.cloud.google.com/auth/overview)
   - [OAuth 클라이언트 만들기](https://console.cloud.google.com/auth/clients/create)
4. 배포: `./deploy/deploy.sh`
5. [claude.ai 커넥터 설정](https://claude.ai/settings/connectors)에서 **커스텀 커넥터 추가** → 주소에 `https://<서비스주소>/mcp` 입력 → Google 계정으로 로그인

## 로컬 개발

```bash
cd server
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest
DISABLE_AUTH=1 uvicorn app.main:app --port 8080   # GCP 없이 메모리 저장소로 실행
```
