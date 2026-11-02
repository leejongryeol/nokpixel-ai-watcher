# 게임 ↔ Python 연결 설계 (AI 설정 장면)

> [A-5-1] 설계 문서. 이 문서대로 A-5-2부터 만든다.
> **A-5-2(AI 설정 장면, 값 기억만)는 만들었다** (10/31). 실제로 만든 것과 설계와 다른 점은 9장 "A-5-2 결과".
> **A-5-3(값 전달 + `config.json` 자동 기록)을 만들었다** (11/2). 9장 "A-5-3 결과". 던전 도착 뒤 AI 자동 시작(A-5-4)은 아직이다.

캐릭터 선택 화면 뒤에 게임 안 **"AI 설정" 장면**을 넣어, 게임에서 설정을 고르고 바로 AI 판을 시작하게 한다. 지금은 사람이 던전까지 들어간 뒤 관찰 패널에서 AI를 따로 시작한다.

**표기**
- ✅ 코드를 읽어서 확인한 것
- 💭 설계안 (아직 만들지 않음)
- ⬜ 미확인 (만들 때 확인해야 함)

---

## 0. 조사 결과 요약 (코드 읽기만)

경로는 `core/src/main/java/com/shatteredpixel/shatteredpixeldungeon/` 기준이다.

| # | 조사 항목 | 결과 |
|---|---|---|
| 1 | 캐릭터 선택의 시작 버튼 | ✅ `scenes/HeroSelectScene.java:150-164`. 순서: `selectedClass`가 없으면 무시 → `Dungeon.hero = null` → `Dungeon.daily = dailyReplay = false` → `Dungeon.initSeed()` → `ActionIndicator.clearAction()` → `InterlevelScene.mode = DESCEND` → `Game.switchScene(InterlevelScene.class)` |
| | 일일 도전 | ✅ 같은 화면의 일일 도전 버튼(`:752-758`)은 위 순서를 따로 실행해 바로 시작한다 |
| | 뒤로 가기 | ✅ `onBackPressed()`(`:557-563`)는 타이틀로 간다. `create()`가 `GamesInProgress.selectedClass`(static)를 다시 골라 주므로(`:391-392`) 다른 장면에서 돌아와도 고른 캐릭터가 남는다 |
| 2 | 캐릭터 | ✅ `GamesInProgress.selectedClass` (`HeroClass`) |
| | 제약(도전 모드) | ✅ `SPDSettings.challenges()` (9가지 비트 묶음, `Challenges.MASKS`·`NAME_IDS`). 판 시작 때 `Dungeon.init()`이 `Dungeon.challenges`로 복사(`Dungeon.java:236`) |
| | 시드 | ✅ `SPDSettings.customSeed()` (빈 글 = 무작위). 실제 시드는 `Dungeon.initSeed()`(`Dungeon.java:217-231`) 뒤의 `Dungeon.seed` |
| | 주의 | ✅ VICTORY 배지가 없고 디버그 실행이 아니면, 캐릭터 선택 화면이 제약·시드를 지운다(`HeroSelectScene.java:236-240`). `gradlew.bat desktop:debug`는 버전에 `INDEV`가 붙어 `DeviceCompat.isDebug()`가 참이라 지금 방식에서는 쓸 수 있다 |
| 3 | 던전 도착 | ✅ 로딩이 끝나면 `InterlevelScene.java:523`에서 `Game.switchScene(GameScene.class)`. `GameScene.create()`에서 `Dungeon.hero.next()`(`:612`) → 층 도착 메시지(`:626-629`) → `InterlevelScene.mode = NONE`(`:742`) → `fadeIn()`(`:779`) |
| | 주의 | ✅ `GameScene.create()`는 층을 옮기거나 이어하기를 할 때마다 불린다. "이번 판의 첫 도착"을 따로 구분해야 한다 (→ 3장) |
| | 주의 | ✅ 첫 판(`SPDSettings.intro()`)이면 튜토리얼이 툴바·상태창을 숨긴다(`GameScene.java:748-765`). ⬜ AI 첫 판에 주는 영향 |
| 4 | 가려서 입력 | ✅ `windows/WndTextInput`에는 가리기 옵션이 없다. 안쪽 `SPD-classes/.../noosa/TextInput.java`는 libGDX `TextField`를 `private`으로 들고 있어서 밖에서 켤 수 없다. libGDX `TextField`에는 `setPasswordMode`·`setPasswordCharacter`가 있다 → **`TextInput`에 메서드 하나를 더해야 한다** (게임 엔진 쪽 수정, A-5-2에서 합의) |
| | | ⬜ 가림 글자가 게임 글꼴로 그려지는지 (`TextInput.java:120`은 실제 입력 글자로 글꼴을 만든다), 데스크톱에서 Ctrl+V 붙여넣기 |
| 5 | 화면 글자 | ✅ `Messages.get(클래스, 키)`가 `assets/messages/scenes/scenes.properties`(영어 기본)와 `scenes_ko.properties`(한국어)에서 `scenes.<클래스 이름 소문자>.<키>`를 찾는다 (예: `scenes.heroselectscene.start=시작`). 한국어 파일에 없으면 영어 값이 나온다 |
| 6 | 지금 판 시작 흐름 | ✅ 사람이 던전까지 들어감 → 관찰 패널 `POST /api/console/start`(또는 설정 화면 `POST /api/start`) → `Agent(...)` → `config.json` |
| | `config.json` | ✅ player, model, model_name, guide, lessons_from, seed(관찰자가 적은 글, 게임과 연결 안 됨), steps, dry_run, demo, started_at, 첫 판단 뒤 display·game_window·ai_image |
| | 키 저장 | ✅ `/api/start`는 키와 함께 **`MODEL`도 `.env`에 쓴다** (`web.py`의 `set_key(ENV_PATH, "MODEL", ...)`). 4장 원칙과 다르다 (→ 8장) |
| 7 | 통로 재료 | ✅ 게임은 이미 libGDX `Gdx.net.sendHttpRequest`로 HTTP를 쓴다 (`services/news/.../ShatteredNews.java:54`). 결과는 다른 스레드에서 오므로 렌더 스레드로 넘겨야 한다. Python에는 `web.py`(Flask, 127.0.0.1:8765)가 이미 있다. Java 11 기준(`build.gradle:21`) |

---

## 1. 새 흐름도

```mermaid
flowchart TD
    T[타이틀] --> H[캐릭터 선택<br/>캐릭터·제약·시드를 정함]
    H -- 시작 --> A[AI 설정 💭 새 장면]
    H -- 일일 도전 --> L
    A -- "뒤로 / ESC" --> H
    A -- "AI 없이 시작<br/>(원작과 같은 순서)" --> L[로딩<br/>InterlevelScene]
    A -- "AI로 시작<br/>(키 연결 확인 뒤에만)" --> S[Python에 판 설정 보냄<br/>대기 중 AI 판 표시]
    S --> L
    L --> G[던전<br/>GameScene]
    G -- "대기 중 AI 판이 있으면<br/>한 번만" --> R[Python에 던전 도착 알림<br/>→ AI 시작]
    G -- 대기 중 AI 판 없음 --> P[사람이 플레이<br/>원작 그대로]
    R --> E[판 끝: 사망·승리·타이틀로 나감<br/>→ Python에 알림]
```

- 💭 캐릭터 선택의 **시작** 버튼은 `initSeed()` 등을 하지 않고 AI 설정 장면으로 넘어가기만 한다. AI 설정 장면의 두 시작 버튼이 0장 1번의 순서를 그대로 실행한다. **AI 없이 시작**은 그 순서만 실행하므로 원작과 같다.
- 💭 **AI로 시작**은 같은 순서를 실행하기 전에 판 설정을 Python에 보내고 "대기 중 AI 판" 표시를 남긴다. 보내기가 실패하면 시작하지 않고 장면에 머물며 안내한다 (5장).
- 💭 **뒤로·ESC**는 캐릭터 선택으로 돌아간다. 캐릭터는 그대로 남는다 (✅ 0장 1번).
- 이번 범위 밖: **일일 도전**과 **이어하기**(저장된 판 불러오기)는 AI 설정을 거치지 않고 원작대로 동작한다.

---

## 2. AI 설정 장면 화면 구성

세로 360×640 창(배율 ×2, 게임 안 좌표 180×320) 기준이다. 💭 아래 그림은 배치안이고 실제 크기는 만들면서 맞춘다.

```
┌──────────────────────────────┐
│          AI 설정              │
│ 전사 · 제약 없음 · 시드 무작위  │ ← 읽기 전용 (캐릭터 선택에서 정함)
├─ 매번 보는 것 ────────────────┤
│ 모델   [ GPT-6 Luna      ▾ ] │
│ 공략   (●) 없이  ( ) 제공      │
│ API 키 ●●●●●●●●abcd           │
│        ✅ 연결됨 (12초 전)     │
│        [키 입력]  [연결 시험]  │
├─ 실험 옵션 ───────────────────┤
│ 판 방식 (●) 생각만 ( ) 실제 조작│
│ 최대 판단  [ 50 ]             │
│ 교훈 이어받기 [ 없음      ▾ ]  │
│ 플레이어   [ player    ]      │
├───────────────────────────────┤
│ [   AI로 시작   ] ← 연결 전 회색│
│ [  AI 없이 시작  ]             │
│ [ 뒤로 ]                      │
│ 안내: 키를 넣고 연결 시험을 …   │ ← 5장 문구가 나오는 자리
└──────────────────────────────┘
```

| 항목 | 내용 | 기본값 | 기억 |
|---|---|---|---|
| 캐릭터·제약·시드 | 읽기 전용 한 줄. 제약은 개수만 (예: "제약 2개") | – | – |
| 모델 | Python에서 받은 목록 (6장). 못 받으면 회색 | 지난번 값 | ✅ |
| 공략 | 없이 / 제공 | 없이 | ✅ |
| API 키 | 끝 4자리 + 상태 + [키 입력] [연결 시험] (4장) | – | **저장 안 함** |
| 판 방식 | (A-5-3 뒤 없앰: 게임에서 시작하는 판은 언제나 실제 조작, 9장) 생각만 / 실제 조작. **실제 조작은 빨간 글자와 테두리**로 표시하고, [AI로 시작] 글자도 "AI로 시작 · 실제 조작"으로 바꾼다 | **생각만** | ✅ |
| 최대 판단 | 1~500 | 50 | ✅ |
| 교훈 이어받기 | Python에서 받은 교훈 목록. 못 받으면 "없음"만 | 없음 | ✅ (목록에 없으면 "없음") |
| 플레이어 | 기록 폴더 이름에 쓰는 이름 | player | ✅ |

- 💭 **[AI로 시작]이 눌리는 조건**: Python이 켜져 있음 + 고른 모델의 키 연결 시험이 성공함 (6장의 `key.tested_ok`). 설정을 바꿔서 회사가 달라지면 다시 회색이 된다.
- 💭 **[AI 없이 시작]과 [뒤로]는 언제나 눌린다.**
- 💭 **기억하는 곳**: 게임 설정(`SPDSettings`)에 `ai_model`, `ai_guide`, `ai_dry_run`, `ai_steps`, `ai_lessons_from`, `ai_player`로 저장한다. API 키는 어디에도 저장하지 않는다.
- 💭 판 방식을 기억하더라도, 지난번에 "실제 조작"이었으면 장면을 열 때 안내 줄에 "지난번 판은 실제 조작이었어요"를 한 번 보여 준다. 실수로 실제 조작 판을 시작하지 않게 하려는 것이다.

---

## 3. 게임 ↔ Python 약속

### 3-1. 주고받는 값

모두 JSON이다. 💭 주소는 `web.py`에 `/api/bridge/...`로 새로 만든다.

**① 상태 조회** `GET /api/bridge/status` (게임 → Python, 장면을 열 때와 3초마다)
```json
{
  "bridge_version": 1,
  "running": false,
  "models": [
    {"id": "gpt-6-luna", "name": "GPT-6 Luna", "provider": "openai"},
    {"id": "claude-haiku-4-5-20251001", "name": "Haiku 4.5", "provider": "anthropic"}
  ],
  "keys": {
    "openai":    {"present": true,  "last4": "abcd", "tested_ok": true,  "tested_at": "2026-11-02T14:03:11"},
    "anthropic": {"present": false, "last4": "",     "tested_ok": false, "tested_at": ""}
  },
  "lesson_sources": [
    {"run_id": "run_20261025_225713_live10", "label": "10/25 · GPT-6 Luna · 10판단"}
  ]
}
```

**② 키 보내기** `POST /api/bridge/key` (게임 → Python, [키 입력]에서 확인을 누를 때)
```json
요청 {"provider": "openai", "key": "sk-…(전체 키)"}
응답 {"ok": true, "last4": "abcd"}
```

**③ 연결 시험** `POST /api/bridge/test` (게임 → Python, [연결 시험])
```json
요청 {"model": "gpt-6-luna"}
응답 {"ok": false, "reason": "key_invalid", "message": "키가 맞지 않아요"}
```
`reason` 값: `ok`, `no_key`, `key_invalid`, `no_credit`, `model_unavailable`, `timeout`, `other`. 게임은 `reason`을 보고 5장의 문구를 고른다.

**④ 판 설정 확정** `POST /api/bridge/run` (게임 → Python, [AI로 시작])
```json
요청 {
  "player": "player", "model": "gpt-6-luna", "guide": false, "dry_run": false,
  "steps": 50, "lessons_from": "",
  "hero_class": "WARRIOR", "hero_title": "전사",
  "challenges": 0, "challenge_names": [], "challenge_titles": [], "custom_seed": ""
}
응답 {"ok": true, "run_id": "run_20261102_140501_player"}
```
Python은 `Agent`를 만들어 두기만 하고 **아직 시작하지 않는다** (대기 판). `config.json`도 이때 쓴다 (A-5-3). ⑤가 오면 시작한다 (A-5-4).
`hero_title`·`challenge_titles`는 게임 화면에 보이는 언어 그대로의 이름이다 (A-5-4). AI 입력의 `[이번 판]`에 쓴다 (7장).

**⑤ 던전 도착** `POST /api/bridge/arrived` (게임 → Python, [AI로 시작]한 판의 첫 `GameScene`에서 한 번만)
```json
요청 {"run_id": "run_20261102_140501_player", "depth": 1, "seed_code": "ABC-DEF-GHI"}
응답 {"ok": true}
```
- 보내는 때: 장면이 생기고 1.2초가 지났고(화면이 밝아지는 효과가 1초), `Dungeon.hero.ready`가 참이고, `InterlevelScene.mode == NONE`일 때. 1층이 아니면 보내지 않는다.
- Python은 실제 시드(`seed_code`)와 도착 층(`arrival_depth`)을 **`config.json`에만** 더하고 AI를 시작한다. 시드는 AI 입력에 넣지 않는다 (7장).
- `run_id`가 대기 판과 다르면 `not_pending`(409), 다른 판이 진행 중이면 `running`(409).

**⑥ 판 끝** `POST /api/bridge/ended` (게임 → Python)
```json
요청 {"run_id": "run_20261102_140501_player", "reason": "died", "depth": 3}
```
보내는 곳은 모두 `GameScene` 안 두 곳이다 (A-5-4에서 정함). `Hero`·`Dungeon`·`WndGame`은 고치지 않았다.

| `reason` | 지점 | 근거 |
|---|---|---|
| `died` | `GameScene.gameOver()` | `Hero.die()` → `reallyDie()` → 렌더 스레드에서 `gameOver()`. 앙크가 있으면 부르지 않는다 (부활 창) |
| `won` | `GameScene.destroy()`에서 `Statistics.gameWon`이 참 | `Dungeon.win()`이 `gameWon`을 켠 뒤 장면을 바꾼다 |
| `quit` | `GameScene.destroy()`에서 `InterlevelScene.mode == NONE` | 층을 옮길 때는 늘 `NONE`이 아닌 값으로 정한 뒤 장면을 바꾼다. 타이틀로 나가기·게임 창 닫기는 `NONE` |

- 게임 창을 닫을 때도 `quit`이 간다. 하지만 곧바로 프로그램이 끝나서 닿을지 보장이 없다. Python은 1초 뒤 게임 창이 없으면 `game_closed`로 바꿔 적는다. 닿지 않으면 ⑦이 끊겨서 멈춘다.
- `reason`이 위 셋이 아니면 `bad_reason`(400), `run_id`가 진행 중 판과 다르면 `not_running`(409).
- 한계: 아뮬렛 장면(26층)으로 갈 때도 `quit`으로 보일 수 있다. 목표가 5층이라 다루지 않았다.

**⑦ 살아 있음 신호** `POST /api/bridge/heartbeat` (게임 → Python, AI 판 동안 1초마다, A-5-4)
```json
요청 {"run_id": "run_20261102_140501_player", "alive": true, "depth": 2}
응답 {"ok": true}
```
- ⑤가 성공한 뒤부터 `GameScene`에 있는 동안 보낸다. 주인공이 죽은 것을 처음 보면 1초를 기다리지 않고 바로 `alive: false`를 보낸다.
- 응답이 `ok: false`(판이 이미 끝남, 관찰기를 다시 켬)면 게임은 신호를 멈춘다. 3번 연달아 실패하면(관찰기가 꺼짐) 신호를 멈추고 기록창에 한 줄 띄운다. 게임은 그대로 진행한다.
- Python은 키·클릭 하나를 보내기 **직전마다** 확인한다 (`Agent._guard()`): 중지됐으면 멈춤 → 마지막 신호가 `alive: false`면 `died` → 신호가 3초 넘게 없으면 키를 보내지 않고 기다림(층 이동 로딩일 수 있음) → 게임 창이 없어졌으면 `game_closed` → 30초가 지나면 `lost_game`. 게임 창이 맨 앞일 때만 키를 보내는 기존 확인은 그대로다.

### 3-2. 방향과 시점

| 시점 | 방향 | 내용 | 실패하면 |
|---|---|---|---|
| AI 설정 장면을 열 때, 그 뒤 3초마다 | 게임 → Python | ① 상태 조회 (Python→게임에 필요한 모델 목록·키 상태·시험 결과·교훈 목록을 이 응답으로 받음) | "Python이 꺼져 있어요" 안내, 모델·교훈 고르기 회색, [AI로 시작] 회색 |
| [키 입력] 확인 | 게임 → Python | ② 키 보내기 | 키는 버리고 안내 |
| [연결 시험] | 게임 → Python | ③ 연결 시험 (최대 30초) | 결과에 맞는 안내 |
| [AI로 시작] | 게임 → Python | ④ 판 설정 확정 | 시작하지 않고 장면에 머묾 |
| 던전 도착 (그 판의 첫 번째만) | 게임 → Python | ⑤ 던전 도착 | 게임은 그대로 진행, 게임 기록창에 "AI가 시작되지 않았어요. 직접 플레이할 수 있어요." 한 줄 |
| 판 끝 (사망·승리·타이틀로 나가기·창 닫기) | 게임 → Python | ⑥ 판 끝 | 무시. 닿지 않아도 ⑦이 끊겨서 Python은 키를 보내지 않는다 |
| AI 판 동안 1초마다 | 게임 → Python | ⑦ 살아 있음 신호 | 3번 연달아 실패하면 신호를 멈추고 기록창에 "AI 관찰기와 연결이 끊겼어요. 직접 이어서 할 수 있어요." 한 줄 |

Python이 게임에 먼저 말을 거는 일은 없다. 게임이 물으면 Python이 답한다.

### 3-3. 통로 방식 비교

| 방식 | 구현 난이도 | 한쪽이 꺼져 있을 때 | 시험 방법 |
|---|---|---|---|
| **A. 파일** (게임이 `bridge/request.json`을 쓰고 Python이 읽음) | 쉬움. 대신 두 프로그램이 파일 위치를 같이 알아야 하고, 반쯤 쓴 파일 읽기·오래된 파일 지우기를 직접 처리 | 응답이 안 옴 → 기다릴 시간을 정해야 함. 꺼져 있는지 바로 알 수 없음 | 파일을 손으로 만들어 넣어 봄 |
| **B. 게임 → Python 로컬 HTTP** (`web.py`에 주소 추가) | 쉬움. 게임에 이미 `Gdx.net`(✅ 0장 7번), Python에 이미 Flask | 요청이 바로 실패 → "Python이 꺼져 있어요" 안내. 게임은 멈추지 않음 | `curl`로 Python 쪽만 따로 시험, 게임 없이 가능 |
| C. Python → 게임 로컬 HTTP (게임이 서버) | 어려움. 게임 안에 서버를 띄우고 받은 요청을 렌더 스레드로 넘겨야 함. 게임 코드 수정이 큼 | 게임이 꺼져 있으면 Python만 실패 | `curl`로 게임 쪽 시험 |
| D. 소켓 (TCP로 직접) | 중간~어려움. 메시지 경계·재연결을 직접 만들어야 함 | 연결 실패를 바로 앎. 끊김 처리를 직접 만들어야 함 | 시험용 도구를 따로 만들어야 함 |

**추천: B (게임이 Python의 `web.py`에 로컬 HTTP로 묻는다)**
- 두 쪽 모두 이미 있는 도구라 새 프로그램이 필요 없다.
- 게임 코드 수정이 가장 작다. 게임은 묻고 답만 받는다. 게임 규칙에 손대지 않는다.
- Python이 꺼져 있으면 요청이 바로 실패하므로 안내만 띄우면 된다. 게임은 멈추지 않는다.
- 게임 없이 `curl`로 Python 쪽을 먼저 만들고 시험할 수 있다.
- 💭 주소는 `http://127.0.0.1:8765` 고정. 바꿀 일이 생기면 실행 옵션으로 추가한다.
- 💭 **다른 웹사이트가 몰래 요청하지 못하게**: 브라우저에서 열린 아무 페이지나 `127.0.0.1:8765`에 요청을 보낼 수 있다. 그래서 `/api/bridge/*`는 `X-Nokpixel-Bridge: 1` 헤더가 있고 내용이 JSON인 요청만 받는다. 이 조합이면 브라우저는 먼저 허락을 묻고(사전 요청), Flask가 허락하지 않으므로 막힌다. A-5-3에서 상태를 바꾸는 기존 주소(중지, 힌트, 창 배치 등)에도 같이 적용했다 (9장).

---

## 4. API 키 처리

| 원칙 | 방법 |
|---|---|
| 입력할 때 가린다 | 💭 `TextInput`에 가리기 메서드를 하나 더하고, 키 입력 창에서만 켠다 (0장 4번. ⬜ 가림 글자 표시, ⬜ Ctrl+V) |
| 게임은 저장하지 않는다 | 💭 입력받은 키는 ② 키 보내기에만 쓰고 바로 버린다. `SPDSettings`·저장 파일·게임 로그에 넣지 않는다. 입력 창에도 이전 키를 채워 두지 않는다 |
| Python이 `.env`에만 저장한다 | 💭 ②를 받으면 `ai-bridge/.env`에 `OPENAI_API_KEY` 또는 `ANTHROPIC_API_KEY` **한 줄만** 쓴다. 모델 등 다른 값은 쓰지 않는다 |
| 화면에는 끝 4자리와 시험 결과만 | 💭 Python은 `last4`만 돌려준다. 키 전체를 돌려주는 주소는 만들지 않는다 |
| 기록에 남지 않는다 | 💭 `config.json`·`log.jsonl`·`summary.txt`·관찰 패널 응답에 키가 들어가지 않는다. Flask 기본 접속 기록은 주소만 남기고 본문은 남기지 않는다 (⬜ 만들 때 실제 출력으로 확인). 오류 문구에 키가 섞이지 않게, 연결 시험 실패는 `reason`으로 바꿔서만 돌려준다 |
| 키가 지나가는 범위 | 같은 컴퓨터 안(127.0.0.1)에서만 지나간다. 암호화는 하지 않는다. 같은 컴퓨터의 다른 프로그램이 엿볼 수 있는 정도의 위험은 지금의 `.env` 파일과 같다 |

---

## 5. 안내 문구

원칙: 사용자가 **무엇을 하면 되는지** 말한다. "파일을 확인하세요" 같은 문장은 쓰지 않는다. **어떤 경우에도 게임은 멈추거나 꺼지지 않고, [AI 없이 시작]은 언제나 눌린다.**

| 상황 | 알아채는 방법 | 안내 문장 | 버튼 |
|---|---|---|---|
| Python이 꺼져 있음 | ① 요청이 바로 실패 | "AI 관찰기가 꺼져 있어요. `ai-bridge` 폴더에서 `python web.py`를 실행하면 자동으로 이어져요." | [다시 확인] [AI 없이 시작] |
| 키 없음 | ①의 `present: false` | "OpenAI API 키가 아직 없어요. [키 입력]을 눌러 붙여 넣어 주세요." (회사 이름은 고른 모델에 맞춤) | [키 입력] |
| 키 틀림 | ③ `key_invalid` | "키가 맞지 않아요. 키를 처음부터 끝까지 다시 복사해서 넣어 주세요." | [키 입력] [연결 시험] |
| 크레딧 부족 | ③ `no_credit` | "키는 맞지만 남은 크레딧이 없어요. 결제 페이지에서 충전한 뒤 [연결 시험]을 눌러 주세요." | [연결 시험] |
| 모델 사용 불가 | ③ `model_unavailable` | "이 키로는 GPT-6 Luna를 쓸 수 없어요. 다른 모델을 골라 주세요." | 모델 고르기로 이동 |
| 시간 초과 | ③ `timeout` | "AI 서버가 30초 안에 답하지 않았어요. 인터넷 연결을 본 뒤 [연결 시험]을 다시 눌러 주세요." | [연결 시험] |
| 연결 끊김 (장면에 있는 동안) | 3초마다 하는 ①이 실패 | "AI 관찰기와 연결이 끊겼어요. `python web.py` 창이 켜져 있는지 봐 주세요. 다시 켜지면 자동으로 이어져요." | [다시 확인] [AI 없이 시작] |
| [AI로 시작] 실패 | ④ 실패 | "AI 판을 준비하지 못했어요. 잠시 뒤 다시 눌러 주세요. 지금 바로 하려면 [AI 없이 시작]을 누르세요." | [AI로 시작] [AI 없이 시작] |
| 다른 판이 진행 중 | ①의 `running: true` | "관찰기에서 다른 판이 아직 진행 중이에요. 관찰 패널에서 중지한 뒤 시작해 주세요." | [다시 확인] |

💭 문장은 `scenes_ko.properties`에 한국어로, `scenes.properties`에 영어로 함께 넣는다 (0장 5번).

---

## 6. 모델 목록 한 곳에서 관리하기

**추천: Python(`ai-bridge/agent.py`의 `MODELS`)이 유일한 원본이고, 게임은 ① 상태 조회로 받아 온다.**
- AI 판을 돌리는 것은 Python이므로 Python이 아는 목록이 곧 쓸 수 있는 목록이다.
- 모델을 더하거나 뺄 때 Python 한 곳만 고치면 된다. 게임은 다시 빌드할 필요가 없다.
- Python이 꺼져 있으면 어차피 AI로 시작할 수 없으므로, 모델 고르기도 회색이면 된다. 지난번 고른 모델 이름은 회색 글자로 보여 준다.

| 대안 | 고르지 않은 이유 |
|---|---|
| 공용 JSON 파일(예: `ai-bridge/models.json`)을 게임과 Python이 각자 읽음 | 게임이 저장소 안 파일 위치를 알아야 한다 (실행 위치에 따라 달라짐). 게임 배포본에서는 깨진다 |
| Java와 Python에 같은 목록을 따로 적음 | 지금처럼 `DISPLAY_PRESETS`·`AI_WINDOW_PRESETS`를 두 곳에 두면, 한쪽만 고치는 실수가 생긴다 |

---

## 7. AI에게 주지 않을 정보

원칙: **플레이어 화면에 보이는 것만 준다.** (CLAUDE.md 5장)

| 값 | AI 입력에 | 이유 |
|---|---|---|
| 시드 (`custom_seed`, 실제 `seed_code`) | ❌ 넣지 않음. `config.json`에만 기록 | 시드는 맵을 미리 알게 해 주는 값이다. 사람도 게임 중에는 시드로 맵을 알 수 없다. 기록에는 같은 던전을 다시 만들려고 남긴다 |
| 캐릭터 (`hero_class`) | ✅ 넣음 (예: "직업: 전사") | 캐릭터 그림, 상태창의 초상화로 화면에 늘 보인다. 사람도 알고 시작한다 |
| 제약 (`challenges`) | ✅ 켜진 제약의 **이름만** 넣음 (예: "제약: 어둠 속으로"). 없으면 넣지 않음 | 게임 안 메뉴에서 플레이어가 언제든 볼 수 있다 (✅ `ui/MenuPane.java:133`, `windows/WndGame.java:70`). 규칙이 바뀌는데 모르면 사람보다 불리하다. 제약의 자세한 설명은 넣지 않는다 (공략에 가까움) |
| 공략 여부·교훈 | 지금과 같음 | 공략 제공·교훈 이어받기는 실험 조건으로 이미 따로 넣고 있다 |

💭 **실험 비교 주의**: README의 실험 조건은 "직업 전사, 도전 모드 끔"으로 고정이다. 캐릭터·제약 줄을 AI 입력에 더하면 프롬프트가 바뀌므로, 이 줄이 들어간 판과 이전 판은 조건이 다르다. 전사·제약 없음으로 고정할 거라면 이 줄을 넣지 않는 선택도 있다 (10장 남은 질문).

→ A-5-4 오더에서 합의해 **게임에서 시작한 판에만** 넣었다. 규칙 바로 뒤, 공략·교훈 앞에 아래 블록이 붙는다. 제약이 없으면 `제약:` 줄이 없다. `mvp.py` 판은 그대로다. 두 판은 `config.json`의 `started_from: "game"`으로 구분한다.
```
[이번 판]
직업: 전사
제약: 다이어트 중, 어둠 속으로
```

---

## 8. 관찰 패널과 역할 나누기

**설정의 주인은 게임 안 AI 설정 장면이다.** 관찰 패널은 읽기 전용으로 보여 주고, 판 진행 중에 필요한 것만 남긴다.

| 지금 패널에 있는 것 | 제안 |
|---|---|
| 실험 설정 칸 (플레이어, 모델, 생각만/실제, 최대 판단, 공략, 교훈, 시드) | 💭 **읽기 전용 요약**으로 바꾼다: "GPT-6 Luna · 공략 없이 · 생각만 · 50판단 · 전사 · 제약 없음 · 시드 ABC-DEF-GHI". 고치는 칸은 없앤다 |
| ▶ 시작 버튼 | 💭 없앤다. 그 자리에 "게임의 AI 설정에서 시작해요" 안내 |
| ■ 중지, ⊞ 창 배치, 게임 창 앞으로, 힌트 보내기, 기록 창 열기 | 그대로 둔다 (판 진행 중에 쓰는 것) |
| `/api/console/start` | 💭 ④ 판 설정 확정으로 대신하고 없앤다 |
| 설정 화면(`/`)과 `/api/start` | 💭 데모 모드(`--demo`)에서만 쓰는 시연용으로 남긴다. 실제 판에서는 게임에서 시작한다. `.env`에 `MODEL`을 쓰는 부분은 없앤다 (4장 원칙). → A-5-3에서 합의대로 했다 (9장) |
| `mvp.py` (명령줄) | 그대로 둔다. 게임 밖에서 바로 시험할 때 쓴다 |

---

## 9. 다음 단계 범위

| 단계 | 하는 일 | 끝났다는 기준 |
|---|---|---|
| **A-5-2** AI 설정 장면 (값 저장만, 전달 없음) | 새 장면, 캐릭터 선택 → AI 설정 → 로딩 흐름, 두 묶음 화면, 가려서 키 입력, 값 기억(키 제외), 한국어·영어 문구 | `desktop:debug`에서 캐릭터 선택 → AI 설정 → [AI 없이 시작]이 원작과 같이 던전에 들어가고, [뒤로]·ESC로 캐릭터 선택에 돌아가며, 고른 값이 다음 실행에 남는다 (키는 남지 않는다) |
| **A-5-3** 값 전달 + `config.json` 자동 기록 | `web.py`의 `/api/bridge/*`(①~④), 게임의 HTTP 요청, 키 `.env` 저장, 연결 시험, 안내 문구, 관찰 패널 읽기 전용 | Python을 켜고 게임에서 키 입력·연결 시험·[AI로 시작]을 하면 `config.json`이 게임에서 고른 값으로 생기고, Python을 끈 상태에서도 게임이 멈추지 않고 [AI 없이 시작]이 된다 |
| **A-5-4** 던전 도착 신호 → AI 시작 | ⑤ 던전 도착(첫 도착만 구분), 실제 시드 기록, AI 판 자동 시작, ⑥ 판 끝 | [AI로 시작]만 누르면 던전 1층 도착 뒤 사람이 아무것도 누르지 않아도 AI가 첫 판단을 하고, 층을 옮겨도 AI 판이 새로 시작되지 않는다 |

### A-5-2 결과 (10/31)

**고친 게임 파일**
| 파일 | 내용 |
|---|---|
| `scenes/AISetupScene.java` (새 파일) | AI 설정 장면 |
| `scenes/HeroSelectScene.java` | [시작]은 AI 설정 장면으로 넘어가기만 한다. 원래 시작 순서 6줄은 [AI 없이 시작]으로 글자 그대로 옮겼다 |
| `SPDSettings.java` | `ai_model`, `ai_guide`, `ai_dry_run`, `ai_steps`, `ai_lessons_from`, `ai_player` 저장 (API 키 항목은 없음) |
| `SPD-classes/.../noosa/TextInput.java` | `setPasswordMode()` 추가. 가림 글자 `*`. 부르지 않으면 기존 입력 창은 그대로 |
| `messages/scenes/scenes.properties`, `scenes_ko.properties` | `scenes.aisetupscene.*` 문구 (영어·한국어) |

**확인한 것** (`desktop:debug`, 1920×1080 · 125% 배율 모니터)
- ✅ 캐릭터 선택 → AI 설정 → [AI 없이 시작] → 던전 1층
- ✅ 같은 시드(AAA-AAA-AAA, 제약 1개)로 바꾸기 전 빌드(`582834b`)와 1층 첫 화면을 비교: 지도가 같고, 다른 곳은 움직이는 그림(주인공·하수구)뿐
- ✅ [뒤로]·ESC → 캐릭터 선택. 캐릭터·제약·시드 그대로
- ✅ 일일 도전, 이어하기(저장 슬롯 → 계속)는 AI 설정 장면을 거치지 않는다
- ✅ 키 창: 가짜 키 17글자가 `*` 17개로 보임, Ctrl+V 붙여넣기 됨, 복사 버튼을 눌러도 클립보드에 키가 들어가지 않음. 시드 입력 창은 가려지지 않음
- ✅ 껐다 켜도 공략·판 방식·최대 판단·플레이어 값이 남음. `settings.xml`과 게임 데이터 폴더에 가짜 키 글자 없음
- ✅ 실제 조작: 빨간 글자·빨간 테두리, [AI로 시작] 글자 "AI로 시작 · 실제 조작". 다시 열면 "지난번 판은 실제 조작이었어요"
- ✅ 최대 판단 509 → 바꾸지 않고 안내. 플레이어 이름을 비우면 player
- ✅ 세로 3종(360×640 · 540×960 · 720×1280) 모두 잘리지 않음 → 실험 옵션 접기는 만들지 않았다
- ⬜ 키 창의 붙여넣기 **버튼** (Ctrl+V와 같은 함수를 쓰지만 직접 누르지는 않음)
- ⬜ 실제 1440·768 모니터 (1440 크기는 모니터보다 커서 창 내부 캡처로 확인)

**설계(2장)와 다른 점**
- 모델·교훈 이어받기는 펼침 목록 대신 **회색 버튼** 한 줄이다. 목록을 받을 곳(Python)이 아직 없어서 모델은 지난 값(없으면 "연결 후 고를 수 있어요"), 교훈은 "없음"만 보여 준다. `ai_model`·`ai_lessons_from`은 읽기만 하고 아직 쓰지 않는다.
- 공략·판 방식은 둘 중 하나를 고르는 동그라미 대신 **누를 때마다 바뀌는 버튼**이다.
- API 키 줄은 끝 4자리 대신 고정 문구 "AI 관찰기와 연결되면 확인할 수 있어요". [연결 시험]·[AI로 시작]은 언제나 회색.
- [뒤로]는 [AI 없이 시작] 오른쪽에 나란히 둔다.
- "지난번 판은 실제 조작" 안내는 다른 버튼을 하나 누르면 기본 안내로 돌아간다.
- 키 창은 확인을 누르면 입력한 글자를 어디에도 넘기지 않고 끝내고, 안내 줄에 "키 전달은 다음 단계에서 만들어요. 입력한 키는 저장하지 않고 버렸어요."를 보여 준다.
- 참고(원작 동작): 세로 화면의 캐릭터 선택은 4초 뒤 버튼이 흐려지며 눌리지 않는다. 화면을 한 번 누르면 다시 나타난다.

### A-5-3 결과 (11/2)

**고친 파일**
| 파일 | 내용 |
|---|---|
| `core/.../AIBridge.java` (새 파일) | 게임 → Python HTTP 통로. `Gdx.net`으로 보내고, 응답은 `Game.runOnRenderThread`로 렌더 스레드에 넘긴다. 실패·시간 초과(①②④ 3초, ③ 35초)·JSON이 아닌 응답은 모두 `null` |
| `scenes/AISetupScene.java` | 연결 전 상태를 실제 동작으로 바꿨다 (아래) |
| `messages/scenes/scenes*.properties` | 키 상태 줄, 5장 안내 9가지 + 시험 기타 실패·시험 중·준비 중 등 (영어·한국어) |
| `ai-bridge/web.py` | `/api/bridge/*` ①~④, 요청 막기(`bridge_only`), `--env` 옵션, `/`·`/api/start`는 데모 전용, `/api/console/start`와 `.env`에 `MODEL` 쓰기 삭제, Flask가 `.env`를 스스로 읽는 것 끔 |
| `ai-bridge/agent.py` | `Agent.prepare()`(폴더와 `config.json`만 만듦), `game_run` 항목, `LLM(timeout=)`. 프롬프트와 `log.jsonl` 형식은 그대로 |
| `ai-bridge/web/panel.html`, `setup.html`, `log.html`, `static/common.js` | 패널 설정은 읽기 전용 요약, 데모 설정 화면의 키 칸 없앰, 요청에 `X-Nokpixel-Bridge` 헤더 |

**AI 설정 장면 동작**
- 장면을 열 때와 장면에 있는 동안 3초마다 ①. 응답을 기다리는 동안은 다음 ①을 보내지 않는다. 장면을 떠나면 `update()`가 불리지 않아 멈추고, 늦게 온 응답은 버린다.
- 모델·교훈 이어받기: 버튼을 누르면 게임의 고르기 창(`WndOptions`)이 뜬다. 지난 모델이 목록에 없으면 첫 모델, 지난 교훈이 목록에 없으면 "없음". 교훈은 최근 8판까지 보인다.
- 키 줄: "OpenAI API 키: ****abcd · 연결됨 (14:03 시험)" / 시험 실패 / 아직 시험 안 함 / 아직 없음. 회사 이름은 ①의 `providers`(이번에 더함)에서 받는다.
- [키 입력] → 가린 입력 창 → ②. 보낸 글자는 장면 안에 남기지 않는다.
- [연결 시험] 자리: Python이 꺼져 있거나 다른 판이 진행 중이면 **노란 글자 [관찰기 다시 확인]** 으로 바뀌어 ①을 바로 보낸다. 시험 중에는 회색 [시험하는 중…].
- [AI로 시작]: Python 켜짐 + 진행 중 판 없음 + 고른 모델 회사의 `tested_ok`일 때만 눌린다. 누르면 ④ → 성공하면 [AI 없이 시작]과 같은 시작 순서(함수 하나를 같이 씀). 실패하면 장면에 머물고 안내.
- 모델을 바꿔 회사가 달라지면 그 회사 키 상태로 다시 판단한다.

**Python 쪽 동작**
- ③: 고른 모델로 "ok라고만 답해." 한 번(출력 16토큰, 30초, 다시 시도 없음). 오류는 이름으로만 나눈다: `AuthenticationError`→`key_invalid`, `APITimeoutError`→`timeout`, 문구에 `insufficient_quota`·`credit balance`→`no_credit`, `NotFoundError`·`PermissionDeniedError`→`model_unavailable`, 나머지→`other`. 오류 원문은 어디에도 내보내지 않는다. 데모 모드는 API를 부르지 않고 `ok`.
- 시험 결과는 회사별로 메모리에만 둔다. ②로 키를 바꾸면 지운다. `web.py`를 다시 켜면 다시 시험해야 한다.
- ④: 진행 중 판이 있으면 `running`(409), 시험 성공 전이면 `not_tested`(409)로 거절. 대기 판은 하나이고, 새 ④가 오면 바꾼다. 바뀐 대기 판의 폴더에 `config.json`만 있으면 지운다. 대기 판은 `lock_input=True`로 만든다(패널에서 시작하던 때와 같은 입력 잠금).
- `config.json`에 더한 항목: `hero_class`(예: `WARRIOR`), `challenges`(비트 번호), `challenge_names`(`Challenges.NAME_IDS`의 영어 ID), `custom_seed`, `started_from: "game"`. 기존 `seed` 칸에는 `custom_seed`(비면 "무작위")를 넣는다. 캐릭터·제약은 AI 입력에 넣지 않는다 (합의). → A-5-4에서 바꿨다 (7장).

**확인한 것** (curl, 시험용 `--env` 파일과 가짜 키, 11/2)
- ✅ 헤더 없는 요청·JSON이 아닌 POST·헤더 없는 `/api/stop` → 403
- ✅ 실제 모드: `/api/console/start`·`/api/start` → 404, `/` → `/panel`로 넘어감
- ✅ ③ 키 없음 → `no_key` / ② 가짜 키 → `last4`만 돌려줌 / ③ 가짜 OpenAI 키 → `key_invalid`(약 1초), 가짜 Anthropic 키 → `key_invalid` / 시험 성공 전 ④ → `not_tested`
- ✅ ② 뒤 시험용 `.env`에는 회사 키 한 줄씩만 있음. 실제 `ai-bridge/.env`의 수정 시각은 10/25 그대로
- ✅ 데모: ③ → `ok`, ④ 두 번 → 두 번째로 바뀌고 첫 폴더는 지워짐, 진행 중인 판이 있으면 ④ → `running`(409), `config.json`에 새 항목이 들어감
- ✅ 가짜 키 글자가 `logs/` 전체, 서버 출력(Flask 접속 기록 포함), ①·`/api/state`·③ 응답 어디에도 없음. 접속 기록은 주소만 남김 (`"POST /api/bridge/key HTTP/1.1" 200`)
- ✅ 10/25(`run_20261025_225713_live10`), 10/31(`run_20261031_151906_portrait3`) 기록이 `/api/run/…`으로 그대로 열림
- ✅ `gradlew.bat desktop:compileJava` 통과, `desktop:debug`로 게임 창이 뜸
- 사용자 확인: 게임 장면 안 동작, 실제 키로 연결 시험, 관찰 패널 화면을 `docs/test-results/test-results-2026-11-02.txt`의 확인 목록대로 눌러 보았고 별 문제 없었다 (항목별 결과는 기록하지 않음)

**시험하다 찾은 것**
- Flask `app.run()`은 python-dotenv가 깔려 있으면 실행 폴더의 `.env`를 스스로 읽는다. 그래서 `--env`로 시험용 파일을 줘도 실제 키가 들어왔다. `load_dotenv=False`로 고쳤다. 고치기 전 첫 시험에서 실제 OpenAI 키의 끝 4자리가 ① 응답에 나왔고, ③이 실제 키로 GPT-6 Luna를 한 번 불렀다 (아주 적은 비용). 실제 `.env`는 바뀌지 않았다.

**설계와 다른 점**
- 5장 표의 [다시 확인]은 따로 만들지 않고 [연결 시험] 자리를 같이 쓴다 (세로 화면 자리 부족, 사용자 합의). 글자와 색이 다르다.
- 데모 설정 화면의 `/api/start`도 `.env`에 키를 쓰지 않는다. `.env`에 쓰는 곳은 ② 하나다 (사용자 합의).
- ①에 `demo`, `providers`(회사 이름), `pending`(대기 판)을 더했다. `/api/state`에도 `pending`을 더했다.
- A-5-4 전까지는 [AI로 시작]이 판 준비까지만 한다. 패널의 ▶ 시작이 없어졌으므로 그동안 실제 판은 `mvp.py`로만 돌릴 수 있다.

### A-5-3 뒤 바꾼 것 (11/2, 사용자 요청)
- **[AI 관찰기 켜기]**: 관찰기가 꺼져 있으면 [연결 시험] 자리가 노란 글자 [AI 관찰기 켜기]가 된다. 누르면 `AIBridge.launchWatcher()`가 게임을 실행한 폴더에서 위로 올라가며 `ai-bridge/web.py`를 찾고, 새 명령 창에서 `python web.py --panels`를 실행한다 (`cmd /k`라서 오류가 나도 창이 남는다). 켜지면 3초마다 하는 ①이 저절로 이어 준다. 20초 안에 이어지지 않으면 안내. Windows 전용, 폴더를 못 찾으면 직접 실행하라고 안내한다. 다른 판이 진행 중일 때는 그대로 [관찰기 다시 확인].
- 묶음 이름 "매번 보는 것" → **"기본 설정"**.
- **판 방식(생각만/실제 조작)을 없앴다.** 게임에서 시작하는 AI 판은 언제나 실제 조작이고 ④에 `dry_run: false`를 보낸다. 빨간 테두리, "AI로 시작 · 실제 조작" 글자, "지난번 판은 실제 조작" 안내도 없앴다. 생각만 하기는 명령줄 `mvp.py --dry-run`에 남는다. `SPDSettings`의 `ai_dry_run` 값은 이제 읽지 않는다 (허락된 파일 밖이라 지우지 않음).
- 실험 비교: `config.json`의 `dry_run` 칸은 그대로 기록되므로 지난 판과 구분할 수 있다. 프롬프트·`log.jsonl`은 그대로다.
- 확인: ✅ `desktop:compileJava` 통과, ✅ Java `ProcessBuilder`로 `cmd /c start "제목" /D 폴더 …`를 실행해 새 창에서 명령이 도는 것(시험 파일 생성)을 확인. 사용자 확인: 게임에서 버튼을 눌러 `web.py`가 켜지고 이어짐, 별 문제 없었다

### A-5-4 결과 (11/2)

**고친 파일**
| 파일 | 내용 |
|---|---|
| `core/.../AIBridge.java` | `pendingRunId`(④ 성공 직후에만 켬)·`activeRunId`(⑤ 성공 뒤), `onGameUpdate()`(⑤·⑦), `onGameOver()`·`onLeaveGame()`(⑥), 실패를 게임 기록창(`GLog.w`)에 한 줄 |
| `scenes/GameScene.java` | `update()`, `gameOver()`, `destroy()`에 `AIBridge`를 부르는 한 줄씩 (세 줄) |
| `scenes/AISetupScene.java` | ④ 성공 → `pendingRunId`, [AI 없이 시작] → 지움. ④에 `hero_title`·`challenge_titles`. 튜토리얼 판이면 [AI로 시작] 막기 |
| `messages/scenes/scenes*.properties` | 기록창 문구 2개(`gamescene.ai_not_started`, `ai_disconnected`), 튜토리얼 안내(`aisetupscene.tutorial_first`) (영어·한국어) |
| `ai-bridge/web.py` | `/api/bridge/arrived`(⑤), `/heartbeat`(⑦), `/ended`(⑥). ④에서 화면 이름 받기(`clean_name`) |
| `ai-bridge/agent.py` | `arrived()`, `heartbeat()`, `end_game()`, `_guard()`(키·클릭마다), `config.json`의 `ended_reason`·`ended_depth`·`ended_at`, `system_prompt()`의 `[이번 판]` 블록. `log.jsonl` 형식은 그대로 |
| `ai-bridge/web/panel.html`, `report.html` | 시드는 `seed_code`가 있으면 그것을, 끝난 이유·층 표시 (이 항목이 없는 옛 기록은 지금처럼) |

**동작**
- [AI로 시작] → ④ → 던전 1층 → ⑤ → Python이 대기 판을 시작한다. 사람이 아무것도 누르지 않아도 된다. 시작할 때 게임 창을 맨 앞으로 가져온다.
- `pendingRunId`는 첫 `GameScene`에서 한 번 쓰고 지운다. 그래서 계단으로 층을 옮겨도 ⑤를 다시 보내지 않는다. 이어하기·일일 도전은 AI 설정 장면을 거치지 않아 켜질 일이 없다.
- 판이 끝나는 길: ⑥(`died`·`won`·`quit`), ⑦의 `alive: false`(`died`), 신호 끊김(`game_closed`·`lost_game`), 패널 ■ 중지(`stopped`), 최대 판단(`max_steps`), 오류(`error`). 무엇으로 끝나든 그 자리에서 입력 잠금을 먼저 풀고, 처음 받은 이유 하나만 `ended_reason`에 남긴다.
- 키 3개를 연달아 보낼 때도 키마다, 생각을 마친 뒤 실행하기 전에도 확인한다. `quit`·`game_closed`·`lost_game`이면 마지막 화면을 다시 찍지 않는다.
- 첫 판 튜토리얼(`SPDSettings.intro()`)은 툴바를 숨기고 1층 생성·배고픔을 바꾼다 (✅ 코드 확인). 그래서 튜토리얼이 남아 있으면 [AI로 시작]을 회색으로 두고 "첫 판은 튜토리얼이라…[AI 없이 시작]으로 튜토리얼을 한 번 마친 뒤 AI로 시작해 주세요"라고 안내한다.
- 대기 판에 들어가지 않은 경우([AI 없이 시작], 1층이 아닌 곳): Python의 대기 판은 그대로 남고, 다음 ④가 오면 바뀌며 `config.json`만 있는 폴더는 지운다.

**확인한 것** (11/2)
- ✅ `gradlew.bat desktop:compileJava` 통과, `py_compile` 통과
- ✅ curl (데모 모드, 시험용 `--env`): ⑤의 `run_id`가 다르면 거절, 같으면 대기 판이 진행 중으로 바뀌고 `seed_code`가 `config.json`에 들어감
- ✅ curl: 신호 없음 → 키를 보내지 않고 기다리다 30초 뒤 `lost_game` / `alive: false` → `died`, 그 뒤 신호는 거절 / ⑥ `quit` → `quit`(다른 `run_id` 409, 틀린 `reason` 400) / 패널 중지 → `stopped` / 최대 판단 → `max_steps` / ⑥ `died` → `died`와 층
- ✅ `mvp.py` 판은 확인 장치가 꺼져 있고 지금처럼 끝남 (`ended_reason: max_steps`). 10/25 기록이 리포트에서 그대로 열림
- ✅ AI 입력: 데모로 시스템 프롬프트를 출력해 비교. 게임 판은 규칙 뒤에 `[이번 판]` 블록, 제약이 없으면 `직업:` 줄만, `mvp.py` 판은 원래 규칙과 글자까지 같음, 시드 글자는 없음
- ✅ curl: ④의 화면 이름이 `config.json`에 들어감. 줄바꿈은 공백으로, 빈 이름은 빠짐
- ⬜ 게임에서 직접 해 보는 확인 (손 시험 목록: `docs/test-results/test-results-2026-11-02.txt`의 A-5-4 부분)
- ⬜ 실제 판 (GPT-6 Luna, 최대 판단 5)
- ⬜ 게임이 보내는 한국어 직업·제약 이름이 그대로 들어가는지 (curl로는 확인, 게임에서는 미확인)

**설계와 다른 점**
- ⑤는 `GameScene.create()`가 아니라 `update()`에서, 조작할 수 있게 된 뒤에 보낸다 (화면 효과·주인공 준비를 기다림).
- ⑦ 살아 있음 신호를 더했다. 처음 약속에는 없었다 (⑥이 닿지 않을 때를 위해).

### A-5-4 실제 판 뒤 바꾼 것 (11/2, 사용자 요청)

**실제 판** `run_20261102_182004_player`: GPT-6 Luna, 최대 40 중 34판단, 관찰 패널 ■ 중지로 끝남(`stopped`, 1층), 시드 `XQW-TMQ-ZDW`, 비용 $0.0113(교훈 포함). AI는 1층 올라가는 계단(입구)을 출구로 알고 거듭 밟아 "아직 떠날 수 없습니다" 안내를 띄우고, 그 안내를 여러 번 눌렀다. 자세한 것: `docs/test-results/test-results-2026-11-02.txt` 6장.

| 사용자 요청 | 바꾼 것 | 커밋 |
|---|---|---|
| 중지한 뒤 다시 진행할 수 없고, 패널 입력이 먹통 | 판이 끝나면 패널 힌트·버튼이 꺼지는 것(원래 동작)이었다. **⏸ 일시정지 / ▶ 재개**를 더했다: 멈추면 입력 잠금이 바로 풀리고 힌트 칸은 그대로 쓸 수 있다. 생각하던 판단은 버리고 재개 뒤 같은 번호로 다시 생각한다(비용은 합계에 더함). 멈춘 시간은 `config.json`의 `pauses`. ■ 중지는 입력 잠금을 바로 풀고 한 번 확인한다 | `81bcdec` |
| 생각·판단 칸이 작다, 최근 판단 칸은 자리만 차지 | 최근 판단 칸을 없애고(판단은 기록 창에서), 지금 생각 칸이 남는 자리를 모두 쓰게 했다. [기록 창에서 보기]로 지금 판단을 연다 | `c057a0c` |
| 최종 목표가 고정돼 있다 | AI 설정 장면 실험 옵션에 [최종 목표] (최대 판단과 한 줄). ④의 `final_goal` → `config.json`. 규칙·`check_goal` 설명·큰 점검·교훈 쓰기 네 곳의 목표 글자만 바뀐다. **비우면 AI 입력이 글자까지 예전과 같다** (지난 판과 비교 가능) | `5605c39` |

- 확인: ✅ 일시정지·재개·중지 (curl, 데모), ✅ 기본 목표일 때 AI 입력이 바꾸기 전과 글자까지 같음 (mvp 판·게임 판), ✅ 패널·리포트 화면 (headless Edge 캡처), ✅ `desktop:compileJava`
- ⬜ 실제 게임에서: 일시정지 때 입력 잠금 풀림·재개 때 다시 잠김, AI 설정 장면의 [최종 목표][최대 판단] 반쪽 버튼과 입력 창 (손 시험 목록 7장)

---

## 10. 남은 질문 · 미확인

**만들 때 정할 것**
- ~~`TextInput`(SPD-classes)에 가리기 메서드를 더하는 것~~ → A-5-2 오더에서 합의, `setPasswordMode()`로 만들었다.
- ~~캐릭터·제약 줄을 AI 입력에 넣을지~~ → A-5-3 오더에서 합의: `config.json`에만 기록하고 AI 입력은 바꾸지 않는다.
- ~~판 끝(⑥)을 알릴 지점~~ → A-5-4에서 `GameScene.gameOver()`·`destroy()` 두 곳으로 정했다 (3-1).
- ~~기존 `/api/start` 등에도 다른 웹사이트 요청 막기(3-3)를 적용할지~~ → 적용했다 (9장 A-5-3 결과).
- 대기 판이 있는데 사람이 [AI 없이 시작]으로 들어가거나 `web.py`를 끄면 대기 판을 어떻게 할지 → A-5-4에서는 그대로 둔다. 게임은 AI를 시작하지 않고, Python의 대기 판은 다음 ④가 오면 바뀐다. `web.py`를 끄면 `config.json`만 있는 폴더가 남는다 (리포트 목록에는 나오지 않는다).
- ~~캐릭터·제약 줄을 AI 입력에 넣을지 (A-5-3 합의 다시)~~ → A-5-4에서 게임 판에만 넣기로 했다 (7장).

**⬜ 미확인**
- ~~가림 글자가 게임 글꼴로 그려지는지, 데스크톱에서 Ctrl+V로 키를 붙여 넣을 수 있는지~~ → ✅ A-5-2에서 확인 (9장).
- ~~첫 판 튜토리얼(`SPDSettings.intro()`)이 AI 첫 판에 주는 영향~~ → 화면과 1층·배고픔이 달라서 튜토리얼이 남아 있으면 [AI로 시작]을 막았다 (9장 A-5-4).
- 게임 창을 닫을 때 ⑥이 Python에 닿는지 (닿지 않아도 ⑦이 끊겨 멈춘다).
- 앙크로 부활할 때: `gameOver()`가 불리지 않으므로 AI 판은 이어진다. 다만 죽는 순간 ⑦에 `alive: false`가 먼저 갈 수 있다. 게임에서 확인하지 않았다.
- 아뮬렛 장면(26층)으로 갈 때 `quit`으로 보이는 것 (목표 밖).
- `Gdx.net` 요청이 실패할 때 걸리는 시간 (Python이 꺼져 있을 때 바로 실패하는지). → 확인 목록에 넣음.
- ~~Flask 접속 기록에 요청 본문(키)이 정말 남지 않는지~~ → ✅ 남지 않는다 (9장 A-5-3 결과).
- ~~세로 360×640(게임 안 180×320)에 이 항목이 모두 들어가는지~~ → ✅ 들어간다 (9장).
