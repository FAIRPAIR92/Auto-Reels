# 릴스 자동화 기술스펙서 (GCP 기반)

| 항목 | 내용 |
|---|---|
| 문서 버전 | v0.2 |
| 작성일 | 2026-10-15 |
| 시스템명 | Reels Studio (가칭) |
| 기반 | Google Cloud Platform (GCP), Claude(대화형 오케스트레이션), uplika(인스타그램 게시 · DM 자동화) |

---

## 1. 개요

### 1.1 목적
Claude와의 한 대화 안에서 **영상 편집 → 사람 확인 → 인스타그램 릴스 게시 → 댓글 키워드 DM 자동화**까지 이어지는 파이프라인을 구축한다. 영상 분석·생성·편집은 GCP 위에 구축한 **Reels Studio MCP 서버**가 담당하고, 게시와 DM 자동화는 uplika가 담당한다. 사용자는 편집 프로그램을 열거나 파일을 옮기지 않고 채팅만으로 릴스 한 편을 완성해 올린다.

### 1.2 범위
| 포함 | 제외 |
|---|---|
| 참고 영상 분석, 부족한 장면 생성, 컷 편집 · 자막 합성, 최종 mp4 출력 | uplika 자체 기능 개발 (외부 서비스 그대로 사용) |
| 예상 비용 산출 및 승인 게이트 | 인스타그램 앱 내 직접 편집 |
| 결과물 보관 및 uplika 전달용 URL 발급 | |
| Claude 커스텀 커넥터(MCP) 제공 | |

### 1.3 주요 요구사항
- **R1** 참고 영상의 편집 스타일(컷 템포, 전환, 자막 스타일)을 사용자 소스(클립·사진, 이미지 최대 5장)로 재현한다.
- **R2** 소스로 채울 수 없는 장면은 AI로 생성해 채운다.
- **R3** 세로 9:16, 지정 길이(예: 30초) 이내의 완성본 1개를 자막 포함으로 출력한다.
- **R4** 생성 전에 예상 비용을 보여주고, 사용자 승인 없이는 과금 작업을 실행하지 않는다.
- **R5** 결과 수정은 "바꿀 점 한 줄"로 요청하며, 바뀐 부분만 다시 만든다.
- **R6** 완성본은 사람이 확인한 뒤 uplika로 인스타그램 릴스에 게시한다.
- **R7** 게시한 릴스에 댓글 키워드 → DM 자동화를 건다.

---

## 2. 전체 아키텍처

```
 사용자 ─ claude.ai 대화
            │
            ├─(커스텀 커넥터 A)─▶ Reels Studio MCP 서버  [Cloud Run]
            │                        │
            │                        ├─ Firestore ............ 작업(Job) 상태 · 견적 · 버전 이력
            │                        ├─ Cloud Storage ........ 소스 · 생성 클립 · 완성본 · 커버
            │                        ├─ Cloud Tasks/Workflows  비동기 파이프라인 실행
            │                        │     ├─ Vertex AI Gemini ...... 참고 영상 분석 → 편집 계획(EDL)
            │                        │     ├─ Vertex AI Veo ......... 부족한 장면 영상 생성
            │                        │     ├─ Vertex AI Imagen ...... 정지 이미지 / 커버 생성
            │                        │     ├─ Speech-to-Text (Chirp)  음성 → 자막 타이밍
            │                        │     ├─ Text-to-Speech ........ (선택) 내레이션
            │                        │     └─ Cloud Run Job (FFmpeg)  컷 편집 · 자막 번인 · 인코딩
            │                        └─ Secret Manager / IAM / Cloud Logging · Monitoring
            │
            └─(커스텀 커넥터 B)─▶ uplika MCP  https://api.uplika.com/mcp
                                     └─ Instagram 릴스 게시 · 댓글→DM 자동화
```

### 2.1 구성 요소
| 기능 | GCP 서비스 | 비고 |
|---|---|---|
| MCP 커넥터 엔드포인트 | **Cloud Run** (Streamable HTTP MCP 서버) | 리전 `asia-northeast3`(서울) 기본, Vertex 모델은 지원 리전(예: `us-central1`) 호출 |
| 참고 영상 분석 | **Vertex AI Gemini** (2.5 Pro 계열, 영상 입력) | 컷 길이, 전환, 카메라 무빙, 자막 위치, 템포를 JSON 편집 계획으로 추출 |
| 장면 영상 생성 | **Vertex AI Veo** (Veo 3 계열) | 텍스트→영상, 이미지→영상 |
| 이미지 생성 · 보정 | **Vertex AI Imagen** 또는 Gemini Image | 커버 이미지, 제품 컷 보정 |
| 자막 생성 | **Speech-to-Text v2 (Chirp)** + Gemini 교정 | 한국어 오타 교정 · 줄바꿈 길이 제한 |
| 내레이션 (선택) | **Text-to-Speech** (한국어 음성) | |
| 최종 합성 · 인코딩 | **Cloud Run Jobs + FFmpeg** | 자막 번인(ASS), 컷 연결, 9:16 리프레임, H.264/AAC mp4. 단순 연결만이면 Transcoder API도 가능 |
| 비용 견적 · 통제 | 자체 견적 모듈 + **Cloud Billing 예산 알림** | 5장 참조 |
| 결과물 보관 | **Cloud Storage** + **Firestore** | 수명주기 규칙으로 중간 산출물 자동 삭제 |
| 인증 | **OAuth 2.0** (Google Identity / Identity Platform) | claude.ai 커스텀 커넥터의 OAuth 흐름 지원 |
| 작업 큐 | **Cloud Tasks** 또는 **Workflows** | 생성은 수 분 걸리므로 비동기 |
| 콘텐츠 검사 | Gemini + **Video Intelligence API** | 얼굴 · 로고 감지 |

---

## 3. 사용자 흐름

모든 단계는 **같은 대화 안에서** 이어서 보낸다. "방금 만든 완성본", "방금 올린 릴스"가 앞 대화의 결과를 가리키기 때문이다.

### 3.0 최초 1회 연결
1. uplika 대시보드(`https://uplika.com/dashboard/connections`)에서 게시할 인스타그램 계정을 먼저 연결한다.
2. claude.ai › 맞춤 설정 › 커넥터 › 추가 › **커스텀 커넥터 추가**
   - A: 이름 `Reels Studio`, 주소 `https://<cloud-run-서비스>/mcp` → Google 계정(허용된 사용자만)으로 로그인
   - B: 이름 `uplika`, 주소 `https://api.uplika.com/mcp` → uplika 로그인 (API 키 불필요)
3. 대화의 「+」 메뉴에서 두 커넥터가 켜져 있는지 확인한다.

### 3.1 프롬프트 1 · 편집
```
릴스 스튜디오로 편집해줘. 참고 영상은 첨부한 [참고 영상]처럼, 내 소스는 첨부한 [클립 · 사진]으로.
세로 9:16, [30]초 안쪽. 모자란 장면은 새로 만들어 채우고 자막까지 넣어서 완성본 하나로 만들어줘.
시작하기 전에 예상 비용부터 보여주고, 내가 '진행' 하면 시작해.
```
시스템 동작: `reels_upload_source` → `reels_plan`(분석 + 견적, 생성 없음) → 사용자 "진행" → `reels_render` → `reels_status` 확인 → 미리보기 URL 제시.

### 3.2 확인 (게시 전 필수)
인스타그램은 게시 후 수정이 안 되므로(삭제 후 재게시만 가능) 게시 전 확인 단계를 둔다. 서버가 자동 검사를 먼저 돌리고, 사람이 미리보기로 한 번 본다.

| 항목 | 자동 검사 | 기준 |
|---|---|---|
| 비율 · 길이 · 규격 | ffprobe | 9:16, mp4/mov, ≤300MB, ≤15분, 가로 ≤1920 (uplika 인스타 규격) |
| 생성 장면 | Gemini 영상 리뷰 | 어색한 장면 · 문맥 불일치 플래그 |
| 자막 | Gemini 텍스트 검사 | 한글 오타, 잘린 줄, 안전 영역 밖 위치 |
| 타인 얼굴 · 로고 · 음악 | Gemini + Video Intelligence API | 참고 영상에서 딸려 온 요소 경고 |
| 커버 | 규격 검사 | jpeg, ≤8MB. 미지정 시 영상 앞부분 |

수정 프롬프트:
```
방금 결과에서 [바꿀 점 · 예: 3번째 장면 자막]만 바꿔서 다시 만들어줘. 나머지는 그대로. 다시 만들기 전에 예상 비용부터 보여줘.
```
→ `reels_revise`: 편집 계획에서 해당 장면만 무효화하고 재생성. 나머지 클립은 캐시 재사용.

### 3.3 프롬프트 2 · 릴스 올리기
```
방금 만든 완성본을 업리카로 인스타 릴스로 올려줘. 캡션도 써 주고, 마지막엔 댓글에 '[키워드]' 남기라고 넣어줘.
올리기 전에 길이랑 커버, 캡션, 계정부터 보여줘. 계정은 업리카 [워크스페이스] 워크스페이스의 @[내 계정] 인스타로.
```
- 완성본은 `reels_export`가 발급한 **GCS Signed URL**(유효 1시간)로 uplika `media_from_url`에 전달한다.
- 실패 시 uplika `media_upload_link`로 받은 업로드 링크에 서버가 직접 PUT 한다.
- 워크스페이스가 여러 개면 계정 줄을 반드시 적는다. 생략하면 다른 워크스페이스의 계정이 선택될 수 있다.
- 요약(길이 · 커버 · 캡션 · 계정)을 확인한 뒤 「올려줘」하면 게시된다. 영상 1개는 기본이 릴스.

### 3.4 프롬프트 3 · 댓글 → DM 자동화
```
방금 올린 릴스에 '[키워드]' 댓글이 달리면 [자료 링크]를 DM 으로 보내줘. 첫 DM 은 버튼으로,
팔로우 확인 켜고. 초안 먼저 보여주고 내가 '켜' 하면 켜.
```
| 항목 | 설명 |
|---|---|
| 키워드 | 이 단어가 들어간 댓글에 반응 |
| 첫 DM | 버튼 1개 필수. 버튼이 없으면 팔로우 확인과 후속 메시지가 동작하지 않음 |
| 팔로우 확인 | 버튼을 누른 사람의 팔로우 여부 확인 (인스타그램 전용) |
| 자료 | 버튼으로 다는 링크, 최대 3개 |

「켜」하는 순간부터 실제 사용자에게 발송되므로, 처음에는 다른 계정으로 키워드 댓글을 달아 직접 수신을 확인한다.

---

## 4. MCP 서버 도구 명세

| 도구 | 입력 | 출력 | 부작용 |
|---|---|---|---|
| `reels_upload_source` | 파일 또는 URL, 종류(`reference` / `source`) | `asset_id`, 업로드용 Signed URL | GCS 저장 |
| `reels_plan` | `reference_asset_id`, `source_asset_ids[]`(이미지 최대 5), `aspect`(기본 `9:16`), `max_seconds`, `instructions` | `job_id`, 장면 목록(EDL), 생성 필요 장면 수/초, **예상 비용**, `approval_token` | 분석만. 생성 비용 없음 (Gemini 분석 비용만) |
| `reels_render` | `job_id`, `approval_token` | `job_id`, 상태 `queued` | Veo/Imagen 생성 · 합성 시작 (**과금**) |
| `reels_status` | `job_id` | 상태, 진행률, 미리보기 URL, 자동 검사 결과 | 없음 |
| `reels_revise` | `job_id`, `change`(한 줄) | 새 `plan` + 예상 비용 + `approval_token` | 분석만 |
| `reels_export` | `job_id`, `version` | 완성본 Signed URL, 커버 Signed URL, 메타(길이·해상도·용량) | 없음 |
| `reels_list_assets` | 기간, 개수 | 최근 작업/완성본 목록 | 없음 |
| `reels_templates` | `action`(list/save/apply), `template_id` | 저장된 편집 계획 템플릿 | Firestore 저장 |

규칙:
- `reels_render`는 **유효한 `approval_token` 없이는 거부**한다. 토큰은 `reels_plan`/`reels_revise`가 발급하며 견적 금액에 묶이고 30분 후 만료된다.
- 모든 생성 도구는 비동기. Claude는 `reels_status`로 상태를 확인한다.
- 자주 쓰는 편집 스타일은 `reels_templates`로 저장해 참고 영상 없이 재사용할 수 있다.

---

## 5. 비용 견적 · 통제

| 요소 | 산식 |
|---|---|
| Veo 생성 | 생성 초 수 × 모델별 초당 단가 (오디오 포함 여부 · Fast 모델 여부에 따라 다름) |
| Imagen | 이미지 장 수 × 장당 단가 |
| Gemini 분석 · 리뷰 | 입력 영상 길이/토큰 × 단가 |
| Speech-to-Text / TTS | 오디오 분 · 글자 수 × 단가 |
| Cloud Run(FFmpeg) · GCS | 실행 vCPU·초, 저장 용량 (소액) |

- 단가는 하드코딩하지 않고 **설정값(Firestore `pricing` 문서)**으로 관리하며, Vertex AI 공식 단가표가 바뀌면 갱신한다.
- 견적은 USD와 KRW(설정 환율)로 함께 표시하고, 수정 시 **해당 장면만** 다시 계산한다.
- 안전장치: 작업당 상한(기본 $5), 일일 상한, Cloud Billing 예산 알림(50/90/100%). 상한을 넘는 견적에는 `approval_token`을 발급하지 않는다.

---

## 6. 처리 파이프라인 상세

1. **수집**: 업로드 파일을 `gs://<bucket>/jobs/{job_id}/input/`에 저장, ffprobe로 메타 추출.
2. **분석 (Gemini)**: 참고 영상 → 장면별 `{start, end, shot_type, motion, transition, caption_style, bgm_tempo}` JSON. 사용자 소스 이미지/클립을 각 장면에 매칭하고, 매칭되지 않는 장면을 "생성 필요"로 표시.
3. **견적**: 5장 산식 적용 → 사용자 승인 대기.
4. **생성 (Veo / Imagen)**: 생성 필요 장면마다 프롬프트 + 참고 이미지로 클립 생성. 모델이 9:16 직접 생성을 지원하지 않으면 16:9로 생성 후 리프레임(크롭). 장면 단위 병렬 실행, 결과 캐시.
5. **자막**: 소스 음성이 있으면 Chirp로 타임스탬프 추출 → Gemini로 교정 · 줄 나눔(한 줄 최대 16자 권장). 음성이 없으면 지침/캡션에서 자막 텍스트 생성.
6. **합성 (Cloud Run Job, FFmpeg)**: EDL 순서대로 컷 연결, 전환 효과, ASS 자막 번인, 오디오 믹스, 1080×1920 H.264/AAC mp4 출력, 커버 jpeg 추출.
7. **검사**: 3.2 자동 검사 실행, 결과를 `reels_status`에 포함.
8. **보관**: 완성본은 `final/v{n}.mp4`, 중간 산출물은 수명주기 규칙으로 7일 후 삭제.

---

## 7. 데이터 모델 (Firestore)

```
jobs/{job_id}
  owner, created_at, status(planning|awaiting_approval|rendering|done|failed)
  aspect, max_seconds, instructions
  reference_asset_id, source_asset_ids[], template_id
  plan: [{scene_idx, start, end, source_asset_id|null, generate:{model, prompt, seconds}}]
  estimate: {usd, krw, breakdown[]}, approval_token_hash, approval_expires_at
  versions: [{v, final_uri, cover_uri, duration, size_bytes, checks{}, created_at}]
assets/{asset_id}
  owner, kind(reference|source|generated|final), gcs_uri, mime, duration, width, height
templates/{template_id}
  owner, name, plan_skeleton[], caption_style, created_at
pricing/current
  veo_per_sec{...}, imagen_per_image, gemini_per_1k_tokens, fx_krw_per_usd, updated_at
```

---

## 8. 보안 · 운영

- **인증**: MCP 엔드포인트는 OAuth 2.0 필수, 허용 사용자/도메인 화이트리스트.
- **권한**: Cloud Run 서비스 계정 최소 권한 (`roles/aiplatform.user`, 대상 버킷 한정 `storage.objectAdmin`, `datastore.user`).
- **비밀**: 외부 키가 필요하면 Secret Manager에 보관 (uplika는 claude.ai 커넥터 측 로그인이라 서버가 보관하는 키 없음).
- **Signed URL**: 읽기 전용, 1시간 만료.
- **콘텐츠 정책**: Vertex AI 안전 필터 결과를 사용자에게 그대로 전달(차단 시 사유 표시), 실존 인물 얼굴 생성 금지 설정.
- **관측**: Cloud Logging(작업별 trace), Cloud Monitoring 알림(실패율, 평균 렌더 시간, 일일 비용).
- **리전**: 데이터 저장은 서울(`asia-northeast3`), 모델 호출은 지원 리전(예: `us-central1`).

---

## 9. 장애 · 예외 처리

| 증상 | 원인 | 처리 |
|---|---|---|
| 커넥터 연결 실패 | OAuth 미허용 계정 | 화이트리스트 확인 |
| 생성 거부 | 승인 토큰 없음/만료, 비용 상한 초과 | `reels_plan` 다시 실행, 상한 조정 |
| Veo 생성 실패/차단 | 안전 필터, 쿼터 | 프롬프트 수정 제안, 쿼터 증설 요청, 지수 백오프 재시도(3회) |
| 비용이 예상보다 큼 | 장면 수/길이 과다 | 견적에 장면별 비용 표시, Fast 모델 옵션 |
| 엉뚱한 계정으로 게시 시도 | uplika 워크스페이스 미지정 | 프롬프트 2에 계정 줄 필수 |
| 완성본이 uplika로 안 넘어감 | URL 만료 · 접근 불가 | Signed URL 재발급 → 실패 시 uplika 업로드 링크로 서버 직접 PUT |
| DM 자동화 권한 오류 `reconsent_required` | 인스타 메시징 권한 없음 | uplika 대시보드에서 인스타 다시 연결 |
| 게시 후 삭제 필요 | uplika 삭제는 페이스북 경유 연결 계정만 지원 | 그 외에는 인스타 앱에서 삭제 |

---

## 10. 확장 · 모션 그래픽 렌더러 (선택)

자막 카드, 숫자 카운트업, 타이틀 모션처럼 코드로 정밀하게 짜는 그래픽이 필요하면 6장 합성 단계에 **HTML 기반 렌더러(예: 오픈소스 하이퍼프레임, Node.js 22 + FFmpeg)를 실행하는 Cloud Run Job**을 추가한다. 렌더 결과는 일반 클립처럼 EDL에 들어가 합성된다.

---

## 11. 구현 단계

| 단계 | 내용 | 산출물 |
|---|---|---|
| M1 | GCP 프로젝트, 버킷, Firestore, Cloud Run MCP 골격, OAuth | 커넥터 연결 성공 |
| M2 | `reels_plan` (Gemini 분석 + 견적), 승인 토큰 | 분석·견적 동작 |
| M3 | Veo/Imagen 생성 + FFmpeg 합성 + 자막 | 완성본 mp4 |
| M4 | 자동 검사, `reels_revise`, `reels_export` → uplika 연동 | 편집→게시 E2E |
| M5 | 템플릿, 비용 상한·예산 알림, 모니터링, 운영 문서 | 운영 투입 |

## 12. 구현 전 확인 사항
- Veo 모델 버전별 9:16 직접 생성 지원 여부, 1회 생성 최대 길이, 참고 이미지 개수 제한은 착수 시 Vertex AI 문서로 확정한다. 미지원 시를 대비해 리프레임 경로를 포함해 두었다.
- 인물 동작을 그대로 옮기는 수준의 모션 재현은 Veo의 영상/이미지 입력 기능 범위 안에서만 가능하다.
