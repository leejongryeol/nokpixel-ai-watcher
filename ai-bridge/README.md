# ai-bridge

게임과 생성형 AI를 연결하는 Python 프로그램입니다.

| 파일 | 역할 |
|---|---|
| `test_connection.py` | Claude API가 연결되는지 확인 |
| `mvp.py` | **MVP**: AI가 게임 화면을 보고 키보드·마우스로 플레이 (Windows 전용) |

## 준비

1. [Python 3.10 이상](https://www.python.org/downloads/) 설치 (설치할 때 **Add python.exe to PATH** 체크)
2. 이 폴더에서 필요한 라이브러리 설치
   ```bash
   pip install -r requirements.txt
   ```
3. [Claude Console](https://console.anthropic.com/)에서 API 키 발급 (크레딧 충전 필요)
4. `.env.example`을 복사해서 `.env`라는 이름으로 저장하고, 안에 API 키 입력
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```
   > ⚠️ `.env`는 `.gitignore`에 들어 있어서 GitHub에 올라가지 않아요. API 키를 다른 파일에 적지 마세요.

## 1. 연결 테스트

```bash
python test_connection.py
```

AI가 모험가처럼 한국어로 한마디 하면 성공이에요.

## 2. MVP 실행

1. 게임을 먼저 켜고, 던전 안까지 들어가 둡니다 (게임 창은 720×400으로 고정돼 있어요)
2. 다른 cmd 창에서:
   ```bash
   python mvp.py --dry-run          # AI가 화면을 보고 생각만 함 (조작 안 함). 처음엔 이걸로!
   python mvp.py --steps 10         # AI가 10번 판단하며 실제로 플레이
   ```
3. 멈추려면 cmd 창에서 `Ctrl + C`, 또는 **마우스를 화면 왼쪽 위 구석으로** 빠르게 옮기기

실행하면 판단마다 이렇게 나와요.
```
━━ 3번째 판단 ━━
🧠 생각: 오른쪽에 쥐가 다가오고 있다. 체력이 충분하니 먼저 공격하자.
💬 "덤벼라!"
🎮 행동: 키 d
🪙 토큰 입력 1210 / 출력 95 · 약 $0.0017 (누적 $0.005)
```

### 기록
`logs/run_날짜_시간/` 폴더에 판단마다 스크린샷(`step_001.png` …)과 `log.jsonl`(생각, 행동, 토큰, 비용)이 저장돼요. 나중에 관찰 화면과 리포트의 재료가 됩니다. 이 폴더는 GitHub에 올라가지 않아요.

### 모델 바꾸기
기본은 가장 저렴한 Haiku 4.5예요. `.env`에 한 줄 추가하면 바뀌어요.
```
MODEL=claude-sonnet-5-5
```

### MVP의 한계 (다음 단계에서 개선)
- AI는 **화면 이미지만** 봐요. 체력·메시지 같은 글 정보는 다음 단계에서 게임 코드로 추가할 예정
- 매번 최근 5개 판단만 기억해요 (요약·기억 메모 없음)
- 판단 순간 감지 없이 **매 행동마다** AI를 불러요
