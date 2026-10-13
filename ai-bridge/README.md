# ai-bridge

게임과 생성형 AI를 연결하는 Python 프로그램입니다. 지금은 **API 연결 확인용 테스트**만 들어 있어요.

## 준비

1. [Python 3.10 이상](https://www.python.org/downloads/) 설치
2. 이 폴더에서 필요한 라이브러리 설치
   ```bash
   pip install -r requirements.txt
   ```
3. [Claude Console](https://console.anthropic.com/)에서 API 키 발급
4. `.env.example`을 복사해서 `.env`라는 이름으로 저장하고, 안에 API 키 입력
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```
   > ⚠️ `.env`는 `.gitignore`에 들어 있어서 GitHub에 올라가지 않아요. API 키를 다른 파일에 적지 마세요.

## 연결 테스트

```bash
python test_connection.py
```

AI가 녹픽던 캐릭터처럼 한국어로 한마디 하면 성공이에요.

## 앞으로 추가할 것

| 파일 | 역할 | 예정 |
|---|---|---|
| `state_to_text.py` | 게임 상태(JSON)를 AI용 텍스트로 변환 | 7주차 |
| `brain.py` | AI에게 판단을 요청하고 행동 + 이유를 받음 | 8주차 |
| `logger.py` | 판단 기록 저장 (관찰 화면, 리포트용) | 8~9주차 |
