import argparse
import json
import os
import random

SPLITS = ("train", "dev", "calibration")


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Split train.jsonl into train, dev and calibration sets.")
  parser.add_argument("--input_path", type=str, default="./data/train.jsonl", help="Path of the dataset to split.")
  parser.add_argument("--output_dir", type=str, default="./data", help="Directory to write train.jsonl, dev.jsonl and calibration.jsonl.")
  parser.add_argument("--dev_ratio", type=float, default=0.12, help="Ratio of families held out for development.")
  parser.add_argument("--calibration_ratio", type=float, default=0.03, help="Ratio of families held out for temperature calibration.")
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


def assign_splits(rows: list[dict], dev_ratio: float, calibration_ratio: float, rng: random.Random) -> dict[str, str]:
  """family마다 split을 정한다. 같은 원문의 변형이 여러 split에 섞이지 않도록 family 단위로 나누고, (suite, 카테고리, 라벨)별로 비율을 맞춘다."""
  groups: dict[tuple[str, str, bool], dict[str, None]] = {}
  for row in rows:
    key = (row["suite"], row["source"].get("category", ""), row["label"])
    groups.setdefault(key, {})[row["family"]] = None

  splits: dict[str, str] = {}
  for families in groups.values():
    families = [family for family in families if family not in splits]
    rng.shuffle(families)
    dev_count = round(len(families) * dev_ratio)
    calibration_count = round(len(families) * calibration_ratio)
    for index, family in enumerate(families):
      splits[family] = "dev" if index < dev_count else "calibration" if index < dev_count + calibration_count else "train"
  return splits


def main():
  args = parse_args()
  rng = random.Random(args.seed)
  rows = load_jsonl(args.input_path)
  splits = assign_splits(rows, args.dev_ratio, args.calibration_ratio, rng)

  outputs: dict[str, list[dict]] = {split: [] for split in SPLITS}
  counters: dict[tuple[str, str], int] = {}
  for row in rows:
    split = splits[row["family"]]
    # id는 split마다 suite별로 다시 매긴다 (agora:dev:00001, cleanbot:calibration:00001 ...)
    index = counters[(split, row["suite"])] = counters.get((split, row["suite"]), 0) + 1
    row = {**row, "id": f"{row['suite']}:{split}:{index:05d}", "source": {**row["source"], "split": split}}
    outputs[split].append(row)

  for split, split_rows in outputs.items():
    path = os.path.join(args.output_dir, f"{split}.jsonl")
    write_jsonl(path, split_rows)
    families = len({row["family"] for row in split_rows})
    blocked = sum(row["label"] for row in split_rows)
    print(f"{split}: {families} families -> {len(split_rows)} rows, blocked {blocked} ({path})")


if __name__ == "__main__":
  main()
