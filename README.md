# 파일 변환기

사진 묶기, 문서 변환, PDF 쪼개기를 한 번에. 말로 시켜도 돼요 ("사진 시간순으로 PDF로 묶어줘").

| | 오프라인 앱 | 온라인 앱 | 사이트 |
|---|---|---|---|
| 설치 | exe (파이썬 필요 없음) | exe | 필요 없음 (브라우저) |
| 인터넷 | 필요 없음 | AI·글자 추출에 필요 | 처음 접속할 때 |
| AI | 내장 Qwen2.5 1.5B (처음 1.1GB 받기) | Claude (중계 서버) | Claude (중계 서버) 또는 규칙 |
| 이미지 → PDF·Word·PPT·ZIP | ✓ | ✓ | ✓ |
| md·html·txt·docx 변환 | ✓ | ✓ | ✓ |
| Word·PPT·엑셀 → PDF | ✓ (MS 오피스/LibreOffice) | ✓ | – |
| PDF → Word | ✓ | ✓ | – |
| PDF → 이미지 | ✓ | ✓ | ✓ |
| 사진·스캔 글자 추출 | – | ✓ | ✓ |
| 파일이 밖으로 나가는지 | 안 나감 | AI 쓸 때 문장·글자 추출 파일만 | AI 쓸 때 문장·글자 추출 파일만 |

## 받기

- **앱**: [Actions](../../actions/workflows/build.yml) → 최근 성공한 빌드 → Artifacts에서 `FileConverter-offline-windows` 또는 `FileConverter-online-windows`
- **사이트**: `https://mikop23.github.io/file-converter/` (아래 1회 설정 후)

## 처음 한 번 설정

### 1. 사이트 켜기 (GitHub Pages)
저장소 **Settings → Pages → Source**를 **GitHub Actions**로 바꾸기 → **Actions → 사이트 배포 → Run workflow**

### 2. 온라인 AI 서버 만들기 (Cloudflare Workers, 무료)
필요한 것: [Cloudflare 계정](https://dash.cloudflare.com/sign-up), [Anthropic API 키](https://console.anthropic.com/)

```bash
cd server
npx wrangler login
npx wrangler secret put ANTHROPIC_API_KEY   # API 키 붙여넣기
npx wrangler deploy                          # 끝나면 https://file-converter-relay.<아이디>.workers.dev 주소가 나옴
```

### 3. 서버 주소 연결
저장소 **Settings → Secrets and variables → Actions → Variables**에 `RELAY_URL` = 위 주소 추가 → 다음 빌드부터 온라인 앱·사이트에 자동으로 들어감.
(앱·사이트 모두 오른쪽 위 **⚙ 설정**에서 직접 넣어도 됨)

## 비용·안전
- 중계 서버는 `/plan`(말 알아듣기)과 `/ocr`(글자 추출)만 허용 → API 키로 아무 대화나 못 시킴
- 같은 IP에서 1분 20번 제한 (`server/wrangler.toml`), 사이트 주소만 허용하려면 `ALLOWED_ORIGINS` 설정
- Anthropic 콘솔에서 월 사용 한도를 꼭 걸어두세요

## 구조
```
app.py        PC 앱 화면 (PySide6)
fconv.py      변환 엔진 (이미지 묶기, 문서 변환, PDF 쪼개기)
fai.py        말 → 작업 계획 (AI + 규칙 보정)
localai.py    오프라인 내장 AI (llama.cpp)
relay.py      온라인 AI·글자 추출 (중계 서버 호출)
server/       중계 서버 (Cloudflare Worker)
site/         사이트 (브라우저에서 변환)
tests/        AI 테스트, 사이트 브라우저 테스트
```
