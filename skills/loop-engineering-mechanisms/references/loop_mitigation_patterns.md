# Loop Engineering & Self-Correction Patterns

This guide defines the advanced design patterns for implementing self-correction retry loops, validation schemas, oscillation detectors, and human escalation gates.

---

## 1. Pydantic-Based Input/Output Validation

Always decouple validation rules from the LLM's prompt. Use Python Pydantic validation schemas to verify data formats, ranges, and types.

### Code Pattern (Structured Validator):
```python
from pydantic import BaseModel, Field, field_validator

class CodeRefactoringTask(BaseModel):
    file_path: str = Field(description="The path to the target source file.")
    refactored_code: str = Field(description="The refactored Python source code.")
    complexity_score: int = Field(description="Complexity score from 1 (simple) to 10 (complex).")

    @field_validator("refactored_code")
    @classmethod
    def check_syntax(cls, code: str) -> str:
        # 1. Syntax compiler check
        try:
            compile(code, "<string>", "exec")
        except SyntaxError as e:
            raise ValueError(f"Python syntax compilation failed: {e.msg} at line {e.lineno}")
        
        # 2. Check for unsafe calls
        if "eval(" in code or "exec(" in code:
            raise ValueError("Execution of 'eval' or 'exec' is strictly prohibited.")
            
        return code
```

---

## 2. Machine-Readable Observation Injection

When validation fails, inject the error message back into the model's message history as an `Observation` formatted for machine readability.

### Code Pattern (Error Formatting & Feedback):
```python
def run_validation_cycle(model_output: str, history: list) -> tuple[bool, list]:
    try:
        # Attempt to parse and validate
        validated_task = CodeRefactoringTask.model_validate_json(model_output)
        return True, history
    except Exception as e:
        # Create a structured error response
        error_report = {
            "status": "VALIDATION_FAILED",
            "errors": [str(err) for err in getattr(e, "errors", lambda: [str(e)])()],
            "instruction": "Please correct the syntax or formatting errors listed above. Maintain your JSON structure."
        }
        
        # Append as a clean system/observation message
        history.append({
            "role": "system",
            "content": f"CRITICAL VALIDATION ERROR:\n{json.dumps(error_report, indent=2)}"
        })
        return False, history
```

---

## 3. Oscillation Detection

Oscillations occur when an agent alternates between the same set of failing outputs or duplicates errors. Use historical signature tracking to detect this.

### Code Pattern (Oscillation Tracker):
```python
class LoopMonitor:
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.error_signatures = []

    def check_oscillation(self, current_error: str) -> bool:
        # Simplify error string to create a signature
        signature = "".join(filter(str.isalnum, current_error.lower()))
        
        if signature in self.error_signatures:
            # The agent is repeating a previous error!
            return True
            
        self.error_signatures.append(signature)
        return False
```

---

## 4. Human Escalation Gate

If retries are exhausted or an oscillation is detected, freeze execution state and transfer control to a human developer.

### Code Pattern (Escalation Handoff):
```python
def execute_loop(task_input: str, max_iterations: int = 3):
    monitor = LoopMonitor(max_retries=max_iterations)
    history = [{"role": "user", "content": task_input}]
    
    for i in range(max_iterations):
        output = call_llm(history)
        success, history = run_validation_cycle(output, history)
        
        if success:
            return "SUCCESS", output
            
        # Check for oscillation
        last_error = history[-1]["content"]
        if monitor.check_oscillation(last_error):
            return trigger_human_escalation("Oscillation detected in code generation loop.", history)
            
    # Retries exhausted
    return trigger_human_escalation("Maximum validation retries reached without success.", history)

def trigger_human_escalation(reason: str, history: list):
    # Log, notify, and raise exception to pause the orchestration framework
    print(f"[ESCALATION TRIGGERED] {reason}")
    # Export state history to a local JSON manifest for human review
    with open("escalation_state.json", "w") as f:
        json.dump(history, f, indent=2)
    raise RuntimeError(f"Workflow paused. Human review required: {reason}")
```
