"""녹픽셀 AI 감시자 - AI 플레이어

AI가 사람처럼 게임 화면을 보고, 키보드와 마우스로 녹픽던을 플레이한다.
mvp.py(명령줄)와 web.py(관찰 웹 화면)가 함께 쓰는 핵심 로직이다.

한 번의 판단
  1. 게임 창 스크린샷을 찍는다 (Windows)
  2. 스크린샷 + 최근 기록 + (있으면) 개발자 힌트를 AI 모델(Claude 또는 OpenAI)에게 보낸다
  3. AI가 생각을 글로 쓰고, 도구(press_keys / click)로 행동을 고른다
     도구에는 말풍선(speech), 중간 목표(goal), 되새김(check_goal, basis),
     기억 메모 추가·지우기(memo_add, memo_remove)도 함께 담긴다
  4. 행동을 실제 키 입력·클릭으로 실행하고, logs/ 폴더에 기록한다

10번째 판단마다, 그리고 중간 목표를 바꾼 다음 판단에는 "큰 점검"을 요청한다.
판이 끝나면 AI가 다음 판의 자신에게 남길 교훈(lessons.md)을 직접 쓴다.
다음 판 설정에서 그 교훈을 이어받을 수 있다.

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
AI_IMAGE_SIZE = (360, 640)  # AI에게 보내는 이미지 크기. 게임 창이 더 크면 줄여서 보낸다
# 게임 창 크기 (DesktopLauncher.java의 AI_WINDOW_PRESETS와 같은 값). 모두 시야 180x320을 배율 4/3/2로 그린다
DISPLAY_PRESETS = {"1440": (720, 1280), "1080": (540, 960), "768": (360, 640)}
RECENT_LOG_SIZE = 5  # AI에게 보여줄 최근 판단 개수
MEMO_LIMIT = 20  # 기억 메모 최대 줄 수
CHECKPOINT_EVERY = 10  # 이 횟수마다 큰 점검
CHECKPOINT_LOG_SIZE = 10  # 큰 점검 때 보여줄 최근 판단 개수
NOT_EXECUTED_MARK = " (실제로 실행 안 됨)"  # 생각만 하기 판에서 최근 기록의 행동 뒤에 붙인다
LESSONS_FILE = "lessons.md"  # 판이 끝나고 AI가 쓴 교훈
INHERITED_FILE = "inherited_lessons.md"  # 판을 시작할 때 이어받은 교훈 (기록용 사본)
FINAL_IMAGE = "final.png"  # 판이 끝난 뒤 화면 (마지막 행동의 결과, 교훈 쓰기에 사용)
BASIS_VALUES = ["화면", "기록", "추측"]
WAIT_AFTER_ACTION = 0.6  # 행동 후 화면이 바뀔 때까지 기다리는 시간(초)
FOCUS_RETRIES = 3  # 게임 창을 맨 앞으로 가져오기 시도 횟수 (입력 전 확인)
FOCUS_WAIT_SECONDS = 30  # 그래도 못 가져오면 다시 시도하며 기다리는 최대 시간(초). 넘으면 판을 멈춘다
FOCUS_WAIT_INTERVAL = 2  # 기다리는 동안 다시 시도하는 간격(초)
TYPING_WAIT_SECONDS = 60  # 관찰자가 힌트를 입력하는 동안 다음 판단을 미루는 최대 시간(초)

MODELS = {  # price: 100만 토큰당 (입력, 출력) 달러
    "claude-haiku-4-5-20251001": {"name": "Haiku 4.5", "provider": "anthropic", "price": (1.0, 5.0)},
    "claude-sonnet-5-5": {"name": "Sonnet 5.5", "provider": "anthropic", "price": (2.0, 10.0)},
    "claude-opus-5-5": {"name": "Opus 5.5", "provider": "anthropic", "price": (4.0, 20.0)},
    "gpt-6-luna": {"name": "GPT-6 Luna", "provider": "openai", "price": (0.10, 0.50)},
    "gpt-6.1-sol": {"name": "GPT-6.1 Sol", "provider": "openai", "price": (2.0, 10.0)},
    "gpt-6-astra": {"name": "GPT-6 Astra", "provider": "openai", "price": (10.0, 50.0)},
}
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
PROVIDERS = {  # cheap_model: 연결 테스트·리포트 요약에 쓰는 가장 저렴한 모델
    "anthropic": {"name": "Claude", "key_env": "ANTHROPIC_API_KEY", "cheap_model": "claude-haiku-4-5-20251001"},
    "openai": {"name": "OpenAI", "key_env": "OPENAI_API_KEY", "cheap_model": "gpt-6-luna"},
}
OPENAI_REASONING_EFFORT = "low"  # OpenAI 모델이 답하기 전에 속으로 생각하는 양 (출력 토큰으로 계산됨)


def key_env(model):
    """그 모델을 쓰려면 필요한 API 키 이름 (예: OPENAI_API_KEY)"""
    return PROVIDERS[MODELS.get(model, MODELS[DEFAULT_MODEL])["provider"]]["key_env"]

# ---------------------------------------------------------------------------
# AI에게 주는 규칙과 도구 (Claude Plays Pokémon 방식: 짧은 규칙 + 생각은 글로 + 행동은 도구로)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """너는 던전 탐험 게임을 하고 있다. 매번 게임 화면 이미지와 최근 기록이 주어진다.

[최종 목표] 지하 5층의 보스를 처치하는 것. 모든 판단은 이 목표를 향한다.
이를 위한 중간 목표(예: 계단 찾기, 체력 회복)는 스스로 세우고, 상황에 따라 바꿔라.

[판단 방법]
1. 화면에서 무엇을 봤고 왜 그렇게 할지 한국어로 2~3문장 생각을 쓴다.
2. 도구를 한 번 사용해 행동한다. 도구에는 되새김을 함께 적는다.
   - check_goal: 이 행동이 중간 목표에, 중간 목표가 최종 목표에 어떻게 이어지는지 한 줄
   - basis: 이 판단의 근거. 화면(지금 화면에서 봄) / 기록(최근 기록·기억 메모) / 추측
   추측이면 솔직하게 추측이라고 적어라. 최종 목표로 이어지지 않으면 행동이나 중간 목표를 바꿔라.

[기억 메모]
- 새로 배운 교훈은 memo_add에 한 줄로 적는다. 기억 메모는 계속 보여진다.
- 메모에는 번호(M1, M2…)와 적은 시점이 붙는다. 메모는 사실이 아니라 그때의 판단이다.
- 틀렸거나 쓸모없어진 메모는 memo_remove에 번호를 적어 지운다.

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
    "check_goal": {"type": "string", "description": "되새김: 이 행동 → 중간 목표 → 최종 목표(5층 보스 처치)가 어떻게 이어지는지 한 줄"},
    "basis": {"type": "string", "enum": BASIS_VALUES, "description": "판단의 근거: 화면(지금 화면에서 봄) / 기록(최근 기록·기억 메모) / 추측"},
    "memo_add": {"type": "string", "description": "새로 배운 교훈 한 줄. 없으면 비워둔다"},
    "memo_remove": {"type": "string", "description": "틀렸거나 쓸모없어진 기억 메모 번호 (예: M3). 없으면 비워둔다"},
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
            "required": ["keys", "goal", "check_goal", "basis"],
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
            "required": ["x", "y", "goal", "check_goal", "basis"],
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


def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def load_lessons(run_id):
    """그 판이 끝나고 AI가 쓴 교훈. 없으면 빈 글."""
    if not run_id:
        return ""
    return read_text(os.path.join(LOGS_DIR, os.path.basename(run_id), LESSONS_FILE))


def checkpoint_reason(step, entries):
    """큰 점검이 필요한 이유. 필요 없으면 빈 글. (층 이동은 게임 코드 연결 후 추가)"""
    reasons = []
    if step % CHECKPOINT_EVERY == 0:
        reasons.append(f"{step}번째 판단")
    if entries and entries[-1].get("goal_changed") and len(entries) > 1:
        reasons.append("방금 중간 목표를 바꿈")
    return " · ".join(reasons)


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
# AI 모델 호출 (Claude / OpenAI의 API 형식 차이를 여기서만 다룬다)
# ---------------------------------------------------------------------------
def _openai_tool(tool):
    """Claude 형식 도구 → OpenAI 형식 도구.
    OpenAI 추론 모델은 도구를 꼭 쓰게 하면 글 답변 없이 도구만 부르는 일이 많아서, 생각을 도구 안 thought 칸으로 받는다."""
    schema = json.loads(json.dumps(tool["input_schema"]))
    schema["properties"] = {"thought": {"type": "string", "description": "화면에서 무엇을 봤고 왜 이렇게 할지 한국어 2~3문장"},
                            **schema["properties"]}
    schema["required"] = ["thought", *schema["required"]]
    return {"type": "function", "name": tool["name"], "description": tool["description"], "parameters": schema,
            "strict": False}


class LLM:
    """모델 하나를 부르는 창구. content는 ("text", 글) / ("image", PIL 이미지) 목록."""

    def __init__(self, model):
        self.model = model if model in MODELS else DEFAULT_MODEL
        self.provider = MODELS[self.model]["provider"]
        if self.provider == "openai":
            import openai
            self.client = openai.OpenAI()
        else:
            import anthropic
            self.client = anthropic.Anthropic()

    def ask(self, content, max_tokens, system=None, tools=None):
        """(글, 도구 호출 {"tool", "input"} 또는 None, 토큰 사용량)을 돌려준다."""
        if self.provider == "openai":
            return self._ask_openai(content, max_tokens, system, tools)
        return self._ask_anthropic(content, max_tokens, system, tools)

    def _ask_anthropic(self, content, max_tokens, system, tools):
        parts = [{"type": "text", "text": value} if kind == "text" else
                 {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": to_base64_png(value)}}
                 for kind, value in content]
        kwargs = {"model": self.model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": parts}]}
        if system:
            kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        if tools:
            kwargs["tools"] = tools
        response = self.client.messages.create(**kwargs)
        text = " ".join(b.text.strip() for b in response.content if b.type == "text").strip()
        tool = next((b for b in response.content if b.type == "tool_use"), None)
        action = {"tool": tool.name, "input": dict(tool.input)} if tool else None
        usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
        return text, action, usage

    def _ask_openai(self, content, max_tokens, system, tools):
        parts = [{"type": "input_text", "text": value} if kind == "text" else
                 {"type": "input_image", "image_url": "data:image/png;base64," + to_base64_png(value), "detail": "high"}
                 for kind, value in content]
        kwargs = {"model": self.model, "input": [{"role": "user", "content": parts}],
                  "max_output_tokens": max_tokens + 2048,  # 속으로 생각하는 추론 토큰도 여기에 포함된다
                  "reasoning": {"effort": OPENAI_REASONING_EFFORT}}
        if system:
            kwargs["instructions"] = system
        if tools:
            kwargs.update(tools=[_openai_tool(t) for t in tools], tool_choice="required", parallel_tool_calls=False)
        response = self.client.responses.create(**kwargs)
        text = (response.output_text or "").strip()
        call = next((o for o in response.output if o.type == "function_call"), None)
        action = None
        if call:
            inp = json.loads(call.arguments or "{}")
            thought = str(inp.pop("thought", "") or "").strip()
            text = text or thought
            action = {"tool": call.name, "input": inp}
        usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
        return text, action, usage


# ---------------------------------------------------------------------------
# 게임 창 찾기, 화면 찍기, 입력 (Windows 전용, 실제 플레이할 때만 불러옴)
# ---------------------------------------------------------------------------
class StopRequested(Exception):
    """게임 창을 기다리는 중에 관찰자가 중지를 누름."""


class WindowsGame:
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("실제 플레이는 Windows에서만 할 수 있어요.")
        import ctypes
        from ctypes import wintypes
        import pyautogui
        from PIL import Image, ImageGrab

        self.ctypes, self.wintypes = ctypes, wintypes
        self.pyautogui, self.Image, self.ImageGrab = pyautogui, Image, ImageGrab
        self.user32 = ctypes.windll.user32
        try:  # 화면 배율(125%, 150% 등)이 있어도 실제 픽셀 좌표를 쓰도록 설정
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            self.user32.SetProcessDPIAware()
        self.hwnd = self.user32.FindWindowW(None, GAME_WINDOW_TITLE)
        if not self.hwnd:
            raise RuntimeError(f'"{GAME_WINDOW_TITLE}" 창을 찾지 못했어요. 게임을 먼저 실행하세요.')
        self.geometry = (0, 0, 1.0, 1.0)
        self.window_size = None  # 마지막으로 찍은 게임 창 안쪽 크기 (config.json 기록용)
        self.stop_event = None  # 에이전트의 중지 신호 (게임 창을 기다리는 중에도 중지할 수 있게)
        self.waiting_focus = False  # 게임 창을 맨 앞으로 가져오지 못해 기다리는 중

    def is_front(self):
        return self.user32.GetForegroundWindow() == self.hwnd

    def _client_box(self):
        rect = self.wintypes.RECT()
        self.user32.GetClientRect(self.hwnd, self.ctypes.byref(rect))
        origin = self.wintypes.POINT(0, 0)
        self.user32.ClientToScreen(self.hwnd, self.ctypes.byref(origin))
        return origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom

    def focus(self):
        """게임 창을 맨 앞으로 가져온다. 정말 맨 앞에 왔으면 True.
        Windows는 뒤에 있는 프로그램이 창을 앞으로 가져오는 것을 자주 막아서, 막히면 방법을 바꿔 다시 시도한다."""
        u = self.user32
        if u.IsIconic(self.hwnd):
            u.ShowWindow(self.hwnd, 9)  # 최소화돼 있으면 복원
        for attempt in range(FOCUS_RETRIES):
            if u.GetForegroundWindow() == self.hwnd:
                return True
            if attempt > 0:  # Alt 키를 한 번 눌렀다 떼면 창 전환이 허용된다
                u.keybd_event(0x12, 0, 0, 0)
                u.keybd_event(0x12, 0, 2, 0)
            # 지금 맨 앞 창의 입력 흐름에 잠깐 붙어서 전환 허락을 얻는다
            fg_thread = u.GetWindowThreadProcessId(u.GetForegroundWindow(), None)
            my_thread = self.ctypes.windll.kernel32.GetCurrentThreadId()
            u.AttachThreadInput(my_thread, fg_thread, True)
            u.BringWindowToTop(self.hwnd)
            u.SetForegroundWindow(self.hwnd)
            u.AttachThreadInput(my_thread, fg_thread, False)
            time.sleep(0.15)
        return u.GetForegroundWindow() == self.hwnd

    def _require_focus(self):
        """입력 직전 확인: 게임 창이 맨 앞이 아니면 아무것도 누르지 않는다 (다른 창에 키가 들어가는 것을 막음).
        못 가져오면 다시 시도하며 최대 FOCUS_WAIT_SECONDS 기다리고, 그래도 안 되면 멈춘다."""
        if self.focus():
            return
        self.waiting_focus = True
        try:
            deadline = time.time() + FOCUS_WAIT_SECONDS
            while time.time() < deadline:
                if self.stop_event is not None and self.stop_event.wait(FOCUS_WAIT_INTERVAL):
                    raise StopRequested()
                if self.stop_event is None:
                    time.sleep(FOCUS_WAIT_INTERVAL)
                if self.focus():
                    return
        finally:
            self.waiting_focus = False
        raise RuntimeError(f"게임 창을 {FOCUS_WAIT_SECONDS}초 동안 맨 앞으로 가져오지 못해서 입력을 멈췄어요. "
                           "다른 창에 키가 들어가는 것을 막기 위해서예요.")

    def _print_window(self, width, height):
        """가려져 있어도 게임 창 내용을 직접 받아온다. 실패하거나 완전히 검은 화면이면 None."""
        ctypes, wintypes, u = self.ctypes, self.wintypes, self.user32
        gdi = ctypes.windll.gdi32

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]

        hdc = u.GetDC(self.hwnd)
        mem = gdi.CreateCompatibleDC(hdc)
        bitmap = gdi.CreateCompatibleBitmap(hdc, width, height)
        gdi.SelectObject(mem, bitmap)
        try:
            if not u.PrintWindow(self.hwnd, mem, 1 | 2):  # 창 안쪽만 | 그래픽 가속 화면까지
                return None
            header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
            buffer = ctypes.create_string_buffer(width * height * 4)
            gdi.GetDIBits(mem, bitmap, 0, height, buffer, ctypes.byref(header), 0)
            image = self.Image.frombuffer("RGB", (width, height), buffer, "raw", "BGRX", 0, 1)
            return image if image.convert("L").getextrema()[1] > 0 else None
        finally:
            gdi.DeleteObject(bitmap)
            gdi.DeleteDC(mem)
            u.ReleaseDC(self.hwnd, hdc)

    def capture(self):
        """게임 화면을 찍어 AI용 크기로 맞춘다."""
        focused = self.focus()  # 실패해도 괜찮다. PrintWindow는 가려진 창도 찍는다
        box = self._client_box()
        image = self._print_window(box[2] - box[0], box[3] - box[1])
        if image is None:  # 안 되면 화면에서 그대로 찍는다. 게임이 맨 앞이 아니면 다른 창이 찍히므로 멈춘다
            if not focused:
                raise RuntimeError("게임 창을 찍지 못했어요. 게임 창이 최소화돼 있거나 다른 창에 가려져 있어요.")
            image = self.ImageGrab.grab(bbox=box, all_screens=True).convert("RGB")
        self.geometry = (box[0], box[1], image.width / AI_IMAGE_SIZE[0], image.height / AI_IMAGE_SIZE[1])
        self.window_size = image.size
        if image.size != AI_IMAGE_SIZE:  # 칸 평균으로 줄인다 (픽셀 그림이 덜 뭉개짐)
            image = image.resize(AI_IMAGE_SIZE, self.Image.BOX)
        return image

    def execute(self, action):
        if not action:
            return
        if action["tool"] == "press_keys":
            for key in action["input"].get("keys", [])[:3]:
                if key in ALLOWED_KEYS:
                    self._require_focus()
                    self.pyautogui.press(key)
                    time.sleep(0.15)
        elif action["tool"] == "click":
            self._require_focus()
            left, top, scale_x, scale_y = self.geometry
            x = int(left + action["input"]["x"] * scale_x)
            y = int(top + action["input"]["y"] * scale_y)
            self.pyautogui.click(x, y)


# ---------------------------------------------------------------------------
# 데모: 화면 캡처와 API 없이 가짜 판단 (관찰 화면 개발·시연용)
# ---------------------------------------------------------------------------
DEMO_SCRIPT = [
    {"thought": "층 입구다. 아직 아무것도 안 보인다. 우선 오른쪽 통로부터 살펴보자.", "keys": ["d", "d"],
     "goal": "계단 찾기", "speech": "출발!", "check_goal": "안 가본 곳을 봐야 계단을 찾고, 계단으로 5층에 간다", "basis": "화면"},
    {"thought": "쥐 한 마리가 다가온다. 체력이 충분하니 먼저 공격하자.", "keys": ["d"],
     "goal": "계단 찾기", "speech": "덤벼라!", "check_goal": "길을 막는 적을 치워야 탐색을 계속할 수 있다", "basis": "화면"},
    {"thought": "쥐를 처치했다. 바닥에 뭔가 떨어져 있다. 주워보자.", "keys": ["space"],
     "goal": "계단 찾기", "speech": "뭐지?", "check_goal": "아이템은 보스전에서 쓸 수 있다", "basis": "화면"},
    {"thought": "주황색 물약을 주웠다. 정체를 모르니 아껴두자. 아마 회복 물약일 것 같다.", "keys": ["s", "s"],
     "goal": "계단 찾기", "speech": "", "check_goal": "모르는 물약은 위급할 때 쓰려고 남긴다", "basis": "추측",
     "memo_add": "주황색 물약은 회복 물약 같다"},
    {"thought": "막다른 길이다. 숨겨진 문이 있을지 모르니 탐색해보자.", "keys": ["e", "e"],
     "goal": "계단 찾기", "speech": "수상한데...", "check_goal": "숨겨진 길 너머에 계단이 있을 수 있다", "basis": "추측"},
    {"thought": "체력이 절반 아래다. 적이 없을 때 쉬어두자.", "keys": ["z"],
     "goal": "체력 회복", "speech": "잠깐 쉬자", "check_goal": "체력이 없으면 5층까지 못 버틴다", "basis": "화면",
     "memo_add": "적이 없을 때 체력 회복"},
    {"thought": "중간 목표를 체력 회복으로 바꿨다. 주황 물약이 회복이라는 건 확인한 적 없는 추측이었다. 메모를 지우자.", "keys": ["z"],
     "goal": "체력 회복", "speech": "", "check_goal": "확인 안 된 메모에 기대면 위급할 때 틀린 물약을 마신다", "basis": "기록",
     "memo_remove": "M1"},
    {"thought": "체력이 찼다. 아래쪽에 계단이 보인다.", "keys": ["s", "s", "a"],
     "goal": "계단으로 이동", "speech": "찾았다!", "check_goal": "계단을 내려가면 5층 보스에 한 층 가까워진다", "basis": "화면"},
]

DEMO_LESSONS = """- 막다른 길에서는 e e로 탐색해 숨겨진 길을 찾는다 (근거: 판단 5)
- 정체를 모르는 물약을 회복 물약이라고 단정하지 않는다. 확인 전까지는 추측으로 둔다 (근거: 판단 7)
- 체력이 절반 아래면 적이 없을 때 z로 쉰다 (근거: 판단 6)
(데모 기록이라 가짜 교훈이에요)"""


class DemoGame:
    def __init__(self):
        from PIL import Image, ImageDraw

        self.Image, self.ImageDraw = Image, ImageDraw
        self.step = 0
        self.window_size = None

    def capture(self):
        width, height = AI_IMAGE_SIZE
        image = self.Image.new("RGB", AI_IMAGE_SIZE, (22, 20, 15))
        draw = self.ImageDraw.Draw(image)
        rnd = random.Random(self.step)
        for _ in range(60):  # 던전처럼 보이는 바닥 타일
            x, y = rnd.randrange(0, width, 16), rnd.randrange(0, height, 16)
            draw.rectangle([x, y, x + 15, y + 15], fill=(58, 52, 42))
        hx, hy = width // 2 - 40 + (self.step % 5) * 16, height // 2
        draw.rectangle([hx, hy, hx + 15, hy + 15], fill=(224, 164, 74))
        draw.text((12, 12), f"DEMO  step {self.step + 1}", fill=(236, 230, 216))
        self.step += 1
        return image

    def execute(self, action):
        pass


def demo_decision(step):
    item = DEMO_SCRIPT[(step - 1) % len(DEMO_SCRIPT)]
    inp = {k: v for k, v in item.items() if k != "thought"}
    action = {"tool": "press_keys", "input": inp}
    usage = {"input_tokens": 1300 + random.randint(-80, 80), "output_tokens": 150 + random.randint(-30, 40)}
    time.sleep(0.8)
    return item["thought"], action, usage


# ---------------------------------------------------------------------------
# AI 플레이어
# ---------------------------------------------------------------------------
class Agent:
    """한 판의 실험을 실행한다. start()로 백그라운드 실행, stop()으로 중지."""

    def __init__(self, player="player", model=DEFAULT_MODEL, guide=False, seed="", steps=50,
                 dry_run=False, demo=False, lessons_from="", lock_input=False):
        lessons_from = os.path.basename(lessons_from or "")
        self.inherited_lessons = load_lessons(lessons_from)
        self.config = {
            "player": player.strip() or "player",
            "model": model if model in MODELS else DEFAULT_MODEL,
            "model_name": MODELS.get(model, MODELS[DEFAULT_MODEL])["name"],
            "guide": bool(guide),
            "lessons_from": lessons_from if self.inherited_lessons else "",
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
        self.memo = []  # [{"id": "M1", "text": ..., "step": 3}]
        self._memo_seq = 0
        self.goal = ""
        self.lessons = ""  # 이번 판이 끝나고 쓴 교훈
        self.lessons_state = ""  # "" → writing → done / error
        self.total_cost = 0.0
        self.total_tokens = 0
        self._hints = []
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        # 세 창 관찰 화면용 (기록·AI 입력에는 들어가지 않는다)
        self.phase = "ready"  # ready → capture → thinking → acting → (typing) … → done
        self.game = None
        self._typing_until = 0.0
        self.input_lock = None
        if lock_input and not demo:
            from input_lock import InputLock
            self.input_lock = InputLock()

    # ----- 외부에서 쓰는 함수 -----
    def start(self):
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def stop(self):
        self._typing_until = 0.0
        self._stop.set()

    def add_hint(self, text):
        text = text.strip()
        if text:
            with self._lock:
                self._hints.append(text)

    def set_typing(self, on):
        """관찰자가 힌트를 입력하는 동안 다음 판단을 미룬다 (게임 창이 입력 중에 앞으로 튀어나오지 않게)."""
        self._typing_until = time.time() + TYPING_WAIT_SECONDS if on else 0.0

    def focus_game(self):
        """게임 창을 맨 앞으로 가져온다. 데모는 게임 창이 없으므로 True."""
        if self.game is None or not hasattr(self.game, "focus"):
            return self.config["demo"]
        return self.game.focus()

    def live_state(self):
        """관찰 화면 신호등용: 게임 창이 맨 앞인지, 게임 창을 기다리는 중인지, 잠금 상태."""
        game = self.game
        return {
            "phase": self.phase,
            "typing": time.time() < self._typing_until,
            "game_front": game.is_front() if hasattr(game, "is_front") else None,
            "focus_waiting": bool(getattr(game, "waiting_focus", False)),
            "lock_used": self.input_lock is not None,
            "locked": bool(self.input_lock and self.input_lock.active),
            "lock_note": self.input_lock.note if self.input_lock else "",
        }

    def snapshot(self, last=12, since=None):
        live = self.live_state()
        with self._lock:
            entries = [e for e in self.entries if e["step"] > since] if since is not None else self.entries[-last:]
            return {
                **live,
                "entry_count": len(self.entries),
                "run_id": self.run_id,
                "config": self.config,
                "status": self.status,
                "error": self.error,
                "step": self.step,
                "goal": self.goal,
                "memo": [dict(m) for m in self.memo],
                "inherited_lessons": self.inherited_lessons,
                "lessons": self.lessons,
                "lessons_state": self.lessons_state,
                "total_cost": round(self.total_cost, 4),
                "total_tokens": self.total_tokens,
                "pending_hints": list(self._hints),
                "entries": entries,
            }

    # ----- 실행 -----
    def run(self):
        os.makedirs(self.run_dir, exist_ok=True)
        self._save_config()
        if self.inherited_lessons:  # 어떤 교훈을 받고 시작했는지 이 판 폴더에도 남긴다
            with open(os.path.join(self.run_dir, INHERITED_FILE), "w", encoding="utf-8") as f:
                f.write(self.inherited_lessons + "\n")
        self.status = "running"
        final_status, client, image, game = "finished", None, None, None
        try:
            game = DemoGame() if self.config["demo"] else WindowsGame()
            game.stop_event = self._stop
            self.game = game
            if self.input_lock is not None:  # 실패해도 판은 진행한다 (관찰 화면에 🔓와 이유가 보임)
                self.input_lock.start(game.hwnd)
            if not self.config["demo"]:
                client = LLM(self.config["model"])
            system = SYSTEM_PROMPT
            if self.config["guide"]:
                guide = load_guide()
                if guide:
                    system += "\n\n[공략 문서]\n" + guide
            if self.inherited_lessons:
                system += ("\n\n[지난 판의 네가 남긴 교훈]\n"
                           "지난 판에서 네가 직접 겪고 쓴 교훈이다. 이번 판에서 틀린 것으로 보이면 따르지 않아도 된다.\n"
                           + self.inherited_lessons)

            for step in range(1, self.config["steps"] + 1):
                self._wait_while_typing()
                if self._stop.is_set():
                    final_status = "stopped"
                    break
                self.step = step
                self.phase = "capture"
                image = game.capture()
                if step == 1:  # 실제로 찍은 게임 창 크기를 기록에 남긴다
                    self._record_display(game)
                image_name = f"step_{step:03d}.png"
                image.save(os.path.join(self.run_dir, image_name))

                with self._lock:
                    hints, self._hints = self._hints, []
                checkpoint = checkpoint_reason(step, self.entries)

                self.phase = "thinking"
                if self.config["demo"]:
                    thought, action, usage = demo_decision(step)
                else:
                    thought, action, usage = self._ask(client, system, image, hints, checkpoint)

                self._record(step, image_name, thought, action, usage, hints, checkpoint)
                self.phase = "acting"
                if not self.config["dry_run"]:
                    game.execute(action)
                time.sleep(WAIT_AFTER_ACTION)
        except StopRequested:
            final_status = "stopped"
        except Exception as error:  # 관찰 화면에 오류를 보여주기 위해 모두 잡는다
            final_status = "error"
            self.error = str(error)
        finally:  # 판이 어떻게 끝나든 입력 잠금을 푼다
            if self.input_lock is not None:
                self.input_lock.stop()
        self.phase = "done"

        # 한 번이라도 판단했으면 다음 판을 위한 교훈을 쓴다.
        # 생각만 하기(dry-run)는 조작을 안 했는데 AI가 "눌렀더니 ~됐다"는 틀린 교훈을 써서 건너뛴다.
        if self.entries and not self.config["dry_run"]:
            if game is not None and not self.config["demo"]:
                image = self._capture_final(game) or image
            self._finish_with_lessons(client, final_status, image)
        self.status = final_status

    def _save_config(self):
        with open(os.path.join(self.run_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def _record_display(self, game):
        """화면 설정(1440/1080/768), 게임 창 크기, AI 사진 크기를 config.json에 더한다.
        이 항목이 없는 기록은 이전 방식(가로 720x400 창, 사진 720x400)이다."""
        size = game.window_size
        if self.config["demo"]:
            display = "데모"
        else:
            display = next((name for name, preset in DISPLAY_PRESETS.items() if preset == size), "기타")
        self.config.update(display=display, game_window=list(size) if size else None, ai_image=list(AI_IMAGE_SIZE))
        self._save_config()

    def _wait_while_typing(self):
        while time.time() < self._typing_until and not self._stop.is_set():
            self.phase = "typing"
            time.sleep(0.2)

    def _capture_final(self, game):
        """마지막 행동의 결과가 보이도록, 판이 끝난 뒤 화면을 한 번 더 찍는다. 실패하면 None."""
        try:
            image = game.capture()
            image.save(os.path.join(self.run_dir, FINAL_IMAGE))
            return image
        except Exception:
            return None

    def _record(self, step, image_name, thought, action, usage, hints, checkpoint):
        price_in, price_out = MODELS[self.config["model"]]["price"]
        cost = (usage["input_tokens"] * price_in + usage["output_tokens"] * price_out) / 1_000_000
        inp = action["input"] if action else {}
        goal = (inp.get("goal") or "").strip()
        memo_add = (inp.get("memo_add") or "").strip()
        memo_remove_id = (inp.get("memo_remove") or "").strip().upper()
        basis = inp.get("basis") if inp.get("basis") in BASIS_VALUES else ""
        with self._lock:
            removed = next((m for m in self.memo if m["id"] == memo_remove_id), None)
            if removed:
                self.memo.remove(removed)
            added_id = ""
            if memo_add and all(m["text"] != memo_add for m in self.memo):  # 같은 교훈은 한 번만
                self._memo_seq += 1
                added_id = f"M{self._memo_seq}"
                self.memo.append({"id": added_id, "text": memo_add, "step": step})
                self.memo = self.memo[-MEMO_LIMIT:]
            entry = {
                "step": step,
                "time": datetime.now().isoformat(timespec="seconds"),
                "image": image_name,
                "thought": thought,
                "speech": (inp.get("speech") or "").strip(),
                "goal": goal,
                "goal_changed": bool(goal) and goal != self.goal,
                "check_goal": (inp.get("check_goal") or "").strip(),
                "basis": basis,
                "checkpoint": checkpoint,
                "memo_add": memo_add if added_id else "",
                "memo_add_id": added_id,
                "memo_removed": f"{removed['id']} {removed['text']}" if removed else "",
                "hints": hints,
                "action": action,
                "action_text": describe_action(action),
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "cost_usd": round(cost, 6),
            }
            self.entries.append(entry)
            self.total_cost += cost
            self.total_tokens += usage["input_tokens"] + usage["output_tokens"]
            if goal:
                self.goal = goal
        with open(os.path.join(self.run_dir, "log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _ask(self, client, system, image, hints, checkpoint):
        content = [
            ("text", self._prompt_text(hints, checkpoint) + "\n\n[현재 게임 화면]"),
            ("image", image),
            ("text", "생각을 쓰고 도구로 행동해라."),
        ]
        return client.ask(content, 2048, system=system, tools=TOOLS)

    def _prompt_text(self, hints, checkpoint):
        """판단 요청에 들어가는 글 부분 (최근 기록, 중간 목표, 기억 메모, 힌트, 큰 점검)."""
        recent = self.entries[-(CHECKPOINT_LOG_SIZE if checkpoint else RECENT_LOG_SIZE):]
        # 생각만 하기 판에서 AI가 기록 속 행동을 실제로 했다고 믿지 않게 표시한다. 실제 조작 판의 형식은 그대로.
        mark = NOT_EXECUTED_MARK if self.config["dry_run"] else ""
        if recent:
            history = "\n".join(
                f"- 판단 {e['step']}: {e['thought'][:120]} → {e['action_text']}{mark}"
                + (f" [근거: {e['basis']}]" if e.get("basis") else "")
                for e in recent
            )
        else:
            history = "- (처음 시작)"
        text = f"[최근 기록]\n{history}\n\n[현재 중간 목표] {self.goal or '(아직 없음)'}"
        if self.memo:
            text += "\n\n[기억 메모]\n" + "\n".join(f"- {m['id']} (판단 {m['step']}에 적음): {m['text']}" for m in self.memo)
        if hints:
            text += "\n\n[개발자 힌트]\n" + "\n".join(f"- {h}" for h in hints)
        if checkpoint:
            text += (f"\n\n[큰 점검 · {checkpoint}]\n"
                     "행동하기 전에 생각에 다음을 함께 써라. "
                     "① 지금까지 최종 목표(5층 보스 처치)에 가까워졌는가 "
                     "② 지금 중간 목표가 여전히 맞는가 "
                     "③ 기억 메모 중 근거가 약하거나 틀린 것은 없는가 (있으면 memo_remove)")
        return text

    # ----- 판이 끝난 뒤: 다음 판의 나에게 남기는 교훈 -----
    def _finish_with_lessons(self, client, final_status, image):
        self.lessons_state = "writing"
        ending = {"finished": "정해진 판단 횟수를 다 씀", "stopped": "관찰자가 중지함"}.get(
            final_status, f"오류로 멈춤 ({self.error})")
        try:
            if self.config["demo"]:
                time.sleep(1.0)
                lessons = DEMO_LESSONS
            else:
                if client is None:
                    client = LLM(self.config["model"])
                lessons, usage = self._ask_lessons(client, ending, image)
                price_in, price_out = MODELS[self.config["model"]]["price"]
                with self._lock:
                    self.total_cost += (usage["input_tokens"] * price_in + usage["output_tokens"] * price_out) / 1_000_000
                    self.total_tokens += usage["input_tokens"] + usage["output_tokens"]
            with open(os.path.join(self.run_dir, LESSONS_FILE), "w", encoding="utf-8") as f:
                f.write(lessons + "\n")
            self.lessons, self.lessons_state = lessons, "done"
        except Exception as error:
            self.lessons_state = "error"
            self.error = (self.error + " / " if self.error else "") + f"교훈 쓰기 실패: {error}"

    def _ask_lessons(self, client, ending, image):
        log = "\n".join(
            f"{e['step']}. [목표: {e['goal']}] [근거: {e.get('basis') or '-'}] {e['thought'][:200]} → {e['action_text']}"
            for e in self.entries[-150:])
        memo = "\n".join(f"- {m['id']}: {m['text']}" for m in self.memo) or "(없음)"
        prompt = f"""방금 던전 게임 한 판이 끝났다. 끝난 이유: {ending}
최종 목표는 지하 5층의 보스 처치였다. 마지막 화면(마지막 행동까지 끝난 뒤의 화면)을 보면 캐릭터가 살아 있는지, 몇 층인지 알 수 있다.

[이번 판의 판단 기록]
{log}

[끝날 때의 기억 메모]
{memo}

[이번 판을 시작할 때 받은 지난 교훈]
{self.inherited_lessons or "(없음)"}

다음 판의 너에게 남길 교훈을 써라.
- 이번 판에서 직접 겪은 일에서 나온 교훈만 쓴다. 원래 알던 게임 지식을 옮겨 적지 마라.
- 한 줄에 하나, 최대 7줄. 각 줄 끝에 근거가 된 판단 번호를 적는다. 예: "- 막다른 길에서는 e e로 탐색하면 길이 나온다 (근거: 판단 14)"
- 지난 교훈 중 이번 판에서도 맞았던 것은 남기고 끝에 (이어받음)을 붙인다. 틀린 것으로 드러난 것은 고치거나 뺀다.
- 교훈 목록만 출력해라."""
        content = [("text", prompt)]
        if image is not None:
            content += [("text", "[마지막 게임 화면]"), ("image", image)]
        lessons, _, usage = client.ask(content, 1024)
        return lessons, usage


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
    return {"run_id": os.path.basename(run_id), "config": config, "entries": entries, "summary": summary,
            "lessons": read_text(os.path.join(run_dir, LESSONS_FILE)),
            "inherited_lessons": read_text(os.path.join(run_dir, INHERITED_FILE))}


def summarize_run(run_id, demo=False):
    """판단 기록을 AI에게 넘겨 관찰 리포트 요약을 받는다. (그 판과 같은 회사의 가장 저렴한 모델 사용)"""
    run = load_run(run_id)
    if not run:
        raise FileNotFoundError(run_id)
    if demo or run["config"].get("demo"):
        summary = ("데모 기록이라 실제 분석은 하지 않았어요. 실제 판에서는 이 칸에 AI가 판단 기록을 읽고 "
                   "중간 목표의 변화, 위험한 선택, 기억 메모가 행동을 바꾼 순간을 요약해 줘요.")
    else:
        lines = [f"{e['step']}. [목표: {e.get('goal', '')}] [근거: {e.get('basis') or '-'}] {e['thought']} → {e['action_text']}"
                 + (f" (힌트: {'; '.join(e['hints'])})" if e.get("hints") else "")
                 for e in run["entries"]]
        prompt = ("다음은 AI가 던전 게임을 플레이하며 남긴 판단 기록이다. 관찰자를 위해 한국어로 5문장 이내로 요약해라. "
                  "어떤 중간 목표를 세우고 바꿨는지, 위험하거나 인상적인 판단, 추측에 기대 판단한 순간, 실패에서 배운 것을 중심으로.\n\n"
                  + "\n".join(lines[-300:]))
        provider = MODELS.get(run["config"].get("model"), MODELS[DEFAULT_MODEL])["provider"]
        summary, _, _ = LLM(PROVIDERS[provider]["cheap_model"]).ask([("text", prompt)], 800)
    with open(os.path.join(LOGS_DIR, run["run_id"], "summary.txt"), "w", encoding="utf-8") as f:
        f.write(summary)
    return summary
