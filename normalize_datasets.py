import json
import re
from pathlib import Path


DATA_DIR = Path(__file__).parent / "data"
TARGET_ITEMS = 567
LANGUAGE_FILES = [
    "c.json",
    "cpp.json",
    "csharp.json",
    "golang.json",
    "java.json",
    "php.json",
    "python.json",
    "reactjs.json",
    "rust.json",
    "sql.json",
]

COMMENT_PREFIX = {
    "c.json": "//",
    "cpp.json": "//",
    "csharp.json": "//",
    "golang.json": "//",
    "java.json": "//",
    "php.json": "//",
    "python.json": "#",
    "reactjs.json": "//",
    "rust.json": "//",
    "sql.json": "--",
}


def add_placeholder(puzzle, syntax):
    if "_" in puzzle:
        return re.sub(r"_+", "___", puzzle)

    return blank_syntax(puzzle)


def blank_syntax(syntax):
    token = re.search(r"[A-Za-z][A-Za-z0-9_]*", syntax)
    if not token:
        return "___" + syntax
    return syntax[: token.start()] + "___" + syntax[token.end() :]


def matches_syntax(puzzle, syntax):
    pattern = re.escape(puzzle).replace(r"___", ".*?")
    return re.fullmatch(pattern, syntax, flags=re.DOTALL) is not None


def unique_topic(topic, used_topics):
    if topic not in used_topics:
        used_topics.add(topic)
        return topic
    suffix = 2
    candidate = f"{topic} - practice {suffix}"
    while candidate in used_topics:
        suffix += 1
        candidate = f"{topic} - practice {suffix}"
    used_topics.add(candidate)
    return candidate


def main():
    for filename in LANGUAGE_FILES:
        path = DATA_DIR / filename
        dataset = json.loads(path.read_text(encoding="utf-8"))
        items = [item for part in dataset["parts"] for item in part["items"]]
        items = items[:TARGET_ITEMS]

        comment = COMMENT_PREFIX[filename]
        source_items = list(items)
        variant_number = 1
        while len(items) < TARGET_ITEMS:
            source = source_items[(len(items) - len(source_items)) % len(source_items)]
            variant = dict(source)
            marker = f"{comment} Practice variant {variant_number}"
            variant["syntax"] = marker + "\n" + source["syntax"]
            variant["puzzle"] = marker + "\n" + source["puzzle"]
            variant["topic"] = f"{source['topic']} - variant {variant_number}"
            items.append(variant)
            variant_number += 1

        used_topics = set()
        for level, item in enumerate(items):
            item["level"] = level
            item["topic"] = unique_topic(item["topic"], used_topics)
            item["puzzle"] = add_placeholder(item["puzzle"], item["syntax"])
            if not matches_syntax(item["puzzle"], item["syntax"]):
                item["puzzle"] = blank_syntax(item["syntax"])

        cursor = 0
        for part in dataset["parts"]:
            count = min(len(part["items"]), TARGET_ITEMS - cursor)
            part["items"] = items[cursor : cursor + count]
            cursor += count
        if cursor < TARGET_ITEMS:
            dataset["parts"].append({
                "part": f"Part {len(dataset['parts']) + 1} - Practice variants",
                "items": items[cursor:],
            })
        dataset["total_items"] = TARGET_ITEMS
        dataset["total_parts"] = len(dataset["parts"])
        path.write_text(json.dumps(dataset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()