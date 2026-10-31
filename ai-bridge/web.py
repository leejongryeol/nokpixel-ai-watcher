"""녹픽셀 AI 감시자 - 관찰 웹 화면

실행: python web.py          → 브라우저에서 http://127.0.0.1:8765 이 열린다
      python web.py --demo   → 게임·API 없이 가짜 판단으로 화면만 확인
      python web.py --panels → 관찰 패널(/panel)을 앱 창으로 띄우고 게임 창 오른쪽에 배치

화면 흐름: ① 실험 설정(/) → ② 관찰 화면(/observe) → ③ 관찰 리포트(/report)
두 창 화면: 게임(실행 중 사람 입력 잠금) / 관찰 패널(/panel). 판단별 상세는 패널에서 여는 기록 창(/log)
이 서버는 내 컴퓨터(127.0.0.1)에서만 접속할 수 있다.
"""

import argparse
import atexit
import os
import threading
import webbrowser

from dotenv import load_dotenv, set_key
from flask import Flask, abort, jsonify, request, send_from_directory

import agent as agent_module
import window_layout
from agent import MODELS, PROVIDERS, DEFAULT_MODEL, Agent, key_env, list_runs, load_lessons, load_run, summarize_run

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HERE, "web")
ENV_PATH = os.path.join(HERE, ".env")

app = Flask(__name__, static_folder=os.path.join(WEB_DIR, "static"), static_url_path="/static")
state = {"agent": None, "demo": False}


def current():
    return state["agent"]


# ---------------- 화면 ----------------
@app.get("/")
def page_setup():
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
def start():
    return _start_agent(request.get_json(force=True), save_env=True, lock_input=False)


@app.post("/api/console/start")
def console_start():
    """관찰 패널에서 시작: .env에 쓰지 않고, 실행 중에는 게임 창의 사람 입력을 잠근다."""
    return _start_agent(request.get_json(force=True), save_env=False, lock_input=True)


def _start_agent(data, save_env, lock_input):
    a = current()
    if a and a.status == "running":
        return jsonify({"error": "이미 실험이 진행 중이에요. 관찰 화면에서 먼저 중지하세요."}), 409
    model = data.get("model") if data.get("model") in MODELS else DEFAULT_MODEL
    env_name = key_env(model)

    if save_env:
        api_key = (data.get("api_key") or "").strip()
        if api_key:  # 새로 입력한 키는 이 컴퓨터의 .env에만, 고른 모델의 회사 이름으로 저장
            if not os.path.exists(ENV_PATH):
                open(ENV_PATH, "a", encoding="utf-8").close()
            set_key(ENV_PATH, env_name, api_key, quote_mode="never")
            os.environ[env_name] = api_key
        if os.path.exists(ENV_PATH):  # 마지막에 고른 모델을 기억
            set_key(ENV_PATH, "MODEL", model, quote_mode="never")

    if not state["demo"] and not os.getenv(env_name):
        provider_name = PROVIDERS[MODELS[model]["provider"]]["name"]
        if save_env:
            return jsonify({"error": f"{provider_name} API 키를 입력하세요."}), 400
        return jsonify({"error": f"{provider_name} API 키가 없어요. 실험 설정 화면(/)에서 키를 먼저 넣어 주세요."}), 400

    seed = data.get("seed", "") if data.get("seed_mode") == "fixed" else ""
    try:
        steps = max(1, min(500, int(data.get("steps", 50))))
    except (TypeError, ValueError):
        steps = 50
    new = Agent(player=data.get("player", ""), model=model, guide=bool(data.get("guide")), seed=seed,
                steps=steps, dry_run=bool(data.get("dry_run")), demo=state["demo"],
                lessons_from=data.get("lessons_from") or "", lock_input=lock_input)
    state["agent"] = new
    new.start()
    return jsonify({"run_id": new.run_id})


# ---------------- 관찰 ----------------
@app.get("/api/state")
def get_state():
    a = current()
    if not a:
        return jsonify({"status": "none"})
    since = request.args.get("since", type=int)  # 관찰 패널·기록 창은 새 판단만 받아 간다
    if since is not None:
        return jsonify(a.snapshot(since=since))
    return jsonify(a.snapshot(last=1000))  # 글만 보내므로 판단 1000개도 가볍다


@app.post("/api/typing")
def typing():
    a = current()
    if a and a.status == "running":
        a.set_typing(bool(request.get_json(force=True).get("on")))
    return jsonify({"ok": True})


@app.post("/api/focus")
def focus_game():
    a = current()
    if not a or a.status != "running":
        return jsonify({"error": "진행 중인 실험이 없어요."}), 400
    if not a.focus_game():
        return jsonify({"error": "게임 창을 앞으로 가져오지 못했어요. 잠시 뒤 다시 눌러 보세요."}), 409
    return jsonify({"ok": True})


@app.post("/api/layout")
def layout():
    return jsonify(window_layout.arrange())


@app.post("/api/hint")
def hint():
    a = current()
    if not a or a.status != "running":
        return jsonify({"error": "진행 중인 실험이 없어요."}), 400
    a.add_hint(request.get_json(force=True).get("text", ""))
    return jsonify({"ok": True})


@app.post("/api/stop")
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
    args = parser.parse_args()

    load_dotenv(ENV_PATH)
    state["demo"] = args.demo
    atexit.register(release_lock)
    url = f"http://127.0.0.1:{args.port}"
    print(f"녹픽셀 AI 감시자 {'(데모 모드) ' if args.demo else ''}→ {url}")
    print("끄려면 이 창에서 Ctrl + C")
    if args.panels:
        def open_and_arrange():
            window_layout.open_panel(url)
            window_layout.arrange_when_ready()
        threading.Timer(1.0, open_and_arrange).start()
    elif not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
