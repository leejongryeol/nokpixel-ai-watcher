# 녹픽셀 AI 감시자 (nokpixel-ai-watcher)

> 매 판 새로운 던전에서, 외운 공략이 아닌 스스로의 판단으로 나아가는 생성형 AI를 지켜본다.

오픈소스 로그라이크 게임 **Shattered Pixel Dungeon**(녹픽던)에 생성형 AI를 연결해, AI가 게임을 플레이하며 내리는 판단과 그 이유를 기록하고 관찰하는 대학 개별 프로젝트입니다.

- **탐구 질문**: AI는 스스로 판단하는가, 아니면 아는 것을 꺼내 쓰는 것뿐인가?
- **목표**: 1구역 보스(5층) 도달 과정에서 AI의 판단을 관찰
- **사용자**: AI가 게임을 어떻게 판단하며 플레이하는지 궁금한 관찰자 (사용자는 직접 플레이하지 않음)
- **기획서**: [노션 페이지](https://app.notion.com/p/3eb8b0a72c89800f9c25ce49d1a9a8cc)

## 동작 과정

```
[게임] → ① 판단 순간 감지 → ② 게임 상태를 텍스트로 변환 → ③ 생성형 AI가 행동과 이유 생성 → ④ 게임 명령으로 실행 → [게임]
                                                                    ↓
                                                     관찰 화면 (AI 생각 / 게임 화면)
```

## 저장소 구조

| 경로 | 내용 |
|---|---|
| `core/`, `desktop/`, `SPD-classes/` … | 녹픽던 원본 게임 코드 (Java, v4.0.2 기준) |
| `ai-bridge/` | **새로 추가**: 게임과 AI를 연결하는 프로그램 (Python) |
| `docs/project/` | **새로 추가**: 시스템 구조, 판단 순간·숨길 정보 표 등 설계 문서 |
| `docs/getting-started-*.md` | 원본 게임 빌드 안내 (원작자 작성) |

## 시작하기

### 1. 게임 실행 (Java)
1. [JDK 21](https://adoptium.net/) 설치
2. 이 저장소를 내려받은 폴더에서 실행
   ```bash
   ./gradlew desktop:debug        # macOS / Linux
   gradlew.bat desktop:debug      # Windows
   ```
   처음 실행은 필요한 파일을 내려받느라 몇 분 걸릴 수 있어요.

### 2. AI 연결 준비 (Python)
`ai-bridge/README.md`를 보세요.

> ⚠️ **API 키는 절대 GitHub에 올리지 마세요.** `ai-bridge/.env`에만 저장하고, 이 파일은 `.gitignore`로 제외돼 있어요.

## 개발 일정

| 주차 | 기간 | 목표 |
|---|---|---|
| 6주차 | ~ 10/13 | 기획 확정, 개발 환경 준비 |
| 7주차 | 10/14 ~ 10/20 | 게임 상태를 텍스트로 추출 |
| 8주차 | 10/21 ~ 10/27 | (중간고사) AI 연결 최소 버전 |
| 9주차 | 10/28 ~ 11/3 | 기본 관찰 화면 |
| 10주차 | 11/4 ~ 11/10 | 부가 기능, 기능 완성 |
| 11주차 | 11/11 ~ 11/17 | 실험, 결과물 완성(11/14), 발표 준비 |
| 12주차 | 11/18 | 최종 발표 |

## 원작과 라이선스

이 프로젝트는 [00-Evan/shattered-pixel-dungeon](https://github.com/00-Evan/shattered-pixel-dungeon)을 포크해 만들었습니다.
Shattered Pixel Dungeon은 Evan Debenham이 [Watabou의 Pixel Dungeon](https://github.com/00-Evan/pixel-dungeon-gradle)을 바탕으로 만든 게임이며, 원본 README는 [`docs/ORIGINAL_README.md`](docs/ORIGINAL_README.md)에 보존돼 있습니다.

원작과 마찬가지로 이 저장소의 코드는 **GNU GPL v3.0** 라이선스를 따릅니다. 자세한 내용은 [`LICENSE.txt`](LICENSE.txt)를 보세요.
