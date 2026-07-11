# Multi-LLM Routing & Token Optimization Strategies

This guide defines the advanced design patterns for routing agentic subtasks across multiple LLM tiers, optimizing prompt token budgets, and caching responses.

---

## 1. Multi-LLM Tiering Matrix

To minimize latency and API costs, classify every node or agent task into one of three tiers and bind the appropriate model.

| Tier | Characteristics | Ideal Models | Sample Tasks |
|---|---|---|---|
| **Reasoning** | Complex coding, multi-step logic, self-correction, planning | `claude-3-5-sonnet`, `o1`, `o3` | Code generation, architectural design, root-cause analysis |
| **Utility** | Classification, data extraction, JSON validation, formatting | `gpt-4o-mini`, `gemini-1.5-flash` | Text summarization, mapping tool outputs, user intent detection |
| **Edge / Local** | High-throughput, low-latency, offline data processing | `ollama/llama3`, `mistral` | Simple PII filtering, basic text categorization |

---

## 2. Dynamic Routing Router Code Pattern

Implement a dynamic routing gate that analyzes the incoming request and directs it to the appropriate model based on complexity and prompt length.

### Code Pattern (Python Dynamic Router):
```python
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

class RoutingDecision(BaseModel):
    tier: Literal["reasoning", "utility"] = Field(
        description="The LLM tier required to handle the input."
    )
    explanation: str = Field(description="Reasoning for selecting this tier.")

# 1. Initialize a cheap classifier model
classifier = ChatOpenAI(model="gpt-4o-mini").with_structured_output(RoutingDecision)

def route_task(user_prompt: str) -> str:
    # 2. Check simple rules first to save classifier costs
    if len(user_prompt) > 8000 or any(kw in user_prompt.lower() for kw in ["refactor", "architect", "bug"]):
        return "claude-3-5-sonnet"
        
    # 3. Classify dynamically
    prompt = ChatPromptTemplate.from_template(
        "Evaluate the task complexity and select the tier.\nTask: {task}"
    )
    decision = classifier.invoke(prompt.format(task=user_prompt))
    
    if decision.tier == "reasoning":
        return "claude-3-5-sonnet"
    return "gpt-4o-mini"
```

---

## 3. Token Budgeting & Context Reduction Policies

Context windows can expand rapidly in multi-agent loops. Enforce strict summarization policies to reduce token footprint.

### Context Compression Pattern:
```python
def compress_history(messages: list, token_threshold: int = 15000) -> list:
    """If history exceeds token threshold, summarize middle messages while keeping system and last user prompts intact."""
    current_estimate = sum(len(m.get("content", "")) // 4 for m in messages) # 1 token ~= 4 characters
    
    if current_estimate < token_threshold:
        return messages
        
    system_msg = messages[0]
    last_msg = messages[-1]
    middle_msgs = messages[1:-1]
    
    # Generate summary of intermediate conversation
    summary_text = call_summarization_model(middle_msgs)
    
    return [
        system_msg,
        {"role": "system", "content": f"Summary of previous actions: {summary_text}"},
        last_msg
    ]
```
