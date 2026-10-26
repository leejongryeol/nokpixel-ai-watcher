"""게임 창 입력 잠금 - 실행 중에 사람의 마우스·키보드가 게임에 닿지 않게 막는다 (Windows 전용)

AI의 키·클릭(pyautogui = Windows SendInput)은 Windows가 "프로그램이 만든 입력" 표시를 붙여서 그대로 통과한다.
사람 입력만 막는다.
- 마우스: 커서가 게임 창 안쪽에 있을 때 클릭·휠만 막는다 (커서 이동은 막지 않음 → 다른 창 사용, pyautogui 비상 정지 가능)
- 키보드: 게임 창이 맨 앞일 때만 막는다 (다른 창에서 힌트를 칠 수 있음)

AI 작업과 따로 돌도록 별도 프로세스로 실행한다. 훅 처리가 늦으면 Windows가 훅을 말없이 빼기 때문이다.
풀리는 경우: 부모가 terminate() / 부모 프로세스가 죽음 / 게임 창이 사라짐 / 비상 해제 F12 (어느 창에서 눌러도 됨).
프로세스가 어떻게 끝나든 Windows가 훅을 자동으로 뺀다.

단독 실행: python input_lock.py --hwnd <창 번호> --parent <부모 PID>
"""

import argparse
import subprocess
import sys
import threading

UNLOCK_HINT = "비상 해제 F12"


class InputLock:
    """에이전트 쪽에서 잠금 프로세스를 켜고 끄는 창구."""

    def __init__(self):
        self.proc = None
        self.note = ""  # 잠금을 못 걸었거나 비상 해제됐을 때 이유

    def start(self, hwnd, wait=5.0):
        """잠금 프로세스를 띄우고 훅이 걸릴 때까지 기다린다. 걸렸으면 True."""
        import os
        self.stop()
        self.note = ""
        try:
            self.proc = subprocess.Popen(
                [sys.executable, os.path.abspath(__file__), "--hwnd", str(int(hwnd)), "--parent", str(os.getpid())],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as error:
            self.note = f"잠금을 걸지 못했어요: {error}"
            return False
        ready = threading.Event()

        def read_lines():
            for line in self.proc.stdout:
                line = line.strip()
                if line == "READY":
                    ready.set()
                elif line == "UNLOCKED_BY_HOTKEY":
                    self.note = "비상 해제 키로 잠금이 풀렸어요."
        threading.Thread(target=read_lines, daemon=True).start()
        if not ready.wait(wait):
            self.stop()
            self.note = "잠금을 걸지 못했어요 (잠금 프로세스가 응답하지 않음)."
            return False
        return True

    @property
    def active(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        proc, self.proc = self.proc, None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(2)
            except Exception:
                proc.kill()


# ---------------------------------------------------------------------------
# 잠금 프로세스 본체
# ---------------------------------------------------------------------------
def run_lock(hwnd, parent_pid):
    import ctypes
    from ctypes import wintypes
    import tkinter as tk

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # 좌표를 실제 픽셀로 (에이전트와 같게)
    except Exception:
        user32.SetProcessDPIAware()

    LRESULT = ctypes.c_ssize_t
    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = LRESULT
    user32.GetForegroundWindow.restype = wintypes.HWND
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    class MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
    LLMHF_INJECTED, LLKHF_INJECTED = 0x01, 0x10
    # 누름 → 뗌 짝 (뗌만 막으면 다른 창이 버튼이 눌린 채로 남으므로, 누름을 막은 것만 뗌도 막는다)
    BUTTON_DOWN = {0x201: "L", 0x204: "R", 0x207: "M", 0x20B: "X", 0x203: "L", 0x206: "R", 0x209: "M", 0x20D: "X"}
    BUTTON_UP = {0x202: "L", 0x205: "R", 0x208: "M", 0x20C: "X"}
    WHEEL = {0x20A, 0x20E}
    KEY_DOWN, KEY_UP = {0x100, 0x104}, {0x101, 0x105}
    VK_F12 = 0x7B

    blocked_buttons, blocked_keys = set(), set()
    unlocked = [False]  # 비상 해제 요청. 훅 안에서는 tkinter를 부르면 프로그램이 죽어서 표시만 하고, check_unlock()이 끝낸다
    hwnd = wintypes.HWND(hwnd)

    def in_game(pt):
        rect = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        origin = wintypes.POINT(0, 0)
        user32.ClientToScreen(hwnd, ctypes.byref(origin))
        return origin.x <= pt.x < origin.x + rect.right and origin.y <= pt.y < origin.y + rect.bottom

    @HOOKPROC
    def mouse_proc(code, wparam, lparam):
        if code == 0 and not unlocked[0]:
            info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            if not info.flags & LLMHF_INJECTED:
                if wparam in BUTTON_DOWN and in_game(info.pt):
                    blocked_buttons.add(BUTTON_DOWN[wparam])
                    return 1
                if wparam in BUTTON_UP and BUTTON_UP[wparam] in blocked_buttons:
                    blocked_buttons.discard(BUTTON_UP[wparam])
                    return 1
                if wparam in WHEEL and in_game(info.pt):
                    return 1
        return user32.CallNextHookEx(None, code, wparam, lparam)

    @HOOKPROC
    def keyboard_proc(code, wparam, lparam):
        if code == 0 and not unlocked[0]:
            info = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if not info.flags & LLKHF_INJECTED:
                # 비상 해제는 키 하나로 한다. 조합키는 Ctrl·Shift가 먼저 막혀서 눌린 상태를 알 수 없다
                if wparam in KEY_DOWN and info.vkCode == VK_F12:
                    unlocked[0] = True  # 이 순간부터 아무것도 막지 않는다
                    return 1
                if wparam in KEY_DOWN and user32.GetForegroundWindow() == hwnd.value:
                    blocked_keys.add(info.vkCode)
                    return 1
                if wparam in KEY_UP and info.vkCode in blocked_keys:
                    blocked_keys.discard(info.vkCode)
                    return 1
        return user32.CallNextHookEx(None, code, wparam, lparam)

    # 잠긴 표시: 게임 창 제목 표시줄 위에 겹치는 띠 (클릭 통과, 게임 화면 안쪽은 가리지 않음)
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.configure(bg="#3b1f1c")
    tk.Label(root, text=f"🔒 잠김 · AI가 조작 중 · {UNLOCK_HINT}", fg="#f0b0a6", bg="#3b1f1c",
             font=("Malgun Gothic", 10, "bold"), padx=10).pack(fill="both", expand=True)
    root.update_idletasks()
    badge = wintypes.HWND(int(root.wm_frame(), 16))
    GWL_EXSTYLE = -20
    user32.SetWindowLongW(badge, GWL_EXSTYLE, user32.GetWindowLongW(badge, GWL_EXSTYLE)
                          | 0x80000 | 0x20 | 0x80 | 0x8000000)  # 겹침 | 클릭 통과 | 작업 표시줄에 안 보임 | 포커스 안 받음

    SYNCHRONIZE = 0x00100000
    parent = kernel32.OpenProcess(SYNCHRONIZE, False, parent_pid)

    def watch():
        """0.5초마다: 부모·게임 창이 살아 있는지 보고, 띠를 게임 창 제목줄에 맞춘다."""
        if not user32.IsWindow(hwnd) or (parent and kernel32.WaitForSingleObject(parent, 0) == 0):
            root.destroy()
            return
        win, origin = wintypes.RECT(), wintypes.POINT(0, 0)
        user32.GetWindowRect(hwnd, ctypes.byref(win))
        user32.ClientToScreen(hwnd, ctypes.byref(origin))
        title_h = max(24, origin.y - win.top)
        if user32.IsIconic(hwnd):
            root.withdraw()
        else:
            root.deiconify()
            root.geometry(f"{max(200, origin.x - win.left + 720)}x{title_h - 4}+{origin.x}+{win.top + 2}")
        root.after(500, watch)

    def check_unlock():
        """0.1초마다: 비상 해제 요청이 있으면 끝낸다."""
        if unlocked[0]:
            print("UNLOCKED_BY_HOTKEY", flush=True)
            root.destroy()
            return
        root.after(100, check_unlock)

    module = kernel32.GetModuleHandleW(None)
    hooks = [user32.SetWindowsHookExW(WH_MOUSE_LL, mouse_proc, module, 0),
             user32.SetWindowsHookExW(WH_KEYBOARD_LL, keyboard_proc, module, 0)]
    if not all(hooks):
        print("HOOK_FAILED", flush=True)
        return 1
    print("READY", flush=True)
    watch()
    check_unlock()
    root.mainloop()  # tk가 Windows 메시지를 돌려 줘야 저수준 훅이 불린다
    for hook in hooks:
        user32.UnhookWindowsHookEx(hook)
    return 0


def main():
    parser = argparse.ArgumentParser(description="게임 창 입력 잠금 (사람 입력만 막음)")
    parser.add_argument("--hwnd", type=int, required=True, help="잠글 게임 창 번호")
    parser.add_argument("--parent", type=int, default=0, help="이 프로세스가 죽으면 잠금도 푼다")
    args = parser.parse_args()
    sys.exit(run_lock(args.hwnd, args.parent))


if __name__ == "__main__":
    main()
