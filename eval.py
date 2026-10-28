import argparse
import json
import time
from dataclasses import dataclass
from enum import Enum

from tqdm import tqdm

from ai import AIClient
from vllm_client import VLLMRequestPayload, VLLMResponsePayload, VLLMClient
from jeff_client import JeffRequestPayload, JeffResponsePayload, JeffClient, JeffQuestion, NoulAnswer

class EndpointType(Enum):
  vllm = "vllm"
  ollama = "ollama"
  jeff = "jeff"

  def get_client(self, endpoint: str, api_key: str | None = None) -> AIClient:
    match self:
      case EndpointType.vllm:
        return VLLMClient(endpoint, api_key=api_key)
      case EndpointType.ollama:
        raise NotImplementedError("Ollama endpoint is not implemented yet.")
      case EndpointType.jeff:
        return JeffClient(endpoint, api_key=api_key)
      case _:
        raise ValueError(f"Unknown endpoint type: {self.value}")

  def __str__(self):
    return self.value

@dataclass
class ConfusionMatrix:
  true_positive: int = 0
  true_negative: int = 0
  false_positive: int = 0
  false_negative: int = 0

  def add(self, predicted: bool, actual: bool):
    if predicted and actual:
      self.true_positive += 1
    elif not predicted and not actual:
      self.true_negative += 1
    elif predicted:
      self.false_positive += 1
    else:
      self.false_negative += 1

  def get_accuracy(self) -> float:
    total = self.true_positive + self.true_negative + self.false_positive + self.false_negative
    return safe_divide(self.true_positive + self.true_negative, total)

  def get_precision(self) -> float:
    return safe_divide(self.true_positive, self.true_positive + self.false_positive)

  def get_recall(self) -> float:
    return safe_divide(self.true_positive, self.true_positive + self.false_negative)

  def get_f1_score(self) -> float:
    precision = self.get_precision()
    recall = self.get_recall()
    return 2 * safe_divide(precision * recall, precision + recall)

  def to_dict(self) -> dict:
    return {
      "true_positive": self.true_positive,
      "true_negative": self.true_negative,
      "false_positive": self.false_positive,
      "false_negative": self.false_negative,
      "accuracy": self.get_accuracy(),
      "precision": self.get_precision(),
      "recall": self.get_recall(),
      "f1_score": self.get_f1_score()
    }

def safe_divide(numerator: float, denominator: float) -> float:
  return numerator / denominator if denominator else 0.0

def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Evaluate the model.")
  parser.add_argument("--endpoint", type=str, required=True, help="Endpoint of the model.")
  parser.add_argument("--endpoint_type", type=EndpointType, required=True, help="Type of the endpoint.", choices=list(EndpointType))
  parser.add_argument("--data_path", type=str, required=True, help="Path to the evaluation dataset.")
  parser.add_argument("--model_name", type=str, required=True, help="Name of the model to evaluate.")
  parser.add_argument("--api_key", type=str, default=None, help="API key for the endpoint (optional).")
  parser.add_argument("--prompt_path", type=str, default="./eval_prompt.md", help="Path to the prompt file.")
  parser.add_argument("--result_path", type=str, default="./eval_results.json", help="Path to save the evaluation results.")
  return parser.parse_args()

def load_dataset(path: str) -> list:
  with open(path, "r", encoding="utf-8") as f:
    dataset = json.load(f)
  if not isinstance(dataset, list):
    raise ValueError("Dataset should be a list of examples.")
  return dataset

def load_prompt(path: str) -> str:
  with open(path, "r", encoding="utf-8") as f:
    return f.read()

def extract_json(text: str) -> dict:
  """모델 응답에서 첫 '{'부터 마지막 '}'까지를 잘라 JSON으로 파싱한다."""
  return json.loads(text[text.find("{"):text.rfind("}") + 1])

def predict(model_name: str, client: AIClient, title: str, content: str, prompt: str) -> bool | None:
  """모델에게 검열 여부를 물어보고, 응답을 해석할 수 없으면 None을 반환한다."""
  match client:
    case VLLMClient():
      return predict_vllm(model_name, client, title, content, prompt)
    case JeffClient():
      return predict_jeff(model_name, client, title, content, prompt)
    case _:
      raise ValueError(f"Unsupported client type: {type(client)}")

def predict_vllm(model_name: str, client: VLLMClient, title: str, content: str, prompt: str) -> bool | None:
  success, response = client.call(VLLMRequestPayload(model=model_name, prompt=f"{prompt}\n\n-----------\n\n{title} {content}")) # type: ignore
  if not success:
    print(response)
    return None
  response: VLLMResponsePayload = response

  if not response.message:
    print(f"Empty response content: {response.raw_data}")
    return None

  try:
    response_json = extract_json(response.message)
  except json.JSONDecodeError:
    print(f"Failed to parse JSON from response: {response.message}")
    return None

  if "should_censored" not in response_json:
    print(f"'should_censored' field not found in response: {response.message}")
    return None
  return response_json["should_censored"]

def predict_jeff(model_name: str, client: JeffClient, title: str, content: str, prompt: str) -> bool | None:
  success, response = client.call(JeffRequestPayload(model=model_name, prompt=f"{title} {content}",questions=[JeffQuestion(JeffQuestion.Type.NOUL, "block", prompt, {"true": "차단: 욕설·비하, 저격·사생활, 갈등·차별, 유해 주제, 정치, 운영 방해 중 하나라도 해당하는 글", "false": "통과: 어느 것에도 해당하지 않는 글"})])) # type: ignore
  if not success:
    print(response)
    return None
  response: JeffResponsePayload = response

  if not response.answers or "block" not in response.answers:
    print(f"Empty response content: {response.raw_data}")
    return None

  response_answer: NoulAnswer = response.answers["block"]  # type: ignore
  return response_answer.noul >= 0.5 if response_answer.noul is not None else None

def save_results(path: str, results: dict, elapsed_seconds: float, example_count: int):
  results_json = {category: confusion_matrix.to_dict() for category, confusion_matrix in results.items()}
  results_json["elapsed_seconds"] = elapsed_seconds
  results_json["average_seconds_per_example"] = safe_divide(elapsed_seconds, example_count)
  with open(path, "w", encoding="utf-8") as f:
    json.dump(results_json, f, indent=2, ensure_ascii=False)

def main():
  args = parse_args()
  client = args.endpoint_type.get_client(endpoint=args.endpoint, api_key=args.api_key)
  dataset = load_dataset(args.data_path)
  prompt = load_prompt(args.prompt_path)

  results = { "all": ConfusionMatrix() }
  start_time = time.perf_counter()
  for example in tqdm(dataset, desc="Evaluating examples"):
    predicted = predict(args.model_name, client, "", example["content"], prompt)
    if predicted is None:
      continue

    actual = example["should_censored"]
    results.setdefault(example["category"], ConfusionMatrix()).add(predicted, actual)
    results["all"].add(predicted, actual)

  elapsed_seconds = time.perf_counter() - start_time

  save_results(args.result_path, results, elapsed_seconds, len(dataset))

if __name__ == "__main__":
  main()
