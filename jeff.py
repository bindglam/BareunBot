from abc import ABC, abstractmethod
from enum import Enum
import requests

from ai import RequestPayload, ResponsePayload, AIClient

class JeffQuestion:
  class Type(Enum):
    NOUL = "noul"
    CHOICE = "choice"

    def __str__(self):
      return self.value

  def __init__(self, type: Type, name: str, instructions: str, criteria: dict[str, str]):
    self.type = type
    self.name = name
    self.instructions = instructions
    self.criteria = criteria

  def to_dict(self) -> dict:
    return {
      "type": str(self.type),
      "instructions": self.instructions,
      "criteria": self.criteria
    }

class JeffAnswer(ABC):
  def __init__(self, question: JeffQuestion, raw_data: dict):
    self.question = question
    self.raw_data = raw_data

    self.type = question.type

class NoulAnswer(JeffAnswer):
  def __init__(self, question: JeffQuestion, raw_data: dict):
    super().__init__(question, raw_data)
    self.noul: float | None = raw_data.get("noul")

class JeffRequestPayload(RequestPayload):
  def __init__(self, model: str, prompt: str, questions: list[JeffQuestion]):
    super().__init__(model, prompt)
    self.questions = questions

  def to_dict(self) -> dict:
    return {
      "model": self.model,
      "state": self.prompt,
      "questions": {question.name: question.to_dict() for question in self.questions}
    }

class JeffResponsePayload(ResponsePayload):
  def __init__(self, raw_data: dict, request_payload: JeffRequestPayload):
    super().__init__(raw_data)
    self.model: str | None = raw_data.get("model")

    self.answers: dict[str, JeffAnswer] = {}
    for question in request_payload.questions:
      if question.name not in raw_data.get("answers", {}):
        raise ValueError(f"Answer for question '{question.name}' is missing in the response.")

      match(question.type):
        case JeffQuestion.Type.NOUL:
          self.answers[question.name] = NoulAnswer(question, raw_data["answers"][question.name])
        case _:
          raise NotImplementedError(f"Answer type '{question.type}' is not implemented yet.")

class JeffClient(AIClient[JeffRequestPayload, JeffResponsePayload]):
  def call(self, request_payload: JeffRequestPayload) -> tuple[bool, JeffResponsePayload | str]:
    request_body = request_payload.to_dict()
    try:
      response = requests.post(self.endpoint, json=request_body, headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})}, timeout=300)
    except requests.RequestException as e:
      return False, str(f"Failed to send request to {self.endpoint}: {e}")
    if response.status_code != 200:
      return False, str(f"Failed to get response from {self.endpoint} ({response.status_code}): {response.text}")

    try:
      response_payload = JeffResponsePayload(response.json(), request_payload)
    except (ValueError, KeyError, TypeError, AttributeError) as e:
      return False, f"Invalid response format: {e}: {response.text}"
  
    return True, response_payload
