import google.generativeai as genai
from typing import Generator, List, Union
import json

class GeminiError(Exception):
    pass

class GeminiClient:
    def __init__(self, model_name: str, temperature: float, max_tokens: int, stream: bool, api_key: str):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream = stream
        self.api_key = api_key
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={
                    "temperature": self.temperature,
                    "max_output_tokens": self.max_tokens,
                }
            )
        else:
            self.model = None

    @property
    def supports_tool_calling(self) -> bool:
        # Gemini supports tool calling, but we need to map the format.
        # For Phase 1, we might start with simple text or implement the mapping.
        return False # Set to False for now to use text-based ReAct if mapping is complex

    def _convert_messages(self, messages: List[dict]):
        gemini_history = []
        system_instruction = ""
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"] or ""
            
            if role == "system":
                system_instruction += content + "\n"
            elif role == "user":
                gemini_history.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                gemini_history.append({"role": "model", "parts": [content]})
            elif role == "tool":
                # Handle tool results if needed
                gemini_history.append({"role": "user", "parts": [f"Tool result: {content}"]})
        
        return system_instruction.strip(), gemini_history

    def chat(self, messages: List[dict], tools: List[dict] = None) -> dict:
        if not self.model:
            raise GeminiError("Gemini API Key is missing.")
            
        system_instruction, history = self._convert_messages(messages)
        
        # We recreate the model with system instruction if present
        if system_instruction:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_instruction,
                generation_config={
                    "temperature": self.temperature,
                    "max_output_tokens": self.max_tokens,
                }
            )
        else:
            model = self.model

        try:
            # We use the last message as the prompt and the rest as history
            last_msg = history.pop()
            chat = model.start_chat(history=history)
            response = chat.send_message(last_msg["parts"][0])
            
            # Update usage
            # self.prompt_tokens = response.usage_metadata.prompt_token_count
            # self.completion_tokens = response.usage_metadata.candidates_token_count
            
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": response.text
                    }
                }]
            }
        except Exception as e:
            raise GeminiError(f"Error in Gemini chat: {str(e)}")

    def chat_stream(self, messages: List[dict], tools: List[dict] = None) -> Generator[Union[str, dict], None, None]:
        if not self.model:
            raise GeminiError("Gemini API Key is missing.")

        system_instruction, history = self._convert_messages(messages)
        
        if system_instruction:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_instruction,
                generation_config={
                    "temperature": self.temperature,
                    "max_output_tokens": self.max_tokens,
                }
            )
        else:
            model = self.model

        try:
            last_msg = history.pop()
            chat = model.start_chat(history=history)
            response_stream = chat.send_message(last_msg["parts"][0], stream=True)
            
            for chunk in response_stream:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            raise GeminiError(f"Error in Gemini stream: {str(e)}")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> List[str]:
        return [self.model_name, "gemini-1.5-flash", "gemini-1.5-pro"]
