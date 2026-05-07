import json
from .parser import extract_thinking

class Planner:
    def __init__(self, llm_client, display):
        self.llm_client = llm_client
        self.display = display

    async def generate_plan(self, user_request: str, cwd_context: str) -> list:
        """
        Generates a step-by-step plan using the LLM.
        Returns a list of step dictionaries: [{"description": "..."}]
        """
        prompt = f"""You are the Planner module for TukiCode, a CLI programming agent.
Your task is to take the user's request and break it down into small, atomic, sequential steps.

USER REQUEST:
{user_request}

ENVIRONMENT CONTEXT:
Working directory info: {cwd_context}

RULES:
1. Each step must focus on ONE single file (create, modify, or delete) or ONE specific terminal command (like running npm install).
2. The code to be generated for each step should ideally be under 120 lines to avoid timeouts.
3. Steps should be sequential (e.g., install dependencies first, then create config, then create main file).
4. Do NOT output the actual code. Only output the description of what needs to be done in each step.
5. You MUST wrap your reasoning inside <thinking>...</thinking> tags first.
6. After thinking, output ONLY a valid JSON array of objects. Each object must have a "description" string key.

EXAMPLE JSON OUTPUT:
```json
[
  {{"description": "Run 'npm init -y' to initialize the project"}},
  {{"description": "Install express and cors via npm"}},
  {{"description": "Create src/index.js and set up the basic Express server with CORS"}},
  {{"description": "Create src/routes.js and add the basic API endpoints"}}
]
```
"""
        messages = [{"role": "user", "content": prompt}]
        
        # Phase 3: Structured output check
        # We pass response_format to chat(), and the clients will handle it if supported.
        
        with self.display.show_spinner("Generating implementation plan..."):
            last_error = None
            for attempt in range(3):
                try:
                    # Async call
                    response = await self.llm_client.chat(messages, response_format={"type": "json_object"})
                    
                    content = ""
                    if "choices" in response and len(response["choices"]) > 0:
                        content = response["choices"][0].get("message", {}).get("content", "")
                    elif "message" in response:
                        content = response["message"].get("content", "")
                        
                    thinking, clean_text = extract_thinking(content)
                    if thinking and attempt == 0:
                        self.display.show_thinking(thinking)
                    
                    import re
                    # Improved JSON extraction
                    json_match = re.search(r'```json\s*(.*?)\s*```', clean_text, re.DOTALL)
                    if not json_match:
                        json_match = re.search(r'```\s*(.*?)\s*```', clean_text, re.DOTALL)
                        
                    if json_match:
                        plan_json_str = json_match.group(1)
                    else:
                        # Try to find the first [ and last ]
                        start = clean_text.find("[")
                        end = clean_text.rfind("]")
                        if start != -1 and end != -1 and end > start:
                            plan_json_str = clean_text[start:end+1]
                        else:
                            plan_json_str = clean_text.strip()
                    
                    plan_json_str = plan_json_str.strip()
                    if plan_json_str.startswith("[") and not plan_json_str.endswith("]"):
                        plan_json_str += "]"
                        
                    try:
                        plan = json.loads(plan_json_str)
                    except json.JSONDecodeError as e:
                        last_error = e
                        messages.append({"role": "assistant", "content": content})
                        messages.append({"role": "user", "content": f"Your last response contained invalid JSON: {str(e)}. Please output ONLY a valid JSON array of objects without any conversational text."})
                        continue

                    if isinstance(plan, list):
                        return plan
                    else:
                        raise Exception("Plan format invalid (not a list).")
                    
                except Exception as e:
                    last_error = e
                    if "402" in str(e) or "401" in str(e) or "timeout" in str(e).lower():
                        break
                    
            raise Exception(f"Failed to generate valid plan after 3 attempts. Last error: {str(last_error)}")
