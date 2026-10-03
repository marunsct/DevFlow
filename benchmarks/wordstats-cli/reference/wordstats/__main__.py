import argparse
import json
import re
import sys
from collections import Counter

WORD = re.compile(r"[A-Za-z0-9']+")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="wordstats")
    parser.add_argument("file")
    parser.add_argument("--top", type=int)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
    except OSError as error:
        print(f"wordstats: {error}", file=sys.stderr)
        return 2
    words = WORD.findall(text)
    if args.top is not None:
        counts = Counter(word.lower() for word in words)
        top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[: args.top]
        if args.json:
            print(json.dumps({"top": [{"word": w, "count": c} for w, c in top]}))
        else:
            for word, count in top:
                print(f"{word} {count}")
        return 0
    stats = {"words": len(words), "lines": len(text.splitlines()), "characters": len(text)}
    if args.json:
        print(json.dumps(stats))
    else:
        for key, value in stats.items():
            print(f"{key}: {value}")
    return 0


sys.exit(main())
