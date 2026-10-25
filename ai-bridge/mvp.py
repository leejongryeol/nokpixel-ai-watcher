"""녹픽셀 AI 감시자 - 명령줄 실행

관찰 웹 화면 없이 콘솔에서 바로 AI를 돌려볼 때 쓴다. (웹 화면은 web.py)

사용법
  python mvp.py --dry-run        # AI가 보고 생각만 함 (조작 안 함). 처음엔 이걸로!
  python mvp.py --steps 20       # AI가 20번 판단하며 실제로 플레이
  python mvp.py --demo           # 게임·API 없이 가짜 판단으로 흐름만 확인
  python mvp.py --model gpt-6-luna --dry-run   # 모델 고르기 (기본: .env의 MODEL, 없으면 Haiku 4.5)
  중지: Ctrl + C (또는 마우스를 화면 왼쪽 위 구석으로 이동)
"""

import argparse
import os
import sys
import time

from dotenv import load_dotenv

from agent import Agent, DEFAULT_MODEL, MODELS, key_env


def main():
    parser = argparse.ArgumentParser(description="녹픽셀 AI 감시자 (명령줄)")
    parser.add_argument("--steps", type=int, default=10, help="AI가 판단할 횟수 (기본 10)")
    parser.add_argument("--dry-run", action="store_true", help="AI가 생각만 하고 조작하지 않음")
    parser.add_argument("--demo", action="store_true", help="게임·API 없이 가짜 판단")
    parser.add_argument("--guide", action="store_true", help="공략 문서(guide.md) 제공")
    parser.add_argument("--player", default="cli", help="플레이어 이름 (기록 폴더 이름)")
    parser.add_argument("--lessons-from", default="", help="이 판(logs/의 폴더 이름)에서 AI가 쓴 교훈을 이어받음")
    parser.add_argument("--model", choices=list(MODELS), help="AI 모델 (기본: .env의 MODEL, 없으면 Haiku 4.5)")
    args = parser.parse_args()

    load_dotenv()
    model = args.model or os.getenv("MODEL", DEFAULT_MODEL)
    if not args.demo and not os.getenv(key_env(model)):
        sys.exit(f".env 파일에 {key_env(model)}가 없어요. ai-bridge/README.md를 확인하세요.")

    agent = Agent(player=args.player, model=model, guide=args.guide,
                  steps=args.steps, dry_run=args.dry_run, demo=args.demo, lessons_from=args.lessons_from)
    if args.lessons_from and not agent.inherited_lessons:
        sys.exit(f"{args.lessons_from} 폴더에 교훈(lessons.md)이 없어요.")
    print(f"모델: {agent.config['model_name']} | 판단 {args.steps}번 | "
          f"{'데모' if args.demo else '생각만 (dry-run)' if args.dry_run else '실제 플레이'}")
    print(f"기록 폴더: {agent.run_dir}\n중지: Ctrl + C\n")

    agent.start()
    shown = 0
    try:
        while agent.status in ("ready", "running") or shown < len(agent.entries):
            for e in agent.entries[shown:]:
                print(f"━━ {e['step']}번째 판단 ━━" + (f"  [큰 점검 · {e['checkpoint']}]" if e.get("checkpoint") else ""))
                print(f"🧠 생각: {e['thought'] or '(생각 없음)'}")
                if e["goal"]:
                    print(f"🗺️ 중간 목표: {e['goal']}{' (변경)' if e['goal_changed'] else ''}")
                if e["speech"]:
                    print(f"💬 \"{e['speech']}\"")
                print(f"🎮 행동: {e['action_text']}")
                if e.get("check_goal") or e.get("basis"):
                    print(f"🎯 되새김: {e.get('check_goal', '')}  👀 근거: {e.get('basis') or '-'}")
                if e["memo_add"]:
                    print(f"📝 기억 메모 추가 {e.get('memo_add_id', '')}: {e['memo_add']}")
                if e.get("memo_removed"):
                    print(f"🗑️ 기억 메모 지움: {e['memo_removed']}")
                print(f"🪙 토큰 입력 {e['input_tokens']} / 출력 {e['output_tokens']} · 약 ${e['cost_usd']:.4f}\n")
            shown = len(agent.entries)
            time.sleep(0.3)
    except KeyboardInterrupt:
        agent.stop()
        print("\n중지하는 중...")
        while agent.status == "running":
            time.sleep(0.2)

    if agent.lessons:
        print(f"\n📜 다음 판에 남긴 교훈 (lessons.md)\n{agent.lessons}")
    if agent.status == "error":
        print(f"[오류] {agent.error}")
    print(f"끝! 총 비용 약 ${agent.total_cost:.3f} · 기록: {agent.run_dir}")


if __name__ == "__main__":
    main()
