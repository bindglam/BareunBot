import requests

from ai import RequestPayload, ResponsePayload, AIClient

class VLLMRequestPayload(RequestPayload):
  def __init__(self, model: str, prompt: str, max_tokens: int = 1024, enable_thinking: bool = False):
    super().__init__(model, prompt)
    self.max_tokens = max_tokens
    self.enable_thinking = enable_thinking

  def to_dict(self) -> dict:
    return {
      "model": self.model,
      "messages": [
        {
          "role": "user",
          "content": self.prompt
        }
      ],
      "max_tokens": self.max_tokens,
      "stream": False,
      "chat_template_kwargs": {
        "enable_thinking": self.enable_thinking
      }
    }

class VLLMResponsePayload(ResponsePayload):
  def __init__(self, raw_data: dict):
    super().__init__(raw_data)
    choices = raw_data.get("choices")
    if not choices:
      raise ValueError("'choices' field is missing or empty.")
    self.message: str | None = choices[0].get("message", {}).get("content")

class VLLMClient(AIClient[VLLMRequestPayload, VLLMResponsePayload]):
  def call(self, request_payload: VLLMRequestPayload) -> tuple[bool, VLLMResponsePayload | str]:
    request_body = request_payload.to_dict()
    try:
      response = requests.post(self.endpoint, json=request_body, headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})}, timeout=300)
    except requests.RequestException as e:
      return False, str(f"Failed to send request to {self.endpoint}: {e}")
    if response.status_code != 200:
      return False, str(f"Failed to get response from {self.endpoint} ({response.status_code}): {response.text}")

    try:
      response_payload = VLLMResponsePayload(response.json())
    except (ValueError, KeyError, TypeError, AttributeError) as e:
      return False, f"Invalid response format: {e}: {response.text}"
  
    return True, response_payload
