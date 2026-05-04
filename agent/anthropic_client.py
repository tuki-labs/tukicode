import anthropic
from typing import Generator, List, Union
import json

class AnthropicError(Exception):
    pass

class AnthropicClient:
    def __init__(self, model_name: str, temperature: float, max_tokens: int, stream: bool, api_key: str):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream = stream
        self.api_key = api_key
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else None

    @property
    def supports_tool_calling(self) -> bool:
        return False # We'll start with text-based ReAct for Phase 1

    def _convert_messages(self, messages: List[dict]):
        anthropic_messages = []
        system_instruction = ""
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"] or ""
            
            if role == "system":
                system_instruction += content + "\n"
            elif role == "user":
                anthropic_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                anthropic_messages.append({"role": "assistant", "content": content})
        
        return system_instruction.strip(), anthropic_messages

    def chat(self, messages: List[dict], tools: List[dict] = None) -> dict:
        if not self._client:
            raise AnthropicError("Anthropic API Key is missing.")
            
        system, anthropic_msgs = self._convert_messages(messages)
        
        try:
            response = self._client.messages.create(
                model=self.model_name,
                system=system,
                messages=anthropic_msgs,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            self._update_usage(response.usage.input_tokens, response.usage.output_tokens)
            
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": response.content[0].text
                    }
                }]
            }
        except Exception as e:
            raise AnthropicError(f"Error in Anthropic chat: {str(e)}")

    def chat_stream(self, messages: List[dict], tools: List[dict] = None) -> Generator[Union[str, dict], None, None]:
        if not self._client:
            raise AnthropicError("Anthropic API Key is missing.")

        system, anthropic_msgs = self._convert_messages(messages)
        
        try:
            with self._client.messages.stream(
                model=self.model_name,
                system=system,
                messages=anthropic_msgs,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            ) as stream:
                for text in stream.text_stream:
                    yield text
                
                # Usage is available after stream ends
                final_msg = stream.get_final_message()
                self._update_usage(final_msg.usage.input_tokens, final_msg.usage.output_tokens)
        except Exception as e:
            raise AnthropicError(f"Error in Anthropic stream: {str(e)}")

    def _update_usage(self, prompt: int, completion: int):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = prompt + completion

    def is_available(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> List[str]:
        return [self.model_name, "claude-3-5-sonnet-20240620", "claude-3-opus-20240229"]
