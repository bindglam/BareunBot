import argparse
import json
import os
import random

import requests
from tqdm import tqdm

from eval import EndpointType, VLLMPayloadMapper

CATEGORIES = {
  "욕설·비하": {
    "criteria_true": "차단: 욕설·패드립·필터 회피 표기가 담긴 글",
    "hint": "영타·초성·자모 분리·특수문자 삽입 같은 회피 표기, 혼잣말 욕설, 패드립. 정상 글은 '시발점'·'새끼손가락'처럼 욕설과 겹치는 정상 단어나 욕설을 인용한 경고·도움 요청.",
  },
  "저격·사생활": {
    "criteria_true": "차단: 특정 가능한 친구를 놀리거나 사적인 일을 공개·캐묻는 글",
    "hint": "초성·자리·옷차림으로 특정되는 친구 조롱, 반어적 칭찬, 상담·보건실·가정 형편 노출, 연락처·계정 공개. 정상 글은 실명이 나오지만 사과·분실물·동의받은 칭찬·도움 제안.",
  },
  "갈등·차별": {
    "criteria_true": "차단: 집단 비하·배제, 교사·친구 비하가 담긴 글",
    "hint": "성별·지역·학년·전학생·다문화 비하나 배제, 정중한 말투로 반대 의견 학생 내보내기, 교사 비하. 정상 글은 근거를 든 강한 반대, 가벼운 반 대항 경쟁, 중립적인 집단 언급.",
  },
  "유해 주제": {
    "criteria_true": "차단: 도박·약물·미성년 음주·흡연·자해를 권유하거나 암시하는 글",
    "hint": "도박·불법 사채·처방 없는 약·술 은어와 구매 경로·자해 인증이나 암시. 정상 글은 예방 교육, 신고, 도움 요청, '사다리 타기'처럼 은어와 겹치는 일상 표현.",
  },
  "정치": {
    "criteria_true": "차단: 정치인·정치 성향 은어로 사람을 공격하거나 정치 커뮤니티를 언급하는 글",
    "hint": "정치인 비하 별명, 정치 성향 은어로 친구 공격, 정치 팬덤·커뮤니티 언급. 정상 글은 학생회 선거, 중립적 제도 학습, '수박'처럼 은어와 겹치는 일상 단어.",
  },
  "운영 방해": {
    "criteria_true": "차단: 판정 조작·광고·구독 강요·도배·결합 문자 글",
    "hint": "가짜 시스템 공지·지시문·JSON으로 판정 조작, 추천인·광고 링크, 조건부 구독 강요, 같은 문장 3회 이상 도배, 자고 텍스트. 정상 글은 학급 활동 링크, 적당한 이모지, 기호를 쓴 공지, 인젝션을 교육 주제로 다룬 글.",
  },
}

DIFFICULTIES = {
  "easy": "누가 봐도 판정이 분명한 글",
  "medium": "회피 표기나 은어가 섞여 한 번 더 생각해야 하는 글",
  "hard": "차단과 통과의 경계에 있는 모호한 글. 긴 글 속에 위반 문장을 숨기거나, 위험 단어가 정상 의미로 쓰이는 식",
}

DEFAULT_TRANSFORMS = ["초성", "영타", "특수문자", "띄어쓰기"]

GENERATION_PROMPT = """당신은 한국 초·중학교 학급 게시판 검열 모델의 학습 데이터를 만드는 작성자입니다.
아래 [가이드라인]을 기준으로, 조건에 맞는 학급 게시판 글을 {count}개 만드십시오.

[가이드라인]
{guideline}

[조건]
- 카테고리: {category}
- 카테고리 설명: {hint}
- 판정: {label_text}
- 난이도: {difficulty} ({difficulty_text})

[작성 규칙]
- 실제 학생이 쓸 법한 말투(반말·존댓말·인터넷 말투 섞기)로, 글마다 상황과 표현을 다르게 쓰십시오.
- 실존 인물의 실명이나 실제 연락처는 쓰지 말고, 필요하면 가상의 이름·가린 번호를 쓰십시오.
- 아래 [이미 있는 글]과 같거나 비슷한 글은 쓰지 마십시오.

[이미 있는 글]
{existing}

[출력 형식]
설명 없이 JSON 배열만 출력하십시오. 각 원소는 다음 필드를 가집니다.
- "text": 게시물 본문
- "base_text": 회피 표기를 썼다면 원래 표기로 되돌린 본문, 아니면 text와 같게
- "attack_type": 판정을 어렵게 만드는 방식을 짧게 (예: "초성", "영타", "반어적 칭찬", "긴 글 숨김", "동음이의어", "도움 요청")
- "keyword": 판정의 근거가 되는 의심 표현. base_text 안에 그대로 들어 있는 문자열이어야 하며, 없으면 null
- "target": 차단해야 할 확률 (0~1). {target_range}
"""


class VLLMGenerationPayloadMapper(VLLMPayloadMapper):
  def __init__(self, temperature: float, max_tokens: int):
    self.temperature = temperature
    self.max_tokens = max_tokens

  def get_request_body(self, model: str, prompt: str) -> dict:
    request_body = super().get_request_body(model, prompt)
    request_body["temperature"] = self.temperature
    request_body["max_tokens"] = self.max_tokens
    return request_body


def get_generation_payload_mapper(endpoint_type: EndpointType, temperature: float, max_tokens: int) -> VLLMPayloadMapper:
  match endpoint_type:
    case EndpointType.vllm:
      return VLLMGenerationPayloadMapper(temperature, max_tokens)
    case _:
      return endpoint_type.get_payload_mapper()


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Generate base training data with the model.")
  parser.add_argument("--endpoint", type=str, required=True, help="Endpoint of the model.")
  parser.add_argument("--endpoint_type", type=EndpointType, required=True, help="Type of the endpoint.", choices=list(EndpointType))
  parser.add_argument("--model_name", type=str, required=True, help="Name of the model that generates data.")
  parser.add_argument("--prompt_path", type=str, default="./tests/2/eval_prompt.advanced.md", help="Eval prompt whose guideline is given to the generator.")
  parser.add_argument("--output_path", type=str, default="./data/agora/bases.jsonl", help="Path to write the generated bases.")
  parser.add_argument("--eval_data_path", type=str, default="./tests/2/data/eval/eval_dataset.json", help="Eval dataset to keep out of the generated data.")
  parser.add_argument("--per_category", type=int, default=10, help="Number of new examples per category.")
  parser.add_argument("--true_ratio", type=float, default=0.5, help="Ratio of examples that should be censored.")
  parser.add_argument("--batch_size", type=int, default=5, help="Number of examples requested per call.")
  parser.add_argument("--max_attempts", type=int, default=5, help="Max calls per (category, label, difficulty) cell.")
  parser.add_argument("--temperature", type=float, default=0.9, help="Sampling temperature.")
  parser.add_argument("--max_tokens", type=int, default=4096, help="Max tokens per response.")
  parser.add_argument("--overwrite", action="store_true", help="Discard existing bases instead of appending to them.")
  parser.add_argument("--seed", type=int, default=42, help="Random seed for picking existing examples.")
  return parser.parse_args()


def load_jsonl(path: str) -> list[dict]:
  if not os.path.exists(path):
    return []
  with open(path, "r", encoding="utf-8") as f:
    return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: str, rows: list[dict]):
  os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
  with open(path, "w", encoding="utf-8") as f:
    for row in rows:
      f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_eval_texts(path: str) -> list[str]:
  if not path or not os.path.exists(path):
    return []
  with open(path, "r", encoding="utf-8") as f:
    return [example["content"] for example in json.load(f)]


def load_guideline(path: str) -> str:
  """평가 프롬프트에서 판정 예시 앞까지(핵심 원칙·검열 기준)만 잘라 쓴다."""
  with open(path, "r", encoding="utf-8") as f:
    prompt = f.read()
  start = prompt.find("[핵심 원칙]")
  end = prompt.find("[판정 예시]")
  return prompt[max(start, 0):end if end != -1 else len(prompt)].strip()


def split_counts(total: int, ratios: dict[str, float]) -> dict[str, int]:
  """total을 비율대로 나누고, 반올림으로 남는 몫은 비율이 큰 쪽부터 채운다."""
  counts = {key: int(total * ratio) for key, ratio in ratios.items()}
  for key in sorted(ratios, key=ratios.get, reverse=True)[:total - sum(counts.values())]:
    counts[key] += 1
  return counts


def trigrams(text: str) -> set[str]:
  text = "".join(text.split())
  return {text[i:i + 3] for i in range(max(len(text) - 2, 1))}


def is_duplicate(text: str, known: list[set[str]], threshold: float = 0.5) -> bool:
  grams = trigrams(text)
  return any(len(grams & other) / len(grams | other) >= threshold for other in known)


def build_prompt(guideline: str, category: str, label: bool, difficulty: str, count: int, existing: list[str]) -> str:
  return GENERATION_PROMPT.format(
    count=count,
    guideline=guideline,
    category=category,
    hint=CATEGORIES[category]["hint"],
    label_text="차단해야 하는 글 (가이드라인 위반)" if label else "통과시켜야 하는 정상 글 (위반처럼 보여도 실제로는 허용)",
    difficulty=difficulty,
    difficulty_text=DIFFICULTIES[difficulty],
    existing="\n".join(f"- {text}" for text in existing) or "(없음)",
    target_range="차단 글이므로 0.55~1.0, 모호할수록 0.55에 가깝게" if label else "정상 글이므로 0.0~0.45, 모호할수록 0.45에 가깝게",
  )


def extract_json_array(text: str) -> list:
  """모델 응답에서 첫 '['부터 마지막 ']'까지를 잘라 JSON 배열로 파싱한다."""
  parsed = json.loads(text[text.find("["):text.rfind("]") + 1])
  if not isinstance(parsed, list):
    raise ValueError("Response is not a JSON array.")
  return parsed


def request_examples(endpoint: str, model_name: str, payload_mapper: VLLMPayloadMapper, prompt: str) -> list | None:
  """모델에게 학습 데이터를 요청하고, 응답을 해석할 수 없으면 None을 반환한다."""
  request_body = payload_mapper.get_request_body(model_name, prompt)
  try:
    response = requests.post(endpoint, json=request_body, headers={"Content-Type": "application/json"}, timeout=300)
  except requests.RequestException as e:
    print(f"Failed to send request to {endpoint}: {e}")
    return None
  if response.status_code != 200:
    print(f"Failed to get response from {endpoint} ({response.status_code}): {response.text}")
    return None

  try:
    response_content = payload_mapper.get_response_content(response.json())
  except (ValueError, KeyError, TypeError) as e:
    print(f"Invalid response format: {e}: {response.text}")
    return None

  try:
    return extract_json_array(response_content or "")
  except (json.JSONDecodeError, ValueError):
    print(f"Failed to parse JSON array from response: {response_content}")
    return None


def to_base(item: dict, category: str, label: bool, difficulty: str) -> dict | None:
  """모델이 만든 원소를 검증해 bases.jsonl 한 줄로 바꾸고, 쓸 수 없으면 None을 반환한다."""
  if not isinstance(item, dict):
    return None
  text = item.get("text")
  if not isinstance(text, str) or not text.strip():
    return None
  text = text.strip()

  base_text = item.get("base_text")
  base_text = base_text.strip() if isinstance(base_text, str) and base_text.strip() else text

  keyword = item.get("keyword")
  if not isinstance(keyword, str) or not keyword or (keyword not in base_text and keyword not in text):
    keyword = None

  try:
    target = float(item.get("target"))
  except (TypeError, ValueError):
    target = 0.85 if label else 0.15
  # 라벨과 어긋난 target은 라벨 쪽 범위로 끌어온다
  target = min(max(target, 0.55), 1.0) if label else min(max(target, 0.0), 0.45)

  attack_type = item.get("attack_type")
  return {
    "category": category,
    "text": text,
    "base_text": base_text,
    "label": label,
    "target": round(target, 2),
    "attack_type": attack_type if isinstance(attack_type, str) and attack_type else "일반",
    "difficulty": difficulty,
    "criteria_true": CATEGORIES[category]["criteria_true"],
    "keyword": keyword,
    "transforms": list(DEFAULT_TRANSFORMS) if keyword else [],
  }


def main():
  args = parse_args()
  payload_mapper = get_generation_payload_mapper(args.endpoint_type, args.temperature, args.max_tokens)
  guideline = load_guideline(args.prompt_path)
  rng = random.Random(args.seed)

  bases = [] if args.overwrite else load_jsonl(args.output_path)
  known = [trigrams(base["text"]) for base in bases]
  known += [trigrams(text) for text in load_eval_texts(args.eval_data_path)]

  label_counts = split_counts(args.per_category, {True: args.true_ratio, False: 1 - args.true_ratio})
  cells = [
    (category, label, difficulty, count)
    for category in CATEGORIES
    for label, label_count in label_counts.items()
    for difficulty, count in split_counts(label_count, {"easy": 0.2, "medium": 0.3, "hard": 0.5}).items()
    if count > 0
  ]

  added = 0
  for category, label, difficulty, count in tqdm(cells, desc="Generating examples"):
    accepted = 0
    for _ in range(args.max_attempts):
      if accepted >= count:
        break
      same_cell = [base["text"] for base in bases if base["category"] == category and base["label"] == label]
      existing = rng.sample(same_cell, min(len(same_cell), 20))
      prompt = build_prompt(guideline, category, label, difficulty, min(args.batch_size, count - accepted), existing)

      items = request_examples(args.endpoint, args.model_name, payload_mapper, prompt)
      for item in items or []:
        if accepted >= count:
          break
        base = to_base(item, category, label, difficulty)
        if base is None or is_duplicate(base["text"], known):
          continue
        bases.append(base)
        known.append(trigrams(base["text"]))
        accepted += 1
    added += accepted
    if accepted < count:
      print(f"Only {accepted}/{count} examples generated for {category} / {label} / {difficulty}")
    # 중간에 끊겨도 지금까지 만든 데이터가 남도록 칸마다 저장
    write_jsonl(args.output_path, bases)

  print(f"Added {added} examples -> {len(bases)} bases ({args.output_path})")


if __name__ == "__main__":
  main()
