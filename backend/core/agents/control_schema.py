from typing import Any, Literal, TypedDict

class AgentTask(TypedDict, total=False):
    id: str
    agent: Literal["engineer", "scholar", "assistant"]
    objective: str
    input: str
    success_criteria: str
    depends_on: list[str]
    priority: Literal["low", "medium", "high"]

class AgentResult(TypedDict, total=False):
    task_id: str
    agent: Literal["engineer", "scholar", "assistant"]
    status: Literal["success", "failure", "partial"]
    summary: str
    evidence: list[str]
    artifacts: list[str, Any]
    uncertainties: list[str]
    next_steps: list[str]

class VerificationResult(TypedDict):
    status: Literal["pass", "revise", "fail"]
    issues: list[str]
    missing_requirements: list[str]
    confidence: float
    final_response_guide: str

class PlanState(TypedDict):
    goal_id: str
    goal: str
    status: Literal["active", "completed", "blocked"]
    milestones: list[dict[str, Any]]
    current_step: str
    completed_steps: list[str]
    open_questions: list[str]
    context: dict[str, Any]