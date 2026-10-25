"""AI API 연결 테스트.

실행: python test_connection.py              → .env에 키가 있는 회사(Claude / OpenAI)마다 가장 저렴한 모델로 확인
      python test_connection.py gpt-6-luna   → 그 모델 하나만 확인
성공하면 AI가 녹픽던 캐릭터처럼 한국어로 한마디 합니다.
"""

import os
import sys

from dotenv import load_dotenv

from agent import MODELS, PROVIDERS, LLM, key_env

PROMPT = "너는 던전 탐험을 막 시작한 모험가야. 지하 1층 계단 앞에서 각오를 한 문장으로 말해줘. 한국어로."


def check(model):
    print(f"── {MODELS[model]['name']} ({model})")
    try:
        text, _, usage = LLM(model).ask([("text", PROMPT)], 200)
    except Exception as error:
        print(f"   실패: {error}")
        return False
    print(f"   AI: {text}")
    print(f"   [토큰] 입력 {usage['input_tokens']} / 출력 {usage['output_tokens']}")
    print("   연결 성공!")
    return True


def main() -> None:
    load_dotenv()
    if len(sys.argv) > 1:
        model = sys.argv[1]
        if model not in MODELS:
            sys.exit(f"모르는 모델이에요: {model}\n고를 수 있는 모델: {', '.join(MODELS)}")
        if not os.getenv(key_env(model)):
            sys.exit(f".env 파일에 {key_env(model)}가 없어요. ai-bridge/README.md를 확인하세요.")
        models = [model]
    else:
        models = [p["cheap_model"] for p in PROVIDERS.values() if os.getenv(p["key_env"])]
        if not models:
            sys.exit(".env 파일에 ANTHROPIC_API_KEY나 OPENAI_API_KEY가 없어요. ai-bridge/README.md를 확인하세요.")
    results = [check(m) for m in models]
    if not all(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
