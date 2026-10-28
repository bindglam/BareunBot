import argparse
import json
import os
import random

VARIATIONS = {
  "초성", "영타", "자모분리", "특수문자", "띄어쓰기", "숫자치환", "긴 글 감싸기", "판정 조작 결합", "오타",
  "일반어 초성", "일반어 영타", "일반어 자모분리", "일반어 특수문자", "일반어 띄어쓰기",
}


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Balance blocked and passed rows to 50:50 within each suite.")
  parser.add_argument("--input_path", type=str, default="./data/train.jsonl", help="Path of the dataset to balance.")
  parser.add_argument("--output_path", type=str, default="./data/train.jsonl", help="Path to write the balanced dataset.")
  parser.add_argument("--backup_path", type=str, default="./data/train.unbalanced.jsonl", help="Where to keep the original when overwriting the input.")
  parser.add_argument("--seed", type=int, default=42, help="Random seed.")
  return parser.parse_args()


def load_jsonl(path: str) -> list[dict]:
  with open(path, "r", encoding="utf-8") as f:
    return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: str, rows: list[dict]):
  os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
  with open(path, "w", encoding="utf-8") as f:
    for row in rows:
      f.write(json.dumps(row, ensure_ascii=False) + "\n")


def kind(row: dict) -> str:
  attack_type = row["source"].get("attack_type")
  return attack_type if attack_type in VARIATIONS else "원본"


def sample_stratified(rows: list[dict], count: int, rng: random.Random) -> list[dict]:
  """원본·문장 삽입·판정 조작·표기 변형의 비율을 유지하면서 count개를 고른다."""
  groups: dict[str, list[dict]] = {}
  for row in rows:
    groups.setdefault(kind(row), []).append(row)
  quotas = {name: len(group) * count // len(rows) for name, group in groups.items()}
  # 반올림으로 모자란 몫은 가장 큰 그룹부터 하나씩 채운다
  for name in sorted(groups, key=lambda name: -len(groups[name]))[:count - sum(quotas.values())]:
    quotas[name] += 1
  chosen = []
  for name, group in groups.items():
    chosen += rng.sample(group, quotas[name])
  return chosen


def main():
  args = parse_args()
  rng = random.Random(args.seed)
  rows = load_jsonl(args.input_path)

  # 출처(suite)마다 따로 맞춰서 agora와 cleanbot의 비중은 그대로 둔다
  kept_ids = set()
  for suite in dict.fromkeys(row["suite"] for row in rows):
    blocked = [row for row in rows if row["suite"] == suite and row["label"]]
    passed = [row for row in rows if row["suite"] == suite and not row["label"]]
    count = min(len(blocked), len(passed))
    larger, smaller = (blocked, passed) if len(blocked) > len(passed) else (passed, blocked)
    kept_ids.update(row["id"] for row in smaller + sample_stratified(larger, count, rng))
    print(f"{suite}: blocked {len(blocked)} / passed {len(passed)} -> {count} / {count}")

  balanced = [row for row in rows if row["id"] in kept_ids]
  if os.path.abspath(args.input_path) == os.path.abspath(args.output_path) and args.backup_path:
    write_jsonl(args.backup_path, rows)
    print(f"original kept at {args.backup_path}")
  write_jsonl(args.output_path, balanced)
  print(f"{len(rows)} rows -> {len(balanced)} rows ({args.output_path})")


if __name__ == "__main__":
  main()
