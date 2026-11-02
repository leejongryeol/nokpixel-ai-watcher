"""녹픽셀 AI 감시자 - 관찰 웹 화면

실행: python web.py          → 브라우저에서 http://127.0.0.1:8765 이 열린다
      python web.py --demo   → 게임·API 없이 가짜 판단으로 화면만 확인
      python web.py --panels → 관찰 패널(/panel)을 앱 창으로 띄우고 게임 창 오른쪽에 배치
      python web.py --env 경로 → 다른 .env 파일을 쓴다 (시험용. 실제 .env를 건드리지 않음)

실제 판은 게임의 AI 설정 장면에서 고르고 시작한다 (/api/bridge/*, docs/project/bridge.md).
두 창 화면: 게임(실행 중 사람 입력 잠금) / 관찰 패널(/panel, 설정은 읽기만). 판단별 상세는 패널에서 여는 기록 창(/log)
데모 모드에서만: ① 실험 설정(/) → ② 관찰 화면(/observe) → ③ 관찰 리포트(/report)
이 서버는 내 컴퓨터(127.0.0.1)에서만 접속할 수 있다.
"""

import argparse
import atexit
import functools
import os
import re
import shutil
import threading
import webbrowser
from datetime import datetime

from dotenv import load_dotenv, set_key
from flask import Flask, abort, jsonify, redirect, request, send_from_directory

import agent as agent_module
import window_layout
from agent import MODELS, PROVIDERS, DEFAULT_MODEL, Agent, list_runs, load_lessons, load_run, summarize_run

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HERE, "web")
ENV_PATH = os.path.join(HERE, ".env")

app = Flask(__name__, static_folder=os.path.join(WEB_DIR, "static"), static_url_path="/static")
state = {"agent": None, "pending": None, "demo": False}
key_tests = {}  # 회사별 연결 시험 결과 {"ok": bool, "at": 시각}. 메모리에만 두고, 키를 바꾸면 지운다
test_locks = {name: threading.Lock() for name in PROVIDERS}
run_lock = threading.Lock()
TEST_TIMEOUT = 30  # 연결 시험 최대 시간(초)
TEST_PROMPT = "ok라고만 답해."


def current():
    return state["agent"]


def bridge_only(view):
    """다른 웹사이트가 몰래 요청하지 못하게 막는다 (bridge.md 3-3).
    브라우저는 다른 사이트에서 이 헤더를 붙인 요청을 보내기 전에 허락을 묻고, 이 서버는 허락하지 않는다."""
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if request.headers.get("X-Nokpixel-Bridge") != "1" or (request.method == "POST" and not request.is_json):
            return jsonify({"ok": False, "reason": "forbidden", "error": "허용되지 않은 요청이에요."}), 403
        return view(*args, **kwargs)
    return wrapped


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


# ---------------- 화면 ----------------
@app.get("/")
def page_setup():
    if not state["demo"]:  # 실제 판은 게임의 AI 설정에서 시작한다. 옛 설정 화면은 데모 전용
        return redirect("/panel")
    return send_from_directory(WEB_DIR, "setup.html")


@app.get("/observe")
def page_observe():
    return send_from_directory(WEB_DIR, "observe.html")


@app.get("/report")
def page_report():
    return send_from_directory(WEB_DIR, "report.html")


@app.get("/panel")
def page_panel():
    return send_from_directory(WEB_DIR, "panel.html")


@app.get("/log")
def page_log():
    return send_from_directory(WEB_DIR, "log.html")


@app.get("/shots/<run_id>/<name>")
def screenshot(run_id, name):
    if not name.endswith(".png"):
        abort(404)
    return send_from_directory(os.path.join(agent_module.LOGS_DIR, os.path.basename(run_id)), os.path.basename(name))


# ---------------- 설정 ----------------
def lesson_sources():
    """교훈을 남긴 지난 판 목록 (최신 순)"""
    result = []
    for run_id in list_runs():
        if load_lessons(run_id):
            run = load_run(run_id)
            result.append({"run_id": run_id, "player": run["config"].get("player", ""),
                           "model_name": run["config"].get("model_name", ""),
                           "steps": len(run["entries"]), "demo": run["config"].get("demo", False)})
    return result


@app.get("/api/setup-info")
def setup_info():
    a = current()
    return jsonify({
        "models": [{"id": k, "name": v["name"], "provider": v["provider"], "price": v["price"]} for k, v in MODELS.items()],
        "default_model": os.getenv("MODEL", DEFAULT_MODEL),
        "providers": {k: {"name": v["name"], "has_key": bool(os.getenv(v["key_env"]))} for k, v in PROVIDERS.items()},
        "guide_ready": bool(agent_module.load_guide()),
        "lesson_sources": lesson_sources(),
        "demo": state["demo"],
        "running": bool(a and a.status == "running"),
    })


@app.post("/api/start")
@bridge_only
def start():
    """데모 설정 화면(/)에서 시작. 데모 모드에서만 쓴다. .env에는 쓰지 않는다."""
    if not state["demo"]:
        abort(404)
    data = body()
    a = current()
    if a and a.status == "running":
        return jsonify({"error": "이미 실험이 진행 중이에요. 관찰 화면에서 먼저 중지하세요."}), 409
    model = data.get("model") if data.get("model") in MODELS else DEFAULT_MODEL
    seed = data.get("seed", "") if data.get("seed_mode") == "fixed" else ""
    new = Agent(player=str(data.get("player", "")), model=model, guide=bool(data.get("guide")), seed=str(seed),
                steps=clamp_steps(data.get("steps")), dry_run=bool(data.get("dry_run")), demo=True,
                lessons_from=str(data.get("lessons_from") or ""))
    state["agent"] = new
    new.start()
    return jsonify({"run_id": new.run_id})


def clamp_steps(value):
    try:
        return max(1, min(500, int(value)))
    except (TypeError, ValueError):
        return 50


# ---------------- 게임 ↔ Python 통로 (bridge.md 3장) ----------------
def run_label(run_id, config):
    """교훈 목록에 보이는 이름 (예: 10/25 · GPT-6 Luna · 10판단)"""
    match = re.match(r"run_\d{4}(\d\d)(\d\d)_", run_id)
    date = f"{int(match.group(1))}/{int(match.group(2))}" if match else run_id
    return f"{date} · {config.get('model_name', '')} · {config.get('steps', '')}판단"


def key_state(name):
    """키 상태. 키 자체는 끝 4자리만 내보낸다."""
    key = os.getenv(PROVIDERS[name]["key_env"]) or ""
    test = key_tests.get(name) or {}
    return {"present": bool(key), "last4": key[-4:] if len(key) >= 8 else "",
            "tested_ok": bool(key and test.get("ok")), "tested_at": test.get("at", "") if key else ""}


def pending_info():
    p = state["pending"]
    return {"run_id": p.run_id, "config": p.config} if p else None


@app.get("/api/bridge/status")
@bridge_only
def bridge_status():
    a = current()
    return jsonify({
        "bridge_version": 1,
        "demo": state["demo"],
        "running": bool(a and a.status == "running"),
        "models": [{"id": k, "name": v["name"], "provider": v["provider"]} for k, v in MODELS.items()],
        "providers": {name: v["name"] for name, v in PROVIDERS.items()},
        "keys": {name: key_state(name) for name in PROVIDERS},
        "lesson_sources": [{"run_id": r["run_id"], "label": run_label(r["run_id"], r)} for r in lesson_sources()],
        "pending": pending_info(),
    })


@app.post("/api/bridge/key")
@bridge_only
def bridge_key():
    """키를 .env에 그 회사 키 한 줄로만 저장한다. 돌려주는 것은 끝 4자리뿐이다."""
    data = body()
    name = data.get("provider")
    key = data.get("key")
    if name not in PROVIDERS:
        return jsonify({"ok": False, "reason": "bad_provider"}), 400
    key = key.strip() if isinstance(key, str) else ""
    if not (8 <= len(key) <= 300) or re.search(r"[\s\"'#=]", key):  # .env 한 줄을 깨는 글자는 받지 않는다
        return jsonify({"ok": False, "reason": "bad_key"}), 400
    env_name = PROVIDERS[name]["key_env"]
    try:
        if not os.path.exists(ENV_PATH):
            open(ENV_PATH, "a", encoding="utf-8").close()
        set_key(ENV_PATH, env_name, key, quote_mode="never")
    except Exception:  # 오류 문구는 내보내지 않는다
        return jsonify({"ok": False, "reason": "save_failed"}), 500
    os.environ[env_name] = key
    key_tests.pop(name, None)  # 새 키는 다시 시험해야 한다
    return jsonify({"ok": True, "last4": key[-4:]})


def classify_error(error):
    """연결 시험 오류 → reason. 오류 문구에는 키 일부가 섞일 수 있어서 분류에만 쓰고 밖으로 내보내지 않는다."""
    kind = type(error).__name__  # Anthropic·OpenAI 라이브러리의 오류 이름은 같다
    text = str(error).lower()
    if kind == "AuthenticationError":
        return "key_invalid"
    if kind == "APITimeoutError":
        return "timeout"
    if "insufficient_quota" in text or "credit balance" in text:
        return "no_credit"
    if kind in ("NotFoundError", "PermissionDeniedError"):
        return "model_unavailable"
    return "other"


@app.post("/api/bridge/test")
@bridge_only
def bridge_test():
    model = body().get("model")
    if model not in MODELS:
        return jsonify({"ok": False, "reason": "model_unavailable"}), 400
    name = MODELS[model]["provider"]
    if not state["demo"] and not os.getenv(PROVIDERS[name]["key_env"]):
        return jsonify({"ok": False, "reason": "no_key"})
    if not test_locks[name].acquire(blocking=False):  # 같은 회사 시험이 이미 진행 중
        return jsonify({"ok": False, "reason": "other"})
    try:
        if state["demo"]:  # 데모는 API를 부르지 않는다
            reason = "ok"
        else:
            try:
                agent_module.LLM(model, timeout=TEST_TIMEOUT).ask([("text", TEST_PROMPT)], 16)
                reason = "ok"
            except Exception as error:
                reason = classify_error(error)
        key_tests[name] = {"ok": reason == "ok", "at": datetime.now().isoformat(timespec="seconds")}
    finally:
        test_locks[name].release()
    return jsonify({"ok": reason == "ok", "reason": reason})


def clean_id(value, limit):
    return re.sub(r"[^A-Za-z0-9_]", "", str(value or ""))[:limit]


@app.post("/api/bridge/run")
@bridge_only
def bridge_run():
    """판 설정을 받아 Agent와 config.json을 만든다. 아직 시작하지 않는다 (던전 도착 신호는 A-5-4)."""
    data = body()
    model = data.get("model")
    if model not in MODELS:
        return jsonify({"ok": False, "reason": "model_unavailable"}), 400
    with run_lock:
        a = current()
        if a and a.status == "running":
            return jsonify({"ok": False, "reason": "running"}), 409
        if not state["demo"] and not key_state(MODELS[model]["provider"])["tested_ok"]:
            return jsonify({"ok": False, "reason": "not_tested"}), 409
        try:
            challenges = max(0, int(data.get("challenges") or 0))
        except (TypeError, ValueError):
            challenges = 0
        names = data.get("challenge_names")
        custom_seed = str(data.get("custom_seed") or "").strip()[:40]
        game_run = {
            "hero_class": clean_id(data.get("hero_class"), 20),
            "challenges": challenges,
            "challenge_names": [clean_id(n, 40) for n in names][:20] if isinstance(names, list) else [],
            "custom_seed": custom_seed,
        }
        try:
            new = Agent(player=str(data.get("player") or "")[:16], model=model, guide=bool(data.get("guide")),
                        seed=custom_seed, steps=clamp_steps(data.get("steps")), dry_run=bool(data.get("dry_run")),
                        demo=state["demo"], lessons_from=str(data.get("lessons_from") or ""), lock_input=True,
                        game_run=game_run)
            new.prepare()
        except Exception:
            return jsonify({"ok": False, "reason": "other"}), 500
        old, state["pending"] = state["pending"], new
        discard_pending_dir(old, keep=new.run_dir)
    return jsonify({"ok": True, "run_id": new.run_id})


@app.post("/api/bridge/arrived")
@bridge_only
def bridge_arrived():
    """⑤ 던전 도착: 대기 중 판과 run_id가 같을 때만 받아서 AI를 시작한다. 실제 시드는 config.json에만 더한다."""
    data = body()
    with run_lock:
        p = state["pending"]
        if not p or data.get("run_id") != p.run_id:
            return jsonify({"ok": False, "reason": "not_pending"}), 409
        a = current()
        if a and a.status == "running":
            return jsonify({"ok": False, "reason": "running"}), 409
        try:
            depth = int(data.get("depth") or 0)
        except (TypeError, ValueError):
            depth = 0
        p.arrived(re.sub(r"[^A-Za-z0-9-]", "", str(data.get("seed_code") or ""))[:20], depth)
        state["agent"], state["pending"] = p, None
        p.start()
    return jsonify({"ok": True})


def running_agent(run_id):
    a = current()
    return a if a and a.status == "running" and run_id == a.run_id else None


def int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@app.post("/api/bridge/heartbeat")
@bridge_only
def bridge_heartbeat():
    """⑦ 게임이 AI 판 동안 1초마다 보내는 살아 있음 신호. ok가 false면 게임은 신호를 멈춘다."""
    data = body()
    a = running_agent(data.get("run_id"))
    if not a:
        return jsonify({"ok": False, "reason": "not_running"}), 409
    a.heartbeat(data.get("alive") is not False, int_or_none(data.get("depth")))
    return jsonify({"ok": True})


@app.post("/api/bridge/ended")
@bridge_only
def bridge_ended():
    """⑥ 판 끝 (died / won / quit). 받으면 바로 키 보내기를 멈추고 입력 잠금을 푼다."""
    data = body()
    reason = data.get("reason")
    if reason not in ("died", "won", "quit"):
        return jsonify({"ok": False, "reason": "bad_reason"}), 400
    a = running_agent(data.get("run_id"))
    if not a:
        return jsonify({"ok": False, "reason": "not_running"}), 409
    a.end_game(reason, int_or_none(data.get("depth")))
    return jsonify({"ok": True})


def discard_pending_dir(old, keep):
    """바뀐 대기 판의 폴더는 config.json만 있으면 지운다 (판단 기록이 있는 폴더는 지우지 않는다)."""
    if not old or os.path.normcase(old.run_dir) == os.path.normcase(keep):
        return
    try:
        if os.listdir(old.run_dir) == ["config.json"]:
            shutil.rmtree(old.run_dir)
    except OSError:
        pass


# ---------------- 관찰 ----------------
@app.get("/api/state")
def get_state():
    a = current()
    if not a:
        return jsonify({"status": "none", "pending": pending_info()})
    since = request.args.get("since", type=int)  # 관찰 패널·기록 창은 새 판단만 받아 간다
    snap = a.snapshot(since=since) if since is not None else a.snapshot(last=1000)  # 글만 보내므로 판단 1000개도 가볍다
    snap["pending"] = pending_info()
    return jsonify(snap)


@app.post("/api/typing")
@bridge_only
def typing():
    a = current()
    if a and a.status == "running":
        a.set_typing(bool(body().get("on")))
    return jsonify({"ok": True})


@app.post("/api/focus")
@bridge_only
def focus_game():
    a = current()
    if not a or a.status != "running":
        return jsonify({"error": "진행 중인 실험이 없어요."}), 400
    if not a.focus_game():
        return jsonify({"error": "게임 창을 앞으로 가져오지 못했어요. 잠시 뒤 다시 눌러 보세요."}), 409
    return jsonify({"ok": True})


@app.post("/api/layout")
@bridge_only
def layout():
    return jsonify(window_layout.arrange())


@app.post("/api/hint")
@bridge_only
def hint():
    a = current()
    if not a or a.status != "running":
        return jsonify({"error": "진행 중인 실험이 없어요."}), 400
    a.add_hint(str(body().get("text", "")))
    return jsonify({"ok": True})


@app.post("/api/stop")
@bridge_only
def stop():
    a = current()
    if a:
        a.stop()
    return jsonify({"ok": True})


# ---------------- 리포트 ----------------
@app.get("/api/runs")
def runs():
    result = []
    for run_id in list_runs():
        run = load_run(run_id)
        if run:
            result.append({"run_id": run_id, "player": run["config"].get("player", ""),
                           "model_name": run["config"].get("model_name", ""),
                           "steps": len(run["entries"]), "demo": run["config"].get("demo", False)})
    return jsonify(result)


@app.get("/api/run/<run_id>")
def run_detail(run_id):
    run = load_run(run_id)
    if not run:
        abort(404)
    return jsonify(run)


@app.post("/api/run/<run_id>/summary")
@bridge_only
def run_summary(run_id):
    try:
        return jsonify({"summary": summarize_run(run_id, demo=state["demo"])})
    except FileNotFoundError:
        abort(404)
    except Exception as error:
        return jsonify({"error": f"요약을 만들지 못했어요: {error}"}), 500


def release_lock():
    """서버가 끝날 때 입력 잠금을 확실히 푼다 (잠금 프로세스도 부모가 죽으면 스스로 끝난다)."""
    a = current()
    if a and a.input_lock is not None:
        a.stop()
        a.input_lock.stop()


def main():
    parser = argparse.ArgumentParser(description="녹픽셀 AI 감시자 관찰 웹 화면")
    parser.add_argument("--demo", action="store_true", help="게임·API 없이 가짜 판단으로 화면 확인")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    parser.add_argument("--panels", action="store_true", help="관찰 패널을 앱 창으로 띄우고 게임 창 옆에 배치")
    parser.add_argument("--env", help="키를 읽고 저장할 .env 파일 (기본: ai-bridge/.env). 시험할 때 실제 .env 대신 쓴다")
    args = parser.parse_args()

    global ENV_PATH
    if args.env:
        ENV_PATH = os.path.abspath(args.env)
    load_dotenv(ENV_PATH)
    state["demo"] = args.demo
    atexit.register(release_lock)
    url = f"http://127.0.0.1:{args.port}"
    print(f"녹픽셀 AI 감시자 {'(데모 모드) ' if args.demo else ''}→ {url}")
    if args.env:
        print(f"키 파일: {ENV_PATH}")
    print("끄려면 이 창에서 Ctrl + C")
    if args.panels:
        def open_and_arrange():
            window_layout.open_panel(url)
            window_layout.arrange_when_ready()
        threading.Timer(1.0, open_and_arrange).start()
    elif not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    # Flask는 python-dotenv가 있으면 실행 폴더의 .env를 스스로 읽는다. --env로 고른 파일만 쓰도록 끈다
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True, load_dotenv=False)


if __name__ == "__main__":
    main()
