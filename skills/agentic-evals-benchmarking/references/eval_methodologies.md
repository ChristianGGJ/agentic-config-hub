# Agentic Evaluation & Benchmarking Methodologies

This guide defines the advanced design patterns for testing agent outputs using LLM-as-a-Judge systems and calculating Ragas/DeepEval metrics.

---

## 1. LLM-as-a-Judge Evaluation Code Pattern

Evaluating agent output (like code correctness or text tone) requires structured scoring prompts that return quantitative metrics rather than conversational explanations.

### Code Pattern (Python Judge):
```python
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

class EvaluationScore(BaseModel):
    score: float = Field(
        description="The quality score from 0.0 (poor/hallucinated) to 1.0 (excellent)."
    )
    findings: list[str] = Field(description="List of specific flaws or improvements found.")
    rationale: str = Field(description="Justification for the numerical score.")

# Use a highly capable model as the Judge
judge_llm = ChatOpenAI(model="gpt-4o").with_structured_output(EvaluationScore)

def evaluate_generation(user_query: str, agent_output: str, source_context: str) -> EvaluationScore:
    prompt = ChatPromptTemplate.from_template("""
        You are an expert quality auditor. Evaluate the agent's output against the source context.
        
        Source Context: {context}
        User Query: {query}
        Agent Output: {output}
        
        Rate the output from 0.0 to 1.0. Deduct score if the output contains facts NOT present in the source context.
    """)
    
    return judge_llm.invoke(prompt.format(
        context=source_context,
        query=user_query,
        output=agent_output
    ))
```

---

## 2. Ragas-Equivalent Metrics Implementation

To validate RAG pipelines in production CI/CD tests, implement automated faithfulness and answer relevance validation.

### Faithfulness (No Hallucinations) Pattern:
```python
class FaithfulnessAudit(BaseModel):
    claims: list[str] = Field(description="Key claims extracted from the agent's response.")
    verifications: list[bool] = Field(
        description="True if the claim is supported by the source context, False otherwise."
    )

audit_llm = ChatOpenAI(model="gpt-4o-mini").with_structured_output(FaithfulnessAudit)

def calculate_faithfulness(agent_output: str, source_context: str) -> float:
    # 1. Extract and verify claims
    prompt = ChatPromptTemplate.from_template(
        "List all factual claims made in the output, and verify if they exist in the context.\nContext: {context}\nOutput: {output}"
    )
    result: FaithfulnessAudit = audit_llm.invoke(prompt.format(context=source_context, output=agent_output))
    
    if not result.verifications:
        return 1.0
        
    # 2. Score = Verified Claims / Total Claims
    score = sum(1 for v in result.verifications if v) / len(result.verifications)
    return score
```
