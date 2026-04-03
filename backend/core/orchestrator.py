from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage
import asyncio
from core.llm_client import llm_complete, llm_stream
from scholar import scholar_respond
from assistant import executive_respond



# ─── State ────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str          # scholar | engineer | executive | persona
    context: dict        # screen context, active app, etc.
    speech_text: str     # what chibi will say
    audio_url: str       # TTS output
    done: bool


# ─── Intent classifier ────────────────────────────────────────────────────────

def classify_intent(state: AgentState) -> AgentState:
    last = state["messages"][-1].content.lower()

    if any(w in last for w in [
        "search", "find", "research", "paper", "arxiv",
        "what is", "explain", "summarize", "look up"
    ]):
        intent = "scholar"
    elif any(w in last for w in [
        "run", "execute", "code", "debug", "fix", "git",
        "terminal", "install", "build", "error", "script"
    ]):
        intent = "engineer"
    elif any(w in last for w in [
        "email", "calendar", "meeting", "schedule", "slack",
        "message", "mail", "remind", "event", "task"
    ]):
        intent = "executive"
    else:
        intent = "persona"

    print(f"[orchestrator] intent: {intent}")
    return { **state, "intent": intent }


def route_intent(state: AgentState) -> str:
    return state["intent"]


# ─── Pipeline nodes ───────────────────────────────────────────────────────────

async def scholar_node(state: AgentState) -> AgentState:
    last = state["messages"][-1].content
    response = await scholar_respond(last)
    return { **state, "speech_text": response, "done": True }

# async def engineer_node(state: AgentState) -> AgentState:
#     print("[engineer] handling engineering task")
#     # placeholder — full implementation in Phase 9
#     return {
#         **state,
#         "speech_text": "on it! let me check that~",
#         "done": True
#     }


async def scholar_node(state: AgentState) -> AgentState:
    last = state["messages"][-1].content
    response = await scholar_respond(last)
    return { **state, "speech_text": response, "done": True }


from core.persona import persona_stream, persona_respond

async def persona_node(state: AgentState) -> AgentState:
    print("[persona] handling conversation")
    last = state["messages"][-1].content
    context = state.get("context", {})

    response = await persona_respond(last, context)

    return {
        **state,
        "speech_text": response,
        "done": True,
    }

# ─── Build graph ──────────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(AgentState)

    # nodes
    graph.add_node("classify", classify_intent)
    graph.add_node("scholar", scholar_node)
    graph.add_node("engineer", engineer_node)
    graph.add_node("executive", executive_node)
    graph.add_node("persona", persona_node)

    # entry
    graph.set_entry_point("classify")

    # routing
    graph.add_conditional_edges(
        "classify",
        route_intent,
        {
            "scholar":   "scholar",
            "engineer":  "engineer",
            "executive": "executive",
            "persona":   "persona",
        }
    )

    # all pipelines end
    graph.add_edge("scholar",   END)
    graph.add_edge("engineer",  END)
    graph.add_edge("executive", END)
    graph.add_edge("persona",   END)

    return graph.compile()


orchestrator = build_graph()


# ─── Public interface ─────────────────────────────────────────────────────────

async def handle_message(text: str, context: dict = {}) -> dict:
    state = await orchestrator.ainvoke({
        "messages": [HumanMessage(content=text)],
        "intent": "",
        "context": context,
        "speech_text": "",
        "audio_url": "",
        "done": False,
    })
    return {
        "speech_text": state["speech_text"],
        "audio_url":   state["audio_url"],
        "intent":      state["intent"],
    }