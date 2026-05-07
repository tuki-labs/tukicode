import json
from pathlib import Path
from typing import List, Dict, Any, Optional

class PlannerState:
    def __init__(self, workspace_dir: str = "."):
        self.state_file = Path(workspace_dir) / "planner_state.json"
        self.state: Dict[str, Any] = {
            "status": "idle", # idle, planning, pending_confirmation, building, completed
            "plan": [],       # lista de pasos: {"id": 1, "description": "...", "status": "pending|completed|failed"}
            "current_step": 0
        }

    def load(self) -> bool:
        """Loads state from planner_state.json if it exists."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Validate basic structure
                    if "status" in data and "plan" in data:
                        self.state = data
                        return True
            except Exception:
                pass
        return False

    def save(self):
        """Saves current state to planner_state.json."""
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

    def set_plan(self, plan: List[Dict[str, str]]):
        """Sets a new plan and resets progress."""
        formatted_plan = []
        for i, step in enumerate(plan):
            formatted_plan.append({
                "id": i + 1,
                "description": step.get("description", str(step)),
                "status": "pending"
            })
        
        self.state["plan"] = formatted_plan
        self.state["status"] = "pending_confirmation"
        self.state["current_step"] = 0
        self.save()

    def get_pending_steps(self) -> List[Dict[str, Any]]:
        return [step for step in self.state["plan"] if step["status"] in ["pending", "failed"]]

    def mark_step_completed(self, step_id: int):
        for step in self.state["plan"]:
            if step["id"] == step_id:
                step["status"] = "completed"
                break
        self.save()

    def mark_step_failed(self, step_id: int):
        for step in self.state["plan"]:
            if step["id"] == step_id:
                step["status"] = "failed"
                break
        self.save()

    def clear(self):
        """Clears the state and deletes the file."""
        self.state = {
            "status": "idle",
            "plan": [],
            "current_step": 0
        }
        if self.state_file.exists():
            try:
                self.state_file.unlink()
            except Exception:
                pass
