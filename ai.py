from abc import ABC, abstractmethod

class RequestPayload(ABC):
  def __init__(self, model: str, prompt: str):
    self.model = model
    self.prompt = prompt

  @abstractmethod
  def to_dict(self) -> dict:
    pass

class ResponsePayload(ABC):
  def __init__(self, raw_data: dict):
    self.raw_data = raw_data

class AIClient[T_request: RequestPayload, T_response: ResponsePayload](ABC):
  def __init__(self, endpoint: str, api_key: str | None = None):
    self.endpoint = endpoint
    self.api_key = api_key

  @abstractmethod
  def call(self, request_payload: T_request) -> tuple[bool, T_response | str]:
    pass
