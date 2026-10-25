# CLAUDE.md · 녹픽던 AI 관찰기 (nokpixel-ai-watcher)

Claude Code가 이 저장소에서 일할 때 따르는 규칙이다. claude.ai 프로젝트 지침과 같은 내용을, 로컬 개발(IntelliJ, VS Code, 터미널)용으로 정리했다.

## 0. 프로젝트 기준선
- 생성형 AI(Claude)가 Shattered Pixel Dungeon(녹픽던)을 플레이하고, 사용자는 **관찰만** 한다.
- 탐구 질문: "AI는 스스로 판단하는가, 아니면 아는 것을 꺼내 쓰는 것뿐인가?"
- 최종 목표: 5층 보스 "구(Goo)" 처치. 결과는 보스 처치 여부 + 도달 층 + 진행도 이정표로 기록한다.
- 범위: 2026-11-18 최종 발표까지. 기능 추가 마감 11/10, 최종 결과물 완성 11/14.
- 사용자는 대학생 개인 개발자다. 설명은 한국어로, 쉬운 말로 한다. 전문 용어는 처음 나올 때 한 줄로 풀어 쓴다.
- 사실과 계획을 섞지 않는다. 하지 않은 일, 확인하지 않은 동작, 돌려보지 않은 실험 결과는 지어내지 않는다.

## 1. 저장소 구조

| 경로 | 내용 |
|---|---|
| `core/`, `desktop/`, `SPD-classes/` | 녹픽던 원본 (Java, LibGDX). v4.0.2 포크, GPL-3.0 |
| `desktop/.../DesktopLauncher.java` | 유일한 원본 수정: 게임 창 720×400 고정 |
| `ai-bridge/agent.py` | AI 플레이어 핵심 (화면 캡처 → Claude 호출 → 키·클릭 → 기록) |
| `ai-bridge/web.py`, `ai-bridge/web/` | 관찰 웹 화면 (설정 → 관찰 → 리포트), 127.0.0.1:8765 |
| `ai-bridge/mvp.py` | 명령줄 실행 |
| `ai-bridge/guide.md` | "공략 제공" 조건에서 AI에게 주는 공략 초안 |
| `docs/project/architecture.md` | 현재 구조와 예정 구조, 사용할 게임 코드 지점 |
| `docs/project/decision-points.md` | `Hero.ready()` 기준 판단 요청 목록 |
| `docs/project/progress-milestones.md` | 진행도 이정표 (평가용) |

## 2. 실행 명령 (Windows)

```bat
:: 게임 실행 (Java 21 필요. 프로젝트 루트에서)
gradlew.bat desktop:debug

:: AI 쪽 준비 (ai-bridge 폴더에서, 처음 한 번)
pip install -r requirements.txt

:: 관찰 웹 화면: 데모 (게임·API 없이)
python web.py --demo

:: 관찰 웹 화면: 실제 플레이 (게임을 먼저 켜고 던전 안까지 들어간 뒤)
python web.py

:: 명령줄: 생각만 하고 조작 안 함
python mvp.py --dry-run --steps 10
```

- 녹픽던은 원래 모바일 게임이라 ESC가 "뒤로 가기"다. 타이틀 화면에서 누르면 게임이 꺼진다.
- 학교 PC(Java 17)에서는 빌드가 실패한다. Java 21을 쓴다.

## 3. 보안 (예외 없음)
- API 키는 `ai-bridge/.env`에만 둔다. **`.env`를 읽거나, 출력하거나, 커밋하지 않는다.** 실험 기록 `ai-bridge/logs/`도 커밋하지 않는다.
- `ANTHROPIC_API_KEY`를 시스템 환경 변수로 설정하라고 안내하지 않는다. 개발 비용이 API 크레딧으로 빠질 수 있다.
- 커밋 전에 `git status`와 diff를 확인해서 비밀 정보나 의도하지 않은 파일이 섞이지 않았는지 본다.

## 4. GitHub
- 사용하는 계정과 저장소는 `leejongryeol/nokpixel-ai-watcher` 하나뿐이다.
- **`20221000` 계정·조직에는 어떤 경우에도 연결하거나 접근하지 않는다.**
- 원본 `00-Evan/shattered-pixel-dungeon`은 읽기 전용 참고용이다. PR·이슈·푸시를 보내지 않는다.
- 기본 브랜치는 `master`다. 하나의 커밋에는 하나의 논리적 변경만 담는다.
- 커밋 메시지는 한국어로 쓴다. 첫 줄은 무엇을 했는지, 본문은 왜 했는지 bullet로 쓴다.
- force push, 이미 올라간 커밋 고치기(rebase·amend), 브랜치 삭제는 사용자 요청 없이 하지 않는다.
- 푸시는 사용자가 요청했을 때만 한다. 푸시한 뒤에는 커밋 해시를 알려준다.

## 5. 코드 변경 원칙
- **게임 코드(Java)는 연결 지점(hook)에 필요한 만큼만 최소로 고친다.** 원작의 게임 규칙이나 동작을 바꾸는 수정은 사용자와 먼저 합의한다.
- 게임 진행은 별도 스레드(actor thread)에서 돌아간다. 밖에서 명령을 넣을 때는 `ShatteredPixelDungeon.runOnRenderThread(...)` 등으로 렌더 스레드에서 처리하고, 주인공이 입력을 기다리는 상태(`Dungeon.hero.ready`)인지 확인한다.
- 칸 이동·공격·줍기·계단은 `Hero.handle(cell)` + `Dungeon.hero.next()`로 처리한다. 사용자가 칸을 클릭할 때와 같은 경로다(`GameScene`의 기본 셀 리스너).
- **AI에게는 화면에 보이는 정보만 준다.** 안 가본 칸, 숨겨진 문·함정(`Terrain.SECRET` 표시가 붙은 지형), 미감정 아이템의 정체, 시드는 AI 입력에 넣지 않는다.
- 실험 조건(모델, 공략 유무, 교훈 이어받기, 시드)을 바꾸는 수정은 기존 기록과 비교할 수 있는지 먼저 확인한다. 비교가 깨지면 사용자에게 알린다.
- 코드를 바꾸면 같은 커밋에서 관련 문서(`README.md`, `ai-bridge/README.md`, `docs/project/*.md`)를 함께 고친다.
- 하지 않은 일은 문서에 ⬜/예정으로 표시한다. ✅는 실제로 확인한 것에만 붙인다.

## 6. 검증
- Java를 바꿨다면 `gradlew.bat desktop:debug`로 빌드·실행까지 확인한다. 빌드 오류는 원인을 설명한 뒤 고친다.
- Python을 바꿨다면 `python web.py --demo` 또는 `python mvp.py --demo`로 흐름을 확인한다.
- 화면(HTML·CSS·JS)을 바꿨다면 해당 페이지를 실제로 띄워서 확인한다.
- 확인하지 못한 것은 "미확인"이라고 명시한다.
- 실제 API를 부르는 실행은 비용이 든다. 사용자가 요청할 때만 하고, 처음에는 Haiku와 `--dry-run`으로 짧게 돌린다.

## 7. 노션 개발 일지 (노션을 쓸 수 있을 때)
- 페이지: "인공지능프로젝트-개별프로젝트-". 수정 전에 최신 내용을 다시 읽는다.
- **덧붙이기만 한다.** 지난 날짜의 기록, 9/30 기획 원문, 기존 표와 이미지는 수정하거나 삭제하지 않는다.
- 새 작업일에는 개발 일지 표 맨 위에 행을 추가하고, `## 이모지 YYYY.MM.DD · 제목` 토글을 만든다.
- 코드 작업을 기록할 때는 커밋 링크를 붙이고, 실험 결과는 실제 기록이 있는 것만 쓴다.
