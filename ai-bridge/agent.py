"""녹픽셀 AI 감시자 - AI 플레이어

AI가 사람처럼 게임 화면을 보고, 키보드와 마우스로 녹픽던을 플레이한다.
mvp.py(명령줄)와 web.py(관찰 웹 화면)가 함께 쓰는 핵심 로직이다.

한 번의 판단
  1. 게임 창 스크린샷을 찍는다 (Windows)
  2. 스크린샷 + 최근 기록 + (있으면) 개발자 힌트를 Claude에게 보낸다
  3. Claude가 생각을 글로 쓰고, 도구(press_keys / click)로 행동을 고른다
     도구에는 말풍선(speech), 중간 목표(goal), 기억 메모(memo_add)도 함께 담긴다
  4. 행동을 실제 키 입력·클릭으로 실행하고, logs/ 폴더에 기록한다

demo=True면 화면 캡처와 API 호출 없이 가짜 판단을 만든다. (화면 개발·시연용)
"""

import base64
import io
import json
import os
import random
import re
import sys
import threading
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(HERE, "logs")
GUIDE_PATH = os.path.join(HERE, "guide.md")

GAME_WINDOW_TITLE = "Shattered Pixel Dungeon"
AI_IMAGE_SIZE = (720, 400)  # AI에게 보내는 이미지 크기 (게임 창 고정 크기와 같음)
RECENT_LOG_SIZE = 5  # AI에게 보여줄 최근 판단 개수
MEMO_LIMIT = 20  # 기억 메모 최대 줄 수
WAIT_AFTER_ACTION = 0.6  # 행동 후 화면이 바뀔 때까지 기다리는 시간(초)

MODELS = {
    "claude-haiku-4-5-20251001": {"name": "Haiku 4.5", "price": (1.0, 5.0)},
    "claude-sonnet-5-5": {"name": "Sonnet 5.5", "price": (2.0, 10.0)},
    "claude-opus-5-5": {"name": "Opus 5.5", "price": (4.0, 20.0)},
}
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# AI에게 주는 규칙과 도구 (Claude Plays Pokémon 방식: 짧은 규칙 + 생각은 글로 + 행동은 도구로)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """너는 던전 탐험 게임을 하고 있다. 매번 게임 화면 이미지와 최근 기록이 주어진다.

최종 목표는 지하 5층의 보스를 처치하는 것이다. 화면에 보이는 정보만 보고 판단해라.
이를 위한 중간 목표(예: 계단 찾기, 체력 회복)는 스스로 세우고, 상황에 따라 바꿔라.

행동하기 전에 화면에서 무엇을 봤고, 지금 중간 목표가 무엇이며, 왜 그렇게 할지 한국어로 2~3문장 생각을 쓰고,
그다음 도구를 사용해 행동해라. 매 응답마다 도구를 한 번 사용해라.
새로 배운 교훈이 있으면 도구의 memo_add에 한 줄로 적어라. 기억 메모는 계속 보여진다.

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

_COMMON_PROPS = {
    "speech": {"type": "string", "description": "캐릭터가 혼잣말하는 짧은 한마디 (말풍선용, 15자 이내)"},
    "goal": {"type": "string", "description": "지금의 중간 목표 (예: 계단 찾기, 체력 회복). 바뀌지 않았으면 그대로 적는다"},
    "memo_add": {"type": "string", "description": "새로 배운 교훈 한 줄. 없으면 비워둔다"},
}

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
                **_COMMON_PROPS,
            },
            "required": ["keys", "goal"],
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
                **_COMMON_PROPS,
            },
            "required": ["x", "y", "goal"],
        },
    },
]


def load_guide():
    try:
        with open(GUIDE_PATH, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return ""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()  # 작성자용 주석은 빼고 전달


def describe_action(action):
    if not action:
        return "(행동 없음)"
    if action["tool"] == "press_keys":
        return "키 " + " → ".join(action["input"].get("keys", []))
    if action["tool"] == "click":
        return f"클릭 ({action['input'].get('x')}, {action['input'].get('y')})"
    return action["tool"]


def to_base64_png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.standard_b64encode(buffer.getvalue()).decode()


# ---------------------------------------------------------------------------
# 게임 창 찾기, 화면 찍기, 입력 (Windows 전용, 실제 플레이할 때만 불러옴)
# ---------------------------------------------------------------------------
class WindowsGame:
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("실제 플레이는 Windows에서만 할 수 있어요.")
        import ctypes
        from ctypes import wintypes
        import pyautogui
        from PIL import ImageGrab

        self.ctypes, self.wintypes = ctypes, wintypes
        self.pyautogui, self.ImageGrab = pyautogui, ImageGrab
        self.user32 = ctypes.windll.user32
        try:  # 화면 배율(125%, 150% 등)이 있어도 실제 픽셀 좌표를 쓰도록 설정
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            self.user32.SetProcessDPIAware()
        self.hwnd = self.user32.FindWindowW(None, GAME_WINDOW_TITLE)
        if not self.hwnd:
            raise RuntimeError(f'"{GAME_WINDOW_TITLE}" 창을 찾지 못했어요. 게임을 먼저 실행하세요.')
        self.geometry = (0, 0, 1.0, 1.0)

    def _client_box(self):
        rect = self.wintypes.RECT()
        self.user32.GetClientRect(self.hwnd, self.ctypes.byref(rect))
        origin = self.wintypes.POINT(0, 0)
        self.user32.ClientToScreen(self.hwnd, self.ctypes.byref(origin))
        return origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom

    def focus(self):
        self.user32.ShowWindow(self.hwnd, 9)  # 최소화돼 있으면 복원
        self.user32.SetForegroundWindow(self.hwnd)
        time.sleep(0.15)

    def capture(self):
        """게임 화면을 찍어 AI용 크기로 맞춘다."""
        self.focus()  # 다른 창(관찰 화면 등)에 가려지지 않게 앞으로 가져온다
        box = self._client_box()
        image = self.ImageGrab.grab(bbox=box, all_screens=True).convert("RGB")
        self.geometry = (box[0], box[1], image.width / AI_IMAGE_SIZE[0], image.height / AI_IMAGE_SIZE[1])
        if image.size != AI_IMAGE_SIZE:
            image = image.resize(AI_IMAGE_SIZE)
        return image

    def execute(self, action):
        if not action:
            return
        self.focus()
        if action["tool"] == "press_keys":
            for key in action["input"].get("keys", [])[:3]:
                if key in ALLOWED_KEYS:
                    self.pyautogui.press(key)
                    time.sleep(0.15)
        elif action["tool"] == "click":
            left, top, scale_x, scale_y = self.geometry
            x = int(left + action["input"]["x"] * scale_x)
            y = int(top + action["input"]["y"] * scale_y)
            self.pyautogui.click(x, y)


# ---------------------------------------------------------------------------
# 데모: 화면 캡처와 API 없이 가짜 판단 (관찰 화면 개발·시연용)
# ---------------------------------------------------------------------------
DEMO_SCRIPT = [
    ("층 입구다. 아직 아무것도 안 보인다. 우선 오른쪽 통로부터 살펴보자.", ["d", "d"], "계단 찾기", "출발!", ""),
    ("쥐 한 마리가 다가온다. 체력이 충분하니 먼저 공격하자.", ["d"], "계단 찾기", "덤벼라!", ""),
    ("쥐를 처치했다. 바닥에 뭔가 떨어져 있다. 주워보자.", ["space"], "계단 찾기", "뭐지?", ""),
    ("주황색 물약을 주웠다. 정체를 모르니 아껴두자.", ["s", "s"], "계단 찾기", "", "모르는 물약은 위급할 때만 마시기"),
    ("막다른 길이다. 숨겨진 문이 있을지 모르니 탐색해보자.", ["e", "e"], "계단 찾기", "수상한데...", ""),
    ("체력이 절반 아래다. 적이 없을 때 쉬어두자.", ["z"], "체력 회복", "잠깐 쉬자", "적이 없을 때 체력 회복"),
    ("체력이 찼다. 아래쪽에 계단이 보인다.", ["s", "s", "a"], "계단으로 이동", "찾았다!", ""),
]


class DemoGame:
    def __init__(self):
        from PIL import Image, ImageDraw

        self.Image, self.ImageDraw = Image, ImageDraw
        self.step = 0

    def capture(self):
        image = self.Image.new("RGB", AI_IMAGE_SIZE, (22, 20, 15))
        draw = self.ImageDraw.Draw(image)
        rnd = random.Random(self.step)
        for _ in range(60):  # 던전처럼 보이는 바닥 타일
            x, y = rnd.randrange(0, 720, 16), rnd.randrange(0, 400, 16)
            draw.rectangle([x, y, x + 15, y + 15], fill=(58, 52, 42))
        hx, hy = 344 + (self.step % 5) * 16, 184
        draw.rectangle([hx, hy, hx + 15, hy + 15], fill=(224, 164, 74))
        draw.text((12, 12), f"DEMO  step {self.step + 1}", fill=(236, 230, 216))
        self.step += 1
        return image

    def execute(self, action):
        pass


def demo_decision(step):
    thought, keys, goal, speech, memo = DEMO_SCRIPT[(step - 1) % len(DEMO_SCRIPT)]
    action = {"tool": "press_keys", "input": {"keys": keys, "goal": goal, "speech": speech, "memo_add": memo}}
    usage = {"input_tokens": 1250 + random.randint(-80, 80), "output_tokens": 110 + random.randint(-30, 40)}
    time.sleep(0.8)
    return thought, action, usage


# ---------------------------------------------------------------------------
# AI 플레이어
# ---------------------------------------------------------------------------
class Agent:
    """한 판의 실험을 실행한다. start()로 백그라운드 실행, stop()으로 중지."""

    def __init__(self, player="player", model=DEFAULT_MODEL, guide=False, seed="", steps=50,
                 dry_run=False, demo=False):
        self.config = {
            "player": player.strip() or "player",
            "model": model if model in MODELS else DEFAULT_MODEL,
            "model_name": MODELS.get(model, MODELS[DEFAULT_MODEL])["name"],
            "guide": bool(guide),
            "seed": seed.strip() or "무작위",
            "steps": int(steps),
            "dry_run": bool(dry_run),
            "demo": bool(demo),
            "started_at": datetime.now().isoformat(timespec="seconds"),
        }
        safe_player = "".join(c for c in self.config["player"] if c.isalnum() or c in "-_") or "player"
        self.run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S_") + safe_player
        self.run_dir = os.path.join(LOGS_DIR, self.run_id)
        self.status = "ready"  # ready → running → finished / stopped / error
        self.error = ""
        self.step = 0
        self.entries = []
        self.memo = []
        self.goal = ""
        self.total_cost = 0.0
        self.total_tokens = 0
        self._hints = []
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None

    # ----- 외부에서 쓰는 함수 -----
    def start(self):
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def add_hint(self, text):
        text = text.strip()
        if text:
            with self._lock:
                self._hints.append(text)

    def snapshot(self, last=12):
        with self._lock:
            return {
                "run_id": self.run_id,
                "config": self.config,
                "status": self.status,
                "error": self.error,
                "step": self.step,
                "goal": self.goal,
                "memo": list(self.memo),
                "total_cost": round(self.total_cost, 4),
                "total_tokens": self.total_tokens,
                "pending_hints": list(self._hints),
                "entries": self.entries[-last:],
            }

    # ----- 실행 -----
    def run(self):
        os.makedirs(self.run_dir, exist_ok=True)
        with open(os.path.join(self.run_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
        self.status = "running"
        try:
            game = DemoGame() if self.config["demo"] else WindowsGame()
            client = None
            if not self.config["demo"]:
                import anthropic
                client = anthropic.Anthropic()
            system = SYSTEM_PROMPT
            if self.config["guide"]:
                guide = load_guide()
                if guide:
                    system += "\n\n[공략 문서]\n" + guide

            for step in range(1, self.config["steps"] + 1):
                if self._stop.is_set():
                    self.status = "stopped"
                    break
                self.step = step
                image = game.capture()
                image_name = f"step_{step:03d}.png"
                image.save(os.path.join(self.run_dir, image_name))

                with self._lock:
                    hints, self._hints = self._hints, []

                if self.config["demo"]:
                    thought, action, usage = demo_decision(step)
                else:
                    thought, action, usage = self._ask(client, system, image, hints)

                price_in, price_out = MODELS[self.config["model"]]["price"]
                cost = (usage["input_tokens"] * price_in + usage["output_tokens"] * price_out) / 1_000_000
                inp = action["input"] if action else {}
                goal = (inp.get("goal") or "").strip()
                memo_add = (inp.get("memo_add") or "").strip()
                entry = {
                    "step": step,
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "image": image_name,
                    "thought": thought,
                    "speech": (inp.get("speech") or "").strip(),
                    "goal": goal,
                    "goal_changed": bool(goal) and goal != self.goal,
                    "memo_add": memo_add,
                    "hints": hints,
                    "action": action,
                    "action_text": describe_action(action),
                    "input_tokens": usage["input_tokens"],
                    "output_tokens": usage["output_tokens"],
                    "cost_usd": round(cost, 6),
                }
                with self._lock:
                    self.entries.append(entry)
                    self.total_cost += cost
                    self.total_tokens += usage["input_tokens"] + usage["output_tokens"]
                    if goal:
                        self.goal = goal
                    if memo_add and memo_add not in self.memo:  # 같은 교훈은 한 번만
                        self.memo.append(memo_add)
                        self.memo = self.memo[-MEMO_LIMIT:]
                with open(os.path.join(self.run_dir, "log.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

                if not self.config["dry_run"]:
                    game.execute(action)
                time.sleep(WAIT_AFTER_ACTION)
            else:
                self.status = "finished"
        except Exception as error:  # 관찰 화면에 오류를 보여주기 위해 모두 잡는다
            self.status = "error"
            self.error = str(error)
        finally:
            if self.status == "running":
                self.status = "finished"

    def _ask(self, client, system, image, hints):
        recent = self.entries[-RECENT_LOG_SIZE:]
        if recent:
            history = "\n".join(
                f"- {len(recent) - i}번째 전: {e['thought'][:120]} → {e['action_text']}"
                for i, e in enumerate(recent)
            )
        else:
            history = "- (처음 시작)"
        text = f"[최근 기록]\n{history}\n\n[현재 중간 목표] {self.goal or '(아직 없음)'}"
        if self.memo:
            text += "\n\n[기억 메모]\n" + "\n".join(f"- {m}" for m in self.memo)
        if hints:
            text += "\n\n[개발자 힌트]\n" + "\n".join(f"- {h}" for h in hints)
        content = [
            {"type": "text", "text": text + "\n\n[현재 게임 화면]"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": to_base64_png(image)}},
            {"type": "text", "text": "생각을 쓰고 도구로 행동해라."},
        ]
        response = client.messages.create(
            model=self.config["model"],
            max_tokens=2048,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS,
            messages=[{"role": "user", "content": content}],
        )
        thought = " ".join(b.text.strip() for b in response.content if b.type == "text").strip()
        tool = next((b for b in response.content if b.type == "tool_use"), None)
        action = {"tool": tool.name, "input": dict(tool.input)} if tool else None
        usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
        return thought, action, usage


# ---------------------------------------------------------------------------
# 지난 기록 읽기 (리포트용)
# ---------------------------------------------------------------------------
def list_runs():
    if not os.path.isdir(LOGS_DIR):
        return []
    runs = []
    for name in sorted(os.listdir(LOGS_DIR), reverse=True):
        path = os.path.join(LOGS_DIR, name)
        if os.path.isfile(os.path.join(path, "log.jsonl")):
            runs.append(name)
    return runs


def load_run(run_id):
    run_dir = os.path.join(LOGS_DIR, os.path.basename(run_id))
    config, entries, summary = {}, [], ""
    try:
        with open(os.path.join(run_dir, "config.json"), encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        pass
    try:
        with open(os.path.join(run_dir, "log.jsonl"), encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return None
    try:
        with open(os.path.join(run_dir, "summary.txt"), encoding="utf-8") as f:
            summary = f.read()
    except FileNotFoundError:
        pass
    return {"run_id": os.path.basename(run_id), "config": config, "entries": entries, "summary": summary}


def summarize_run(run_id, demo=False):
    """판단 기록을 AI에게 넘겨 관찰 리포트 요약을 받는다. (가장 저렴한 모델 사용)"""
    run = load_run(run_id)
    if not run:
        raise FileNotFoundError(run_id)
    if demo or run["config"].get("demo"):
        summary = ("데모 기록이라 실제 분석은 하지 않았어요. 실제 판에서는 이 칸에 AI가 판단 기록을 읽고 "
                   "중간 목표의 변화, 위험한 선택, 기억 메모가 행동을 바꾼 순간을 요약해 줘요.")
    else:
        import anthropic
        lines = [f"{e['step']}. [목표: {e.get('goal', '')}] {e['thought']} → {e['action_text']}"
                 + (f" (힌트: {'; '.join(e['hints'])})" if e.get("hints") else "")
                 for e in run["entries"]]
        prompt = ("다음은 AI가 던전 게임을 플레이하며 남긴 판단 기록이다. 관찰자를 위해 한국어로 5문장 이내로 요약해라. "
                  "어떤 중간 목표를 세우고 바꿨는지, 위험하거나 인상적인 판단, 실패에서 배운 것을 중심으로.\n\n"
                  + "\n".join(lines[-300:]))
        response = anthropic.Anthropic().messages.create(
            model=DEFAULT_MODEL, max_tokens=800, messages=[{"role": "user", "content": prompt}])
        summary = "".join(b.text for b in response.content if b.type == "text").strip()
    with open(os.path.join(LOGS_DIR, run["run_id"], "summary.txt"), "w", encoding="utf-8") as f:
        f.write(summary)
    return summary
