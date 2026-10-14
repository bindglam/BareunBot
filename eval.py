import argparse
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import requests
from tqdm import tqdm

class PayloadMapper(ABC):
  @abstractmethod
  def get_request_body(self, model: str, prompt: str) -> dict:
    pass

  @abstractmethod
  def get_response_content(self, response: dict) -> str:
    pass

class VLLMPayloadMapper(PayloadMapper):
  def get_request_body(self, model: str, prompt: str) -> dict:
    return {
      "model": model,
      "messages": [
        {
          "role": "user",
          "content": prompt
        }
      ],
      "max_tokens": 1024,
      "stream": False,
      "chat_template_kwargs": {
        "enable_thinking": False
      }
    }

  def get_response_content(self, response: dict) -> str:
    choices = response.get("choices")
    if not choices:
      raise ValueError("Invalid response format: 'choices' field is missing or empty.")
    return choices[0]["message"]["content"]

class EndpointType(Enum):
  vllm = "vllm"
  ollama = "ollama"

  def get_payload_mapper(self) -> PayloadMapper:
    match self:
      case EndpointType.vllm:
        return VLLMPayloadMapper()
      case EndpointType.ollama:
        raise NotImplementedError("Ollama endpoint is not implemented yet.")
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

  def to_dict(self) -> dict:
    return {
      "true_positive": self.true_positive,
      "true_negative": self.true_negative,
      "false_positive": self.false_positive,
      "false_negative": self.false_negative,
      "accuracy": self.get_accuracy(),
      "precision": self.get_precision(),
      "recall": self.get_recall()
    }

def safe_divide(numerator: int, denominator: int) -> float:
  return numerator / denominator if denominator else 0.0

def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Evaluate the model.")
  parser.add_argument("--endpoint", type=str, required=True, help="Endpoint of the model.")
  parser.add_argument("--endpoint_type", type=EndpointType, required=True, help="Type of the endpoint.", choices=list(EndpointType))
  parser.add_argument("--data_path", type=str, required=True, help="Path to the evaluation dataset.")
  parser.add_argument("--model_name", type=str, required=True, help="Name of the model to evaluate.")
  parser.add_argument("--prompt_path", type=str, default="./eval_prompt.md", help="Path to the prompt file.")
  parser.add_argument("--result_path", type=str, default="./eval_results.json", help="Path to save the evaluation results.")
  return parser.parse_args()

def load_dataset(path: str) -> list:
  with open(path, "r", encoding="utf-8") as f:
    dataset = json.load(f)
  if not isinstance(dataset, list):
    raise ValueError("Dataset should be a list of examples.")
  return dataset

def load_prompt_template(path: str) -> str:
  with open(path, "r", encoding="utf-8") as f:
    return f.read()

def build_prompt(prompt_template: str, example: dict) -> str:
  return prompt_template.replace("{title}", "안녕").replace("{content}", example["content"])

def extract_json(text: str) -> dict:
  """모델 응답에서 첫 '{'부터 마지막 '}'까지를 잘라 JSON으로 파싱한다."""
  return json.loads(text[text.find("{"):text.rfind("}") + 1])

def predict(endpoint: str, model_name: str, payload_mapper: PayloadMapper, prompt: str) -> bool | None:
  """모델에게 검열 여부를 물어보고, 응답을 해석할 수 없으면 None을 반환한다."""
  request_body = payload_mapper.get_request_body(model_name, prompt)
  response = requests.post(endpoint, json=request_body, headers={"Content-Type": "application/json"})
  if response.status_code != 200:
    print(f"Failed to get response from {endpoint}")
    return None

  response_content = payload_mapper.get_response_content(response.json())
  try:
    response_json = extract_json(response_content)
  except json.JSONDecodeError:
    print(f"Failed to parse JSON from response: {response_content}")
    return None

  if "should_censored" not in response_json:
    print(f"'should_censored' field not found in response: {response_content}")
    return None
  return response_json["should_censored"]

def save_results(path: str, results: dict[str, ConfusionMatrix]):
  results_json = {category: confusion_matrix.to_dict() for category, confusion_matrix in results.items()}
  with open(path, "w", encoding="utf-8") as f:
    json.dump(results_json, f, indent=2, ensure_ascii=False)

def main():
  args = parse_args()
  payload_mapper = args.endpoint_type.get_payload_mapper()
  dataset = load_dataset(args.data_path)
  prompt_template = load_prompt_template(args.prompt_path)

  results = { "all": ConfusionMatrix() }
  for example in tqdm(dataset, desc="Evaluating examples"):
    prompt = build_prompt(prompt_template, example)
    predicted = predict(args.endpoint, args.model_name, payload_mapper, prompt)
    if predicted is None:
      continue

    actual = example["should_censored"]
    results.setdefault(example["category"], ConfusionMatrix()).add(predicted, actual)
    results["all"].add(predicted, actual)

  save_results(args.result_path, results)

if __name__ == "__main__":
  main()
