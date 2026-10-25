"""녹픽셀 AI 감시자 - 관찰 웹 화면

실행: python web.py          → 브라우저에서 http://127.0.0.1:8765 이 열린다
      python web.py --demo   → 게임·API 없이 가짜 판단으로 화면만 확인

화면 흐름: ① 실험 설정(/) → ② 관찰 화면(/observe) → ③ 관찰 리포트(/report)
이 서버는 내 컴퓨터(127.0.0.1)에서만 접속할 수 있다.
"""

import argparse
import os
import threading
import webbrowser

from dotenv import load_dotenv, set_key
from flask import Flask, abort, jsonify, request, send_from_directory

import agent as agent_module
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
    a = current()
    if a and a.status == "running":
        return jsonify({"error": "이미 실험이 진행 중이에요. 관찰 화면에서 먼저 중지하세요."}), 409
    data = request.get_json(force=True)
    model = data.get("model") if data.get("model") in MODELS else DEFAULT_MODEL
    env_name = key_env(model)

    api_key = (data.get("api_key") or "").strip()
    if api_key:  # 새로 입력한 키는 이 컴퓨터의 .env에만, 고른 모델의 회사 이름으로 저장
        if not os.path.exists(ENV_PATH):
            open(ENV_PATH, "a", encoding="utf-8").close()
        set_key(ENV_PATH, env_name, api_key, quote_mode="never")
        os.environ[env_name] = api_key
    if os.path.exists(ENV_PATH):  # 마지막에 고른 모델을 기억
        set_key(ENV_PATH, "MODEL", model, quote_mode="never")

    if not state["demo"] and not os.getenv(env_name):
        return jsonify({"error": f"{PROVIDERS[MODELS[model]['provider']]['name']} API 키를 입력하세요."}), 400

    seed = data.get("seed", "") if data.get("seed_mode") == "fixed" else ""
    try:
        steps = max(1, min(500, int(data.get("steps", 50))))
    except (TypeError, ValueError):
        steps = 50
    new = Agent(player=data.get("player", ""), model=model, guide=bool(data.get("guide")), seed=seed,
                steps=steps, dry_run=bool(data.get("dry_run")), demo=state["demo"],
                lessons_from=data.get("lessons_from") or "")
    state["agent"] = new
    new.start()
    return jsonify({"run_id": new.run_id})


# ---------------- 관찰 ----------------
@app.get("/api/state")
def get_state():
    a = current()
    if not a:
        return jsonify({"status": "none"})
    return jsonify(a.snapshot(last=1000))  # 글만 보내므로 판단 1000개도 가볍다


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


def main():
    parser = argparse.ArgumentParser(description="녹픽셀 AI 감시자 관찰 웹 화면")
    parser.add_argument("--demo", action="store_true", help="게임·API 없이 가짜 판단으로 화면 확인")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않음")
    args = parser.parse_args()

    load_dotenv(ENV_PATH)
    state["demo"] = args.demo
    url = f"http://127.0.0.1:{args.port}"
    print(f"녹픽셀 AI 감시자 {'(데모 모드) ' if args.demo else ''}→ {url}")
    print("끄려면 이 창에서 Ctrl + C")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
