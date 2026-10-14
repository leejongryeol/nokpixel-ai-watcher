"""녹픽셀 AI 감시자 - MVP

AI가 사람처럼 게임 화면을 보고, 키보드와 마우스로 녹픽던을 플레이한다.
게임 코드는 건드리지 않는다. (Windows 전용)

동작 순서 (한 번의 판단)
  1. 게임 창을 찾아 스크린샷을 찍는다
  2. 스크린샷 + 최근 기록을 Claude에게 보낸다
  3. Claude가 생각을 글로 쓰고, 도구(press_keys / click)로 행동을 고른다
  4. 그 행동을 실제 키 입력·클릭으로 실행한다
  5. 생각과 행동을 콘솔에 보여주고 logs/ 폴더에 기록한다

사용법
  python mvp.py --dry-run        # AI가 보고 생각만 함 (조작 안 함). 처음엔 이걸로!
  python mvp.py --steps 20       # AI가 20번 판단하며 실제로 플레이
  중지: 콘솔에서 Ctrl + C (또는 마우스를 화면 왼쪽 위 구석으로 이동)
"""

import argparse
import base64
import ctypes
import io
import json
import os
import sys
import time
from ctypes import wintypes
from datetime import datetime

from dotenv import load_dotenv

if sys.platform != "win32":
    sys.exit("이 MVP는 Windows 전용이에요.")

import anthropic
import pyautogui
from PIL import ImageGrab

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
GAME_WINDOW_TITLE = "Shattered Pixel Dungeon"
AI_IMAGE_SIZE = (720, 400)  # AI에게 보내는 이미지 크기 (게임 창 고정 크기와 같음)
DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # 가장 저렴한 모델로 시작
RECENT_LOG_SIZE = 5  # AI에게 보여줄 최근 판단 개수
WAIT_AFTER_ACTION = 0.6  # 행동 후 화면이 바뀔 때까지 기다리는 시간(초)

# 1M 토큰당 가격(달러). 비용 표시용 대략값.
PRICES = {
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
}

# ---------------------------------------------------------------------------
# AI에게 주는 규칙과 도구 (Claude Plays Pokémon 방식: 짧은 규칙 + 생각은 글로 + 행동은 도구로)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """너는 던전 탐험 게임을 하고 있다. 매번 게임 화면 이미지와 최근 기록이 주어진다.

최종 목표는 지하 5층의 보스를 처치하는 것이다. 화면에 보이는 정보만 보고 판단해라.
이를 위한 중간 목표(예: 계단 찾기, 체력 회복)는 스스로 세우고, 상황에 따라 바꿔라.

행동하기 전에 화면에서 무엇을 봤고, 지금 중간 목표가 무엇이며, 왜 그렇게 할지 한국어로 2~3문장 생각을 쓰고,
그다음 도구를 사용해 행동해라. 매 응답마다 도구를 한 번 사용해라.

[조작법]
- 이동: w(위) a(왼쪽) s(아래) d(오른쪽), 대각선은 num7 num9 num1 num3
- 적이 있는 칸으로 이동하면 공격한다
- space: 한 턴 기다리기 / 발밑 아이템 줍기
- z: 체력이 찰 때까지 쉬기
- e를 두 번: 주변의 숨겨진 것 탐색
- f: 가방 열기, esc: 창 닫기 / 뒤로 가기
- 1~6: 단축 슬롯 아이템 사용
- 화면의 버튼, 아이템, 칸을 직접 누를 때는 click 도구를 쓴다 (이미지 좌표 기준)
- 키 하나를 누를 때마다 한 턴이 지나고, 그동안 적도 움직인다"""

ALLOWED_KEYS = [
    "w", "a", "s", "d", "num7", "num9", "num1", "num3",
    "space", "z", "e", "f", "esc", "enter",
    "1", "2", "3", "4", "5", "6",
]

TOOLS = [
    {
        "name": "press_keys",
        "description": "키보드 키를 순서대로 누른다. 한 번에 최대 3개.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "array",
                    "items": {"type": "string", "enum": ALLOWED_KEYS},
                    "minItems": 1,
                    "maxItems": 3,
                },
                "speech": {
                    "type": "string",
                    "description": "캐릭터가 혼잣말하는 짧은 한마디 (말풍선용, 15자 이내)",
                },
            },
            "required": ["keys"],
        },
    },
    {
        "name": "click",
        "description": f"게임 화면의 한 지점을 마우스로 클릭한다. 좌표는 이미지 기준 (가로 0~{AI_IMAGE_SIZE[0] - 1}, 세로 0~{AI_IMAGE_SIZE[1] - 1}).",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "minimum": 0, "maximum": AI_IMAGE_SIZE[0] - 1},
                "y": {"type": "integer", "minimum": 0, "maximum": AI_IMAGE_SIZE[1] - 1},
                "speech": {
                    "type": "string",
                    "description": "캐릭터가 혼잣말하는 짧은 한마디 (말풍선용, 15자 이내)",
                },
            },
            "required": ["x", "y"],
        },
    },
]

# ---------------------------------------------------------------------------
# 게임 창 찾기, 화면 찍기 (Windows API)
# ---------------------------------------------------------------------------
user32 = ctypes.windll.user32

# 화면 배율(125%, 150% 등)이 있어도 실제 픽셀 좌표를 쓰도록 설정
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    user32.SetProcessDPIAware()


def find_game_window():
    hwnd = user32.FindWindowW(None, GAME_WINDOW_TITLE)
    if not hwnd:
        sys.exit(f'"{GAME_WINDOW_TITLE}" 창을 찾지 못했어요. 게임을 먼저 실행하세요.')
    return hwnd


def get_client_box(hwnd):
    """게임 창에서 제목줄·테두리를 뺀 실제 게임 화면 영역 (화면 좌표)."""
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom


def focus_window(hwnd):
    user32.ShowWindow(hwnd, 9)  # 최소화돼 있으면 복원
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)


def capture(hwnd):
    """게임 화면을 찍어 AI용 크기로 맞춘다. (이미지, 배율) 반환."""
    box = get_client_box(hwnd)
    image = ImageGrab.grab(bbox=box, all_screens=True).convert("RGB")
    scale_x = image.width / AI_IMAGE_SIZE[0]
    scale_y = image.height / AI_IMAGE_SIZE[1]
    if image.size != AI_IMAGE_SIZE:
        image = image.resize(AI_IMAGE_SIZE)
    return image, (box[0], box[1], scale_x, scale_y)


def to_base64_png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.standard_b64encode(buffer.getvalue()).decode()


# ---------------------------------------------------------------------------
# AI에게 묻기
# ---------------------------------------------------------------------------
def ask_ai(client, model, image, recent_log):
    if recent_log:
        history = "\n".join(
            f"- {i + 1}번째 전: {e['thought'][:120]} → {e['action_text']}"
            for i, e in enumerate(reversed(recent_log))
        )
    else:
        history = "- (처음 시작)"

    content = [
        {"type": "text", "text": f"[최근 기록]\n{history}\n\n[현재 게임 화면]"},
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": to_base64_png(image)},
        },
        {"type": "text", "text": "생각을 쓰고 도구로 행동해라."},
    ]

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        tools=TOOLS,
        messages=[{"role": "user", "content": content}],
    )

    thought = " ".join(b.text.strip() for b in response.content if b.type == "text").strip()
    tool = next((b for b in response.content if b.type == "tool_use"), None)
    return thought, tool, response.usage


# ---------------------------------------------------------------------------
# 행동 실행
# ---------------------------------------------------------------------------
def describe(tool):
    if tool is None:
        return "(행동 없음)"
    if tool.name == "press_keys":
        return "키 " + " → ".join(tool.input.get("keys", []))
    if tool.name == "click":
        return f"클릭 ({tool.input.get('x')}, {tool.input.get('y')})"
    return tool.name


def execute(tool, hwnd, geometry):
    if tool is None:
        return
    focus_window(hwnd)
    if tool.name == "press_keys":
        for key in tool.input.get("keys", [])[:3]:
            if key in ALLOWED_KEYS:
                pyautogui.press(key)
                time.sleep(0.15)
    elif tool.name == "click":
        left, top, scale_x, scale_y = geometry
        x = int(left + tool.input["x"] * scale_x)
        y = int(top + tool.input["y"] * scale_y)
        pyautogui.click(x, y)


# ---------------------------------------------------------------------------
# 메인 루프
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="녹픽셀 AI 감시자 MVP")
    parser.add_argument("--steps", type=int, default=10, help="AI가 판단할 횟수 (기본 10)")
    parser.add_argument("--dry-run", action="store_true", help="AI가 생각만 하고 조작하지 않음")
    args = parser.parse_args()

    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit(".env 파일에 ANTHROPIC_API_KEY가 없어요. ai-bridge/README.md를 확인하세요.")
    model = os.getenv("MODEL", DEFAULT_MODEL)
    price_in, price_out = PRICES.get(model, (0.0, 0.0))

    client = anthropic.Anthropic()
    hwnd = find_game_window()

    run_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs",
                           datetime.now().strftime("run_%Y%m%d_%H%M%S"))
    os.makedirs(run_dir, exist_ok=True)
    log_path = os.path.join(run_dir, "log.jsonl")

    print(f"모델: {model} | 판단 {args.steps}번 | {'생각만 (dry-run)' if args.dry_run else '실제 플레이'}")
    print(f"기록 폴더: {run_dir}")
    print("중지: Ctrl + C\n")

    recent_log = []
    total_cost = 0.0

    for step in range(1, args.steps + 1):
        image, geometry = capture(hwnd)
        image.save(os.path.join(run_dir, f"step_{step:03d}.png"))

        try:
            thought, tool, usage = ask_ai(client, model, image, recent_log)
        except anthropic.APIError as error:
            print(f"[오류] API 호출 실패: {error}")
            break

        cost = (usage.input_tokens * price_in + usage.output_tokens * price_out) / 1_000_000
        total_cost += cost
        action_text = describe(tool)
        speech = tool.input.get("speech", "") if tool else ""

        print(f"━━ {step}번째 판단 ━━")
        print(f"🧠 생각: {thought or '(생각 없음)'}")
        if speech:
            print(f"💬 \"{speech}\"")
        print(f"🎮 행동: {action_text}")
        print(f"🪙 토큰 입력 {usage.input_tokens} / 출력 {usage.output_tokens} · 약 ${cost:.4f} (누적 ${total_cost:.3f})\n")

        entry = {
            "step": step,
            "time": datetime.now().isoformat(timespec="seconds"),
            "model": model,
            "thought": thought,
            "speech": speech,
            "action": {"tool": tool.name, "input": tool.input} if tool else None,
            "action_text": action_text,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cost_usd": round(cost, 6),
            "dry_run": args.dry_run,
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        recent_log.append(entry)
        recent_log = recent_log[-RECENT_LOG_SIZE:]

        if not args.dry_run:
            execute(tool, hwnd, geometry)
        time.sleep(WAIT_AFTER_ACTION)

    print(f"끝! 총 비용 약 ${total_cost:.3f} · 기록: {log_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n사용자가 중지했어요.")
