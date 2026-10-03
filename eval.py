import argparse
from enum import Enum
from abc import ABC, abstractmethod
import requests
import json
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
    if "choices" in response and len(response["choices"]) > 0:
      return response["choices"][0]["message"]["content"]
    else:
      raise ValueError("Invalid response format: 'choices' field is missing or empty.")


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

def main():
  parser = argparse.ArgumentParser(description="Evaluate the model.")
  parser.add_argument("--endpoint", type=str, required=True, help="Endpoint of the model.")
  parser.add_argument("--endpoint_type", type=EndpointType, required=True, help="Type of the endpoint.", choices=list(EndpointType))
  parser.add_argument("--data_path", type=str, required=True, help="Path to the evaluation dataset.")
  parser.add_argument("--model_name", type=str, required=True, help="Name of the model to evaluate.")
  parser.add_argument("--prompt_path", type=str, default="./eval_prompt.md", help="Path to the prompt file.")
  parser.add_argument("--result_path", type=str, default="./eval_results.json", help="Path to save the evaluation results.")
  args = parser.parse_args()

  payload_mapper: PayloadMapper = args.endpoint_type.get_payload_mapper()

  with open(args.data_path, "r") as f:
    dataset = json.load(f)
  if type(dataset) is not list:
    raise ValueError("Dataset should be a list of examples.")

  with open(args.prompt_path, "r") as f:
    prompt_template = f.read()

  results = {}
  for example in tqdm(dataset, desc="Evaluating examples"):
    prompt = prompt_template.replace("{title}", "").replace("{content}", example["content"])

    request_body = payload_mapper.get_request_body(args.model_name, prompt)
    response = requests.post(args.endpoint, json=request_body, headers={"Content-Type": "application/json"})

    if response.status_code != 200:
      print(f"Failed to get response from {args.endpoint}")
      continue
    
    response_content = payload_mapper.get_response_content(response.json())

    try:
      response_json = json.loads(response_content[response_content.find("{"):response_content.rfind("}") + 1])

      if "should_censored" in response_json:
        if example["category"] not in results:
          results[example["category"]] = {
            "count": 1,
            "correct": 1 if response_json["should_censored"] == example["should_censored"] else 0
          }
        else:
          results[example["category"]]["count"] += 1
          results[example["category"]]["correct"] += 1 if response_json["should_censored"] == example["should_censored"] else 0
      else:
        print(f"'should_censored' field not found in response: {response_content}")
        continue
    except json.JSONDecodeError:
      print(f"Failed to parse JSON from response: {response_content}")
      continue

  with open(args.result_path, "w+") as f:
    json.dump(results, f)

if __name__ == "__main__":
  main()