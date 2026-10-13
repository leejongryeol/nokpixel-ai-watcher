"""Claude API 연결 테스트.

실행: python test_connection.py
성공하면 AI가 녹픽던 캐릭터처럼 한국어로 한마디 합니다.
"""

import os
import sys

from dotenv import load_dotenv
import anthropic

# 테스트는 가장 저렴한 모델로 합니다.
MODEL = "claude-haiku-4-5-20251001"


def main() -> None:
    load_dotenv()
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit(".env 파일에 ANTHROPIC_API_KEY가 없어요. ai-bridge/README.md를 확인하세요.")

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=MODEL,
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": (
                    "너는 던전 탐험을 막 시작한 모험가야. "
                    "지하 1층 계단 앞에서 각오를 한 문장으로 말해줘. 한국어로."
                ),
            }
        ],
    )

    print("AI:", message.content[0].text)
    print(f"\n[토큰] 입력 {message.usage.input_tokens} / 출력 {message.usage.output_tokens}")
    print("연결 성공!")


if __name__ == "__main__":
    main()
