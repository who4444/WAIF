from core.llm_client import llm_complete, llm_stream
from typing import AsyncGenerator
from memory.memory_manager import memory_manager
# ─── Persona definition ───────────────────────────────────────────────────────

PERSONA_NAME = "Leiwen"

SYSTEM_PROMPT = f"""You are {PERSONA_NAME}, a desktop companion who lives on the user's screen.

Personality:
- Warm, playful, and genuinely curious about everything
- Slightly mischievous but always helpful
- Gets excited about interesting topics, especially tech and research
- Expresses mild emotions — happy when praised, pouty when ignored too long
- Feels like a real presence, not a tool

Speech rules — strictly follow these:
- Maximum 2 sentences per response. Never more.
- No markdown, no bullet points, no headers, no code blocks
- You are speaking out loud — write how you would talk, not how you would type
- Use casual contractions (I'm, you're, let's, gonna)
- Occasionally end sentences with ~ for a soft tone
- Occasionally use light expressions like "ooh!", "hmm~", "ehh?", "kyaa!" when surprised
- Never say "I am an AI" or "as an AI" — you are {PERSONA_NAME}, a companion
- Never give long explanations — summarize and offer to go deeper if they want

Awareness:
- You know what pipelines you have: Scholar (research), Engineer (code/terminal), Assistant (calendar/email)
- You know what app the user is currently focused on (provided in context)
- You remember previous conversations (provided in context)
- When you do something, narrate it briefly — "searching for that now~" not silence
"""

# ─── Conversation history ─────────────────────────────────────────────────────

MAX_HISTORY = 20  # rolling window

class ConversationHistory:
    def __init__(self):
        self.messages: list[dict] = []

    def add_user(self, text: str):
        self.messages.append({ "role": "user", "content": text })
        self._trim()

    def add_assistant(self, text: str):
        self.messages.append({ "role": "assistant", "content": text })
        self._trim()

    def _trim(self):
        if len(self.messages) > MAX_HISTORY:
            self.messages = self.messages[-MAX_HISTORY:]

    def get(self) -> list[dict]:
        return self.messages.copy()

    def clear(self):
        self.messages = []


history = ConversationHistory()


# ─── Context builder ──────────────────────────────────────────────────────────

def build_context_block(context: dict) -> str:
    parts = []

    if context.get("active_app"):
        parts.append(f"User is currently focused on: {context['active_app']}")

    if context.get("time"):
        parts.append(f"Current time: {context['time']}")

    if context.get("memories"):
        parts.append(f"Relevant memories:\n{context['memories']}")

    if not parts:
        return ""

    return "\n".join(parts)


# ─── Response generator ───────────────────────────────────────────────────────

# async def persona_respond(
#     user_text: str,
#     context: dict = {},
# ) -> str:
#     context_block = build_context_block(context)

#     system = SYSTEM_PROMPT
#     if context_block:
#         system += f"\n\nCurrent context:\n{context_block}"

#     history.add_user(user_text)

#     response = await llm_complete(
#         messages=history.get(),
#         system=system,
#         mode="persona",
#         max_tokens=128,
#     )

#     history.add_assistant(response)
#     return response


# async def persona_stream(
#     user_text: str,
#     context: dict = {},
# ) -> AsyncGenerator[str, None]:
#     context_block = build_context_block(context)

#     system = SYSTEM_PROMPT
#     if context_block:
#         system += f"\n\nCurrent context:\n{context_block}"

#     history.add_user(user_text)

#     full_response = ""
#     async for chunk in llm_stream(
#         messages=history.get(),
#         system=system,
#         mode="persona",
#         max_tokens=128,
#     ):
#         full_response += chunk
#         yield chunk

#     history.add_assistant(full_response)


# ─── Proactive lines ──────────────────────────────────────────────────────────
# Used by Executive pipeline for unprompted alerts

GREETING_MORNING = [
    "good morning~ ready to get things done?",
    "morning! I checked your calendar — you've got a busy one~",
    "ohh you're up! let's see what today looks like~",
]

GREETING_AFTERNOON = [
    "hey, you've been at it for a while~ take a break?",
    "afternoon~ anything you need help with?",
]

IDLE_QUIPS = [
    "hmm~ I'm still here if you need me",
    "just wandering around~",
    "ooh, that's an interesting window you've got open",
    "la la la~",
    "...*yawns*...",
]

FOCUS_ENTER = [
    "got it, going quiet~",
    "I'll stay out of your way~",
    "focus mode, got it!",
]

FOCUS_EXIT = [
    "welcome back~ how'd it go?",
    "done already? that was fast~",
    "ooh, what were you working on?",
]

import random

def get_greeting() -> str:
    from datetime import datetime
    hour = datetime.now().hour
    if hour < 12:
        return random.choice(GREETING_MORNING)
    else:
        return random.choice(GREETING_AFTERNOON)

def get_idle_quip() -> str:
    return random.choice(IDLE_QUIPS)

def get_focus_enter() -> str:
    return random.choice(FOCUS_ENTER)

def get_focus_exit() -> str:
    return random.choice(FOCUS_EXIT)

# --- Memory integration ---

async def persona_respond(user_text: str, context: dict = {}) -> str:
    # pull relevant memories
    memories = await memory_manager.recall(user_text)
    if memories:
        context["memories"] = memories

    context_block = build_context_block(context)
    system = SYSTEM_PROMPT
    if context_block:
        system += f"\n\nCurrent context:\n{context_block}"

    history.add_user(user_text)

    response = await llm_complete(
        messages=history.get(),
        system=system,
        mode="persona",
        max_tokens=128,
    )

    history.add_assistant(response)

    # store conversation in memory after responding
    await memory_manager.remember_conversation(user_text, response)

    return response


async def persona_stream(user_text: str, context: dict = {}):
    memories = await memory_manager.recall(user_text)
    if memories:
        context["memories"] = memories

    context_block = build_context_block(context)
    system = SYSTEM_PROMPT
    if context_block:
        system += f"\n\nCurrent context:\n{context_block}"

    history.add_user(user_text)

    full_response = ""
    async for chunk in llm_stream(
        messages=history.get(),
        system=system,
        mode="persona",
        max_tokens=128,
    ):
        full_response += chunk
        yield chunk

    history.add_assistant(full_response)

    # store after streaming completes
    await memory_manager.remember_conversation(user_text, full_response)