"""녹픽셀 AI 감시자 - 명령줄 실행

관찰 웹 화면 없이 콘솔에서 바로 AI를 돌려볼 때 쓴다. (웹 화면은 web.py)

사용법
  python mvp.py --dry-run        # AI가 보고 생각만 함 (조작 안 함). 처음엔 이걸로!
  python mvp.py --steps 20       # AI가 20번 판단하며 실제로 플레이
  python mvp.py --demo           # 게임·API 없이 가짜 판단으로 흐름만 확인
  중지: Ctrl + C (또는 마우스를 화면 왼쪽 위 구석으로 이동)
"""

import argparse
import os
import sys
import time

from dotenv import load_dotenv

from agent import Agent, DEFAULT_MODEL


def main():
    parser = argparse.ArgumentParser(description="녹픽셀 AI 감시자 (명령줄)")
    parser.add_argument("--steps", type=int, default=10, help="AI가 판단할 횟수 (기본 10)")
    parser.add_argument("--dry-run", action="store_true", help="AI가 생각만 하고 조작하지 않음")
    parser.add_argument("--demo", action="store_true", help="게임·API 없이 가짜 판단")
    parser.add_argument("--guide", action="store_true", help="공략 문서(guide.md) 제공")
    parser.add_argument("--player", default="cli", help="플레이어 이름 (기록 폴더 이름)")
    args = parser.parse_args()

    load_dotenv()
    if not args.demo and not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit(".env 파일에 ANTHROPIC_API_KEY가 없어요. ai-bridge/README.md를 확인하세요.")

    agent = Agent(player=args.player, model=os.getenv("MODEL", DEFAULT_MODEL), guide=args.guide,
                  steps=args.steps, dry_run=args.dry_run, demo=args.demo)
    print(f"모델: {agent.config['model_name']} | 판단 {args.steps}번 | "
          f"{'데모' if args.demo else '생각만 (dry-run)' if args.dry_run else '실제 플레이'}")
    print(f"기록 폴더: {agent.run_dir}\n중지: Ctrl + C\n")

    agent.start()
    shown = 0
    try:
        while agent.status in ("ready", "running") or shown < len(agent.entries):
            for e in agent.entries[shown:]:
                print(f"━━ {e['step']}번째 판단 ━━")
                print(f"🧠 생각: {e['thought'] or '(생각 없음)'}")
                if e["goal"]:
                    print(f"🗺️ 중간 목표: {e['goal']}{' (변경)' if e['goal_changed'] else ''}")
                if e["speech"]:
                    print(f"💬 \"{e['speech']}\"")
                print(f"🎮 행동: {e['action_text']}")
                if e["memo_add"]:
                    print(f"📝 기억 메모 추가: {e['memo_add']}")
                print(f"🪙 토큰 입력 {e['input_tokens']} / 출력 {e['output_tokens']} · 약 ${e['cost_usd']:.4f}\n")
            shown = len(agent.entries)
            time.sleep(0.3)
    except KeyboardInterrupt:
        agent.stop()
        print("\n중지하는 중...")
        while agent.status == "running":
            time.sleep(0.2)

    if agent.status == "error":
        print(f"[오류] {agent.error}")
    print(f"끝! 총 비용 약 ${agent.total_cost:.3f} · 기록: {agent.run_dir}")


if __name__ == "__main__":
    main()
