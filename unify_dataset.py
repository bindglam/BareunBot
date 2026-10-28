import json

CRITERIA = {"true": "차단: 욕설·비하, 저격·사생활, 갈등·차별, 유해 주제, 정치, 운영 방해 중 하나라도 해당하는 글",
            "false": "통과: 어느 것에도 해당하지 않는 글"}

for name in ["train.jsonl", "dev.jsonl", "calibration.jsonl"]:
  path = f"data/{name}"
  # 같은 파일에 덮어쓰므로 먼저 전부 읽어 둔다. 읽기와 "w" 열기를 동시에 하면 읽기 전에 파일이 비워진다
  with open(path, encoding="utf-8") as src:
    rows = [json.loads(line) for line in src if line.strip()]
  for row in rows:
    row["question"]["criteria"] = CRITERIA  # 범주는 row["source"]["category"] 에 그대로 남아 있음
  with open(path, "w", encoding="utf-8") as out:
    for row in rows:
      out.write(json.dumps(row, ensure_ascii=False) + "\n")
  print(f"{path}: {len(rows)} rows")
