"""세 창 배치 - 게임(왼쪽 위) / 지금 AI는(게임 아래) / 판단 기록(오른쪽)을 정해진 자리에 놓는다 (Windows 전용)

작업 표시줄을 뺀 영역(SPI_GETWORKAREA) 안에 놓는다. 게임 창은 옮기기만 하고 크기는 바꾸지 않는다.
창2·창3은 Edge(없으면 Chrome)의 앱 창(--app, 주소창·탭 없음)으로 띄운다.
"""

import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.path.join(HERE, ".app-profile")  # 앱 창 전용 브라우저 프로필 (GitHub에 올리지 않음)
GAME_WINDOW_TITLE = "Shattered Pixel Dungeon"
NOW_TITLE = "지금 AI는 · 녹픽셀"  # web/now.html의 <title>
CONSOLE_TITLE = "판단 기록 · 녹픽셀"  # web/console.html의 <title>
DEFAULT_GAME_SIZE = (722, 440)  # 게임 창을 못 찾았을 때 비워 둘 자리 (125% 배율 기준 실제 픽셀)
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def _win():
    import ctypes
    from ctypes import wintypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 실제 픽셀 좌표 (이미 설정돼 있으면 무시됨)
    except Exception:
        pass
    return ctypes, wintypes, ctypes.windll.user32


def work_area():
    ctypes, wintypes, user32 = _win()
    rect = wintypes.RECT()
    user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    return rect.left, rect.top, rect.right, rect.bottom


def find_window(title_part):
    """제목에 title_part가 들어간 보이는 창 하나 (없으면 0)."""
    ctypes, wintypes, user32 = _win()
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                if title_part in buffer.value:
                    found.append(hwnd)
                    return False
        return True

    user32.EnumWindows(each, 0)
    return found[0] if found else 0


def _margins(hwnd):
    """Windows 11 창 둘레의 보이지 않는 테두리 두께 (왼, 위, 오른, 아래)."""
    ctypes, wintypes, user32 = _win()
    outer, visible = wintypes.RECT(), wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(outer))
    if ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(visible), ctypes.sizeof(visible)) != 0:
        return (0, 0, 0, 0), outer
    return (visible.left - outer.left, visible.top - outer.top,
            outer.right - visible.right, outer.bottom - visible.bottom), visible


def _place(hwnd, x, y, w=None, h=None):
    """보이는 테두리 기준으로 (x, y)에 놓는다. w, h가 없으면 크기는 그대로."""
    ctypes, wintypes, user32 = _win()
    if user32.IsIconic(hwnd) or user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd, 9)  # 최소화·최대화 풀기
    (ml, mt, mr, mb), _ = _margins(hwnd)
    flags = 0x0010  # 포커스는 안 가져가고 다른 창들 위로 올림 (HWND_TOP)
    if w is None:
        user32.SetWindowPos(hwnd, 0, x - ml, y - mt, 0, 0, flags | 0x0001)  # 크기 유지
    else:
        user32.SetWindowPos(hwnd, 0, x - ml, y - mt, w + ml + mr, h + mt + mb, flags)
    # HWND_TOP만으로는 안 올라올 때가 있어서, 잠깐 맨 위 고정했다가 풀고 한 번 더 올린다
    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags | 0x0001 | 0x0002)  # HWND_TOPMOST, 위치·크기 유지
    user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, flags | 0x0001 | 0x0002)  # HWND_NOTOPMOST
    user32.BringWindowToTop(hwnd)


def arrange():
    """세 창을 자리에 놓는다. 무엇을 놓았는지 돌려준다."""
    if sys.platform != "win32":
        return {"error": "창 배치는 Windows에서만 돼요."}
    ctypes, wintypes, user32 = _win()
    left, top, right, bottom = work_area()
    result = {"work_area": [left, top, right, bottom]}
    # 뒤에 있는 프로그램은 창을 다른 창 위로 올릴 수 없어서, 지금 맨 앞 창의 입력 흐름에 잠깐 붙는다
    fg_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
    my_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(my_thread, fg_thread, True)
    try:
        _arrange_three(user32, left, top, right, bottom, result)
    finally:
        user32.AttachThreadInput(my_thread, fg_thread, False)
    return result


def _arrange_three(user32, left, top, right, bottom, result):
    game = user32.FindWindowW(None, GAME_WINDOW_TITLE)
    game_w, game_h = DEFAULT_GAME_SIZE
    if game:
        _place(game, left, top)
        _, visible = _margins(game)
        game_w, game_h = visible.right - visible.left, visible.bottom - visible.top
    result["game"] = bool(game)

    now = find_window(NOW_TITLE)
    if now:
        _place(now, left, top + game_h, game_w, bottom - top - game_h)
    result["now"] = bool(now)

    console = find_window(CONSOLE_TITLE)
    if console:
        _place(console, left + game_w, top, right - left - game_w, bottom - top)
    result["console"] = bool(console)


def open_panels(base_url):
    """창2·창3을 앱 창으로 띄운다. 쓴 브라우저 이름 (없으면 보통 브라우저 탭으로 열고 None)."""
    browser = next((path for path in BROWSERS if os.path.exists(path)), None) or shutil.which("msedge")
    if not browser:
        webbrowser.open(base_url + "/console")
        webbrowser.open(base_url + "/now")
        return None
    for path in ("/console", "/now"):
        subprocess.Popen([browser, f"--app={base_url}{path}", f"--user-data-dir={PROFILE_DIR}",
                          "--no-first-run", "--no-default-browser-check"])
    return os.path.basename(browser)


def arrange_when_ready(timeout=15.0):
    """앱 창 제목이 뜰 때까지 기다렸다가 배치한다 (뒤에서 실행)."""
    def wait_and_arrange():
        deadline = time.time() + timeout
        while time.time() < deadline:
            if find_window(NOW_TITLE) and find_window(CONSOLE_TITLE):
                time.sleep(0.5)
                break
            time.sleep(0.5)
        arrange()
    threading.Thread(target=wait_and_arrange, daemon=True).start()
