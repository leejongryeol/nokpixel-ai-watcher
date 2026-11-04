"""숨김 검사: 게임이 보낸 상태(logs/<판>/states/*.json)에 숨겨야 할 글자가 새지 않았는지 찾는다.

금지 글자 (docs/project/game-state.md 2-1):
- 그 판의 시드 코드(config.json의 seed_code, 대시 있음·없음)와 시드 숫자
- 게임 코드 패키지 이름 com.shatteredpixel
- 아이템·적 클래스 이름 (저장소의 items/, actors/mobs/ 아래 .java 파일 이름)
  예: PotionOfHealing. 한 단어 이름(Rat, Gnoll)은 영어 게임의 화면 이름과 겹쳐서 뺀다.

판이 끝날 때 agent.py가 자동으로 부르고 결과를 config.json의 hidden_check에 남긴다.
직접 실행: python check_hidden.py <run_id> [--extra 글자 ...]
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(HERE, "logs")
STATES_DIR = "states"
GAME_SRC = os.path.join(HERE, "..", "core", "src", "main", "java", "com", "shatteredpixel", "shatteredpixeldungeon")
CLASS_DIRS = ["items", os.path.join("actors", "mobs")]
CAMEL = re.compile(r"(?:[A-Z][a-z0-9]+){2,}")  # 대문자로 시작하는 덩이가 둘 이상 (PotionOfHealing)


def class_names(src=GAME_SRC):
    """아이템·적 클래스 이름 목록. 저장소에 게임 코드가 없으면 빈 목록."""
    names = set()
    for sub in CLASS_DIRS:
        for root, _, files in os.walk(os.path.join(src, sub)):
            for name in files:
                stem = name[:-5] if name.endswith(".java") else ""
                if CAMEL.fullmatch(stem):
                    names.add(stem)
    return sorted(names)


def seed_number(code):
    """시드 코드(ABC-DEF-GHI) → 숫자. 게임의 DungeonSeed.convertFromCode와 같은 식. 틀린 코드면 None."""
    letters = re.sub(r"[-\s]", "", code or "").upper()
    if not re.fullmatch(r"[A-Z]{9}", letters):
        return None
    result = 0
    for c in letters:
        result = result * 26 + (ord(c) - 65)
    return result


def forbidden_words(config, extra=()):
    words = ["com.shatteredpixel"]
    code = (config.get("seed_code") or "").strip()
    if code:
        words += [code, code.replace("-", "")]
        number = seed_number(code)
        if number is not None and number >= 100000:  # 너무 짧은 숫자는 다른 숫자와 우연히 겹친다
            words.append(str(number))
    words += class_names()
    words += [w for w in extra if w]
    return list(dict.fromkeys(words))


def check_run(run_dir, extra=()):
    """판 폴더 하나를 검사한다. result: clean(없음) / found(찾음) / no_states(상태 없음)."""
    try:
        with open(os.path.join(run_dir, "config.json"), encoding="utf-8") as f:
            config = json.load(f)
    except (FileNotFoundError, ValueError):
        config = {}
    words = forbidden_words(config, extra)
    patterns = [(w, re.compile(r"(?<![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])")) for w in words]
    states_dir = os.path.join(run_dir, STATES_DIR)
    files = sorted(n for n in os.listdir(states_dir) if n.endswith(".json")) if os.path.isdir(states_dir) else []
    found = []
    for name in files:
        with open(os.path.join(states_dir, name), encoding="utf-8") as f:
            text = f.read()
        hits = [w for w, p in patterns if p.search(text)]
        if hits:
            found.append({"file": name, "found": hits})
    return {
        "result": "found" if found else ("clean" if files else "no_states"),
        "checked": len(files),
        "words": len(words),
        "files": found,
        "at": datetime.now().isoformat(timespec="seconds"),
    }


def main():
    parser = argparse.ArgumentParser(description="게임 상태에 숨길 글자가 새지 않았는지 검사")
    parser.add_argument("run_id", help="logs 아래 판 폴더 이름")
    parser.add_argument("--extra", nargs="*", default=[], help="더 찾을 글자 (시험용)")
    args = parser.parse_args()
    result = check_run(os.path.join(LOGS_DIR, os.path.basename(args.run_id)), args.extra)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(1 if result["result"] == "found" else 0)


if __name__ == "__main__":
    main()
