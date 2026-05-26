import json
import re
from typing import Any, TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage
from core.llm_client import llm_complete
from .scholar import scholar_respond
from .assistant import executive_respond
from .persona import persona_respond
from .engineer import engineer_respond
from .verifier import verify_result
# ─── State ────────────────────────────────────────────────────────────────────

class AgentTask(TypedDict, total=False):
    id: str
    agent: str
    objective: str
    input: str
    success_criteria: str
    depends_on: list[str]


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str          # scholar | engineer | executive | persona | multi
    context: dict        # screen context, active app, etc.
    plan: dict           # LLM-generated orchestration plan
    task_results: list[dict]
    verification: dict    # verification results for subagent outputs
    speech_text: str     # what chibi will say
    audio_url: str       # TTS output
    done: bool


# ─── Planner ──────────────────────────────────────────────────────────────────

ORCHESTRATOR_SYSTEM = """You are Leiwen's task orchestrator.
Decide whether the user needs normal companion conversation or one or more specialized subagents.

Available subagents:
- scholar: web search, arXiv, research, explanations that need external or factual synthesis.
- engineer: safe read-only shell inspection, debugging, GitHub PRs/issues, code/project questions.
- executive: calendar and Gmail summaries, scheduling, reminders, personal admin.
- persona: casual conversation, emotional support, preferences, and companion replies.

Return JSON only with this schema:
{
  "intent": "persona" | "scholar" | "engineer" | "executive" | "multi",
  "response_strategy": "direct" | "single_agent" | "multi_agent",
  "direct_response": "only for direct persona replies, otherwise empty",
  "tasks": [
    {
      "id": "t1",
      "agent": "scholar" | "engineer" | "executive",
      "objective": "specific outcome for this subagent",
      "input": "self-contained task brief",
      "success_criteria": "what a good result must include",
      "depends_on": []
    }
  ],
  "final_response_instructions": "how to combine results for a concise spoken reply"
}

Rules:
- Decompose mixed requests into ordered tasks. Use multiple tasks only when different specialties are needed.
- Do not assign casual chat to subagents; use direct persona for that.
- Keep task inputs concrete and self-contained, including relevant user context.
- Never ask engineer to write/delete/install/mutate; it can inspect and diagnose only.
- If a request is unsafe or impossible, use direct persona and explain briefly."""


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    else:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            stripped = stripped[start:end + 1]
    return json.loads(stripped)


def _fallback_plan(text: str) -> dict[str, Any]:
    lowered = text.lower()
    if any(w in lowered for w in [
        "run", "execute", "code", "debug", "fix", "git",
        "terminal", "install", "build", "error", "script"
    ]):
        agent = "engineer"
    elif any(w in lowered for w in [
        "email", "calendar", "meeting", "schedule", "slack",
        "message", "mail", "remind", "event", "task"
    ]):
        agent = "executive"
    elif any(w in lowered for w in [
        "search", "find", "research", "paper", "arxiv",
        "what is", "explain", "summarize", "look up"
    ]):
        agent = "scholar"
    else:
        return {
            "intent": "persona",
            "response_strategy": "direct",
            "direct_response": "",
            "tasks": [],
            "final_response_instructions": "Reply naturally as Leiwen.",
        }

    return {
        "intent": agent,
        "response_strategy": "single_agent",
        "direct_response": "",
        "tasks": [{
            "id": "t1",
            "agent": agent,
            "objective": "Handle the user's request.",
            "input": text,
            "success_criteria": "Answer the user concisely and accurately.",
            "depends_on": [],
        }],
        "final_response_instructions": "Return a concise spoken answer.",
    }


def _clean_plan(plan: dict[str, Any], original_text: str) -> dict[str, Any]:
    valid_agents = {"scholar", "engineer", "executive"}
    tasks = []
    for index, task in enumerate(plan.get("tasks", []), start=1):
        agent = str(task.get("agent", "")).lower()
        if agent not in valid_agents:
            continue
        tasks.append({
            "id": str(task.get("id") or f"t{index}"),
            "agent": agent,
            "objective": str(task.get("objective") or "Handle this part of the request."),
            "input": str(task.get("input") or original_text),
            "success_criteria": str(task.get("success_criteria") or "Produce a useful concise result."),
            "depends_on": task.get("depends_on") or [],
        })

    if not tasks:
        return {
            "intent": "persona",
            "response_strategy": "direct",
            "direct_response": str(plan.get("direct_response") or ""),
            "tasks": [],
            "final_response_instructions": str(plan.get("final_response_instructions") or "Reply naturally as Leiwen."),
        }

    intent = str(plan.get("intent") or tasks[0]["agent"]).lower()
    if len(tasks) > 1:
        intent = "multi"
    elif intent not in valid_agents:
        intent = tasks[0]["agent"]

    return {
        "intent": intent,
        "response_strategy": "multi_agent" if len(tasks) > 1 else "single_agent",
        "direct_response": "",
        "tasks": tasks,
        "final_response_instructions": str(plan.get("final_response_instructions") or "Return a concise spoken answer."),
    }


async def plan_tasks(state: AgentState) -> AgentState:
    text = state["messages"][-1].content
    context = state.get("context", {})

    messages = [{
        "role": "user",
        "content": (
            f"User request:\n{text}\n\n"
            f"Available context:\n{json.dumps(context, ensure_ascii=True, default=str)}"
        ),
    }]

    raw_plan = await llm_complete(
        messages=messages,
        system=ORCHESTRATOR_SYSTEM,
        mode="reasoning",
        max_tokens=768,
    )

    try:
        plan = _clean_plan(_extract_json(raw_plan), text)
    except Exception as e:
        print(f"[orchestrator] planner parse error: {e}")
        plan = _fallback_plan(text)

    print(f"[orchestrator] intent: {plan['intent']} tasks: {len(plan['tasks'])}")
    return { **state, "intent": plan["intent"], "plan": plan }


def route_intent(state: AgentState) -> str:
    if state.get("plan", {}).get("tasks"):
        return "execute"
    return "persona"


# ─── Pipeline nodes ───────────────────────────────────────────────────────────

async def _run_task(task: AgentTask, original_text: str, prior_results: list[dict]) -> dict:
    agent = task["agent"]
    if agent == "scholar":
        response = await scholar_respond(
            task["input"],
            task=task,
            original_request=original_text,
            previous_results=prior_results,
        )
        if "SPOKEN:" in response:
            response = response.split("SPOKEN:", 1)[1].strip()
    elif agent == "engineer":
        response = await engineer_respond(
            task["input"],
            task=task,
            original_request=original_text,
            previous_results=prior_results,
        )
    elif agent == "executive":
        response = await executive_respond(
            task["input"],
            task=task,
            original_request=original_text,
            previous_results=prior_results,
        )
    else:
        response = f"unsupported agent: {agent}"

    return {
        "task_id": task["id"],
        "agent": agent,
        "objective": task["objective"],
        "result": response,
    }


FINAL_SYNTHESIS_SYSTEM = """You are Leiwen, turning subagent results into the final spoken reply.
Be concise, natural, and useful. No markdown. Mention important limitations or failures.
Use the subagent outputs; do not invent facts or actions that are not in the results."""



async def synthesize_final_response(
    original_text: str,
    plan: dict,
    task_results: list[dict],
    verification: dict
) -> str:
    if len(task_results) == 1:
        return task_results[0]["result"]

    messages = [{
        "role": "user",
        "content": (
            f"Original request:\n{original_text}\n\n"
            f"Final response instructions:\n{plan.get('final_response_instructions', '')}\n\n"
            f"Subagent results:\n{json.dumps(task_results, ensure_ascii=True, default=str, indent=2)}"
            f"\n\nVerification results:\n{json.dumps(verification, ensure_ascii=True, default=str, indent=2)}"
        ),
    }]
    return await llm_complete(
        messages=messages,
        system=FINAL_SYNTHESIS_SYSTEM,
        mode="persona",
        max_tokens=256,
    )


async def execute_plan_node(state: AgentState) -> AgentState:
    original_text = state["messages"][-1].content
    plan = state.get("plan", {})
    task_results = []

    for task in plan.get("tasks", []):
        print(f"[orchestrator] running {task['agent']} task {task['id']}: {task['objective']}")
        result = await _run_task(task, original_text, task_results)
        task_results.append(result)
    verification = verify_result(original_text, plan, task_results)
    response = await synthesize_final_response(original_text, plan, task_results, verification=verification)
    return { **state, 
            "task_results": task_results, 
            "speech_text": response, 
            "verification": verification,
            "done": True }


async def persona_node(state: AgentState) -> AgentState:
    print("[persona] handling conversation")
    last = state["messages"][-1].content
    context = state.get("context", {})

    response = await persona_respond(last, context)

    return {**state, "speech_text": response, "done": True}

# ─── Build graph ──────────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(AgentState)

    # nodes
    graph.add_node("plan", plan_tasks)
    graph.add_node("execute", execute_plan_node)
    graph.add_node("persona", persona_node)

    # entry
    graph.set_entry_point("plan")

    # routing
    graph.add_conditional_edges(
        "plan",
        route_intent,
        {
            "execute": "execute",
            "persona": "persona",
        }
    )

    # all pipelines end
    graph.add_edge("execute", END)
    graph.add_edge("persona", END)

    return graph.compile()


orchestrator = build_graph()


# ─── Public interface ─────────────────────────────────────────────────────────

async def handle_message(text: str, context: dict | None = None) -> dict:
    state = await orchestrator.ainvoke({
        "messages": [HumanMessage(content=text)],
        "intent": "",
        "context": context or {},
        "plan": {},
        "task_results": [],
        "verification": {},
        "speech_text": "",
        "audio_url": "",
        "done": False,
    })
    return {
        "speech_text": state["speech_text"],
        "audio_url":   state["audio_url"],
        "intent":      state["intent"],
    }
