# 일일 브리핑 대시보드 (Daily Briefing Dashboard)

매일 아침 구글 캘린더의 일정, 구글 드라이브 스프레드시트의 은퇴 자산 현황, 동탄의 일주일 날씨 정보, 그리고 주요 뉴스를 자동으로 크롤링하여 아주 세련되고 멋진 프리미엄 다크 모드/글래스모피즘(Glassmorphism) HTML 대시보드 문서로 제공해주는 자동화 도구입니다.

---

## 📂 파일 구조
- `update_dashboard.py`: 날씨, 뉴스, 구글 API 연동 및 데이터 가공을 담당하는 파이썬 코어 스크립트.
- `dashboard_template.html`: Jinja2 문법과 Tailwind CSS, Chart.js, Lucide Icons를 사용해 작성된 반응형 대시보드 템플릿.
- `requirements.txt`: 스크립트 실행을 위해 필요한 파이썬 라이브러리 목록.
- `run.sh`: 자동으로 파이썬 가상환경을 구축하고 라이브러리를 설치한 뒤 대시보드를 생성하여 기본 웹 브라우저로 열어주는 원클릭 쉘 스크립트.
- `dashboard.html` (생성 예정): 최종 빌드된 멋진 대시보드 결과물.

---

## ⚡ 데모 모드 (Demo Mode) 지원
구글 API 연동을 설정하지 않은 상태에서도 프로그램의 정상 작동 및 대시보드 디자인을 체험해볼 수 있도록 **데모 모드**를 지원합니다.
프로젝트 루트 디렉토리에 `credentials.json` 파일이 없을 경우, 스크립트는 실시간 동탄 날씨와 구글 뉴스를 정상 수집하되 자산 현황 및 구글 캘린더 일정은 미리 정의된 시각화용 데모 데이터(Mock Data)로 자동 구성하여 `dashboard.html`을 생성합니다.

---

## 🔐 Google Sheets & Calendar API 연동 가이드

실제 개인 은퇴자산 스프레드시트와 구글 캘린더 일정을 연동하려면 구글 클라우드 콘솔에서 OAuth 2.0 사용자 인증 정보를 다운로드해야 합니다. 아래 단계에 따라 설정해 주세요.

### 단계 1: Google Cloud 프로젝트 생성 및 API 활성화
1. **[Google Cloud 콘솔](https://console.cloud.google.com/)**에 접속하여 로그인합니다.
2. 새 프로젝트를 생성합니다 (예: `DailyBriefingDashboard`).
3. 검색창에 다음 세 가지 API를 검색하여 각각 **[사용(Enable)]** 설정합니다:
   - **Google Sheets API**
   - **Google Calendar API**
   - **Google Drive API**

### 단계 2: OAuth 동의 화면(Consent Screen) 설정
1. 좌측 메뉴에서 **API 및 서비스 > OAuth 동의 화면**으로 이동합니다.
2. User Type을 **외부(External)**로 선택하고 **만들기**를 클릭합니다.
3. 앱 이름(예: `My Daily Dashboard`)과 사용자 지원 이메일을 입력한 뒤 저장합니다.
4. **범위(Scopes)** 설정 단계에서 `.../auth/spreadsheets.readonly`, `.../auth/calendar.readonly`, `.../auth/drive.readonly` 범위를 추가합니다 (또는 건너뛴 후 아래 테스트 사용자 단계에서 계정을 등록하면 작동합니다).
5. **테스트 사용자(Test users)** 단계에서 대시보드와 연동할 본인의 **Google 계정 이메일**을 추가(Add users)합니다. (⚠️ 매우 중요: 테스트 계정을 등록하지 않으면 로그인 에러가 발생합니다).

### 단계 3: 사용자 인증 정보 생성 및 Credentials 다운로드
1. 좌측 메뉴에서 **사용자 인증 정보(Credentials)**로 이동합니다.
2. 상단의 **+ 사용자 인증 정보 만들기**를 클릭하고 **OAuth 클라이언트 ID**를 선택합니다.
3. 애플리케이션 유형을 **데스크톱 앱(Desktop App)**으로 선택하고 이름을 적절히 입력 후 만들기를 클릭합니다.
4. 생성된 클라이언트 정보 창에서 **JSON 다운로드**를 클릭합니다.
5. 다운로드한 파일의 이름을 **`credentials.json`**으로 변경하고, 이 프로젝트 폴더(`6.antigravity_test`) 바로 아래에 넣어 줍니다.

---

## 🚀 대시보드 실행 방법

터미널을 열고 프로젝트 폴더 경로에서 아래 쉘 스크립트를 실행해 주기만 하면 됩니다.

```bash
./run.sh
```

**최초 실행 시 동작:**
1. 파이썬 가상환경(`.venv`)이 자동으로 생성됩니다.
2. `requirements.txt`에 명시된 모든 라이브러리를 가상환경 안에 자동으로 설치합니다.
3. `update_dashboard.py`가 실행됩니다.
4. `credentials.json`이 있는 경우, 브라우저가 열리며 Google 계정 로그인을 요청합니다. 로그인을 승인하면 `token.json`이 로컬에 생성되어 이후에는 추가 로그인 없이 바로 작동합니다.
5. 데이터 수집이 끝나면 `dashboard.html` 파일이 생성되고 기본 웹 브라우저(Safari, Chrome 등)를 통해 대시보드 화면이 활성화됩니다.

---

## ⏰ macOS에서 매일 아침 자동 업데이트 설정 방법 (cron 사용)

매일 아침 특정 시간에 자동으로 대시보드를 최신 정보로 업데이트하여 바로 열어보고 싶으시다면, macOS에 내장된 `cron`을 활용하여 자동화할 수 있습니다.

1. 터미널에서 아래 명령을 실행하여 크론 설정 화면을 엽니다:
   ```bash
   crontab -e
   ```

2. 원하는 시간대에 맞추어 아래 포맷으로 크론 작업을 추가합니다. (예: 매일 아침 7시 30분에 실행)
   ```text
   30 07 * * * /Users/younghum/docker/claude-api/claude-config/workspace/6.antigravity_test/run.sh > /tmp/dashboard_update.log 2>&1
   ```
   *(⚠️ 주의: 프로젝트 경로가 다를 경우 실제 `run.sh`가 있는 절대경로를 입력해 주시기 바랍니다.)*

3. 저장하고 나옵니다. 이제 매일 아침 7시 30분에 자동으로 대시보드가 업데이트되고 웹 브라우저에 브리핑 화면이 표시됩니다.

---

## 🏃 건강 및 운동 관리 대시보드 (Workout Dashboard)

구글 스프레드시트의 **'건강 및 운동 관리 대시보드'** (`1prXk269ik5JTbghA5UZbh3uW56pMrzGhqnNtkrm3YKw`) 내 `'운동 기록'` 시트와 실시간 연동되어 동작하는 종합 운동 & 피트니스 관리 대시보드입니다.

- **실행 스크립트:** `./run_workout_dashboard.sh`
- **로컬 웹 주소:** `http://localhost:8082/workout_dashboard.html`
- **동기화 서버:** `workout_sync_server.py` (백그라운드에서 15초 주기로 구글 시트 변경사항 실시간 감지)
- **주요 기능:**
  1. **종합 대시보드 (Overview):** 당일(Today) 운동 세션 실시간 집계, 누적 시간/거리/칼로리 KPI, 일자별 볼륨 D3 차트
  2. **철인3종 가이드 & 코칭 (Triathlon):** 스프린트/올림픽 코스별 수영·사이클·달리기 진척률, 4단계 로드맵, 주간 추천 훈련 플래너, T1/T2 전환 가이드
  3. **종목별 향상 분석 (Analytics):** 종목별 필터링, 누적 시간 비교 바 차트, 회차별 페이스/속도 향상 추이 곡선
  4. **운동 기록 대장 (Logs):** 전수 92건 운동 기록 검색, 정렬, 신규 등록 및 수정/삭제 모달
  5. **볼륨 & 심박수 추이 (Trends):** 일자별 트레이닝 부하 및 세션별 평균 심박수(bpm) 모니터링

---

## 🌐 GitHub Pages 배포 가이드 (GitHub Deployment)

이 저장소는 GitHub Pages를 통해 무료로 손쉽게 정적 웹사이트로 배포할 수 있도록 설정되어 있습니다.

### 1. 보안 점검 (OAuth 및 토큰 보호)
- `.gitignore` 파일에 개인 구글 OAuth 인증 정보(`credentials.json`, `token.json`)와 로그 파일들이 등록되어 있어 깃허브에 민감한 정보가 노출되지 않습니다.

### 2. 빌드 파일 생성 확인
- 최신 구글 시트 데이터를 정적 HTML에 반영하려면 아래 명령어를 실행합니다:
  ```bash
  python3 build_workout_dashboard.py
  ```
  *(루트의 `index.html`과 `workout_dashboard.html`에 최신 데이터가 반영됩니다.)*

### 3. GitHub 저장소 생성 및 푸시
1. [GitHub](https://github.com/)에 로그인 후 우측 상단의 **+ > New repository**를 클릭합니다.
2. 저장소 이름(예: `workout-dashboard`)을 입력하고 **Public**으로 생성합니다.
3. 터미널에서 아래 명령을 차례대로 실행하여 코드를 업로드합니다:
   ```bash
   git init -b main
   git add .
   git commit -m "feat: Deploy Workout Management Dashboard"
   git remote add origin https://github.com/<본인-깃허브-아이디>/<저장소-이름>.git
   git push -u origin main
   ```

### 4. GitHub Pages 활성화
1. 깃허브 저장소 페이지의 **Settings (설정)** 탭으로 이동합니다.
2. 좌측 메뉴에서 **Pages**를 클릭합니다.
3. **Build and deployment > Source** 옵션에서 다음 중 하나를 선택합니다:
   - **GitHub Actions (권장)**: 내장된 `.github/workflows/deploy.yml`이 동작하여 자동 배포됩니다.
   - 또는 **Deploy from a branch**: Branch를 `main`, 폴더를 `/(root)`로 지정하고 Save를 누릅니다.
4. 약 1~2분 후 상단에 표시되는 대시보드 URL로 접속합니다:
   - `https://<본인-깃허브-아이디>.github.io/<저장소-이름>/`


