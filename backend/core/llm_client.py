import anthropic
import openai
from config import ANTHROPIC_API_KEY, DEEPSEEK_API_KEY
from typing import AsyncGenerator

# ─── Clients ──────────────────────────────────────────────────────────────────

claude_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

deepseek_client = openai.AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
)


# ─── Claude — persona / speech ────────────────────────────────────────────────

async def claude_complete(
    messages: list[dict],
    system: str = "",
    max_tokens: int = 512,
) -> str:
    try:
        response = await claude_client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return response.content[0].text
    except Exception as e:
        print(f"[claude] error: {e}")
        return "sorry, something went wrong~"


async def claude_stream(
    messages: list[dict],
    system: str = "",
    max_tokens: int = 512,
) -> AsyncGenerator[str, None]:
    try:
        async with claude_client.messages.stream(
            model="claude-sonnet-4-5",
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except Exception as e:
        print(f"[claude stream] error: {e}")
        yield "sorry, something went wrong~"


# ─── DeepSeek — reasoning / code ─────────────────────────────────────────────

async def deepseek_complete(
    messages: list[dict],
    system: str = "",
    max_tokens: int = 2048,
) -> str:
    try:
        full_messages = []
        if system:
            full_messages.append({ "role": "system", "content": system })
        full_messages.extend(messages)

        response = await deepseek_client.chat.completions.create(
            model="deepseek-reasoner",
            max_tokens=max_tokens,
            messages=full_messages,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[deepseek] error: {e}")
        # fallback to claude
        print("[deepseek] falling back to claude")
        return await claude_complete(messages, system, max_tokens)


async def deepseek_stream(
    messages: list[dict],
    system: str = "",
    max_tokens: int = 2048,
) -> AsyncGenerator[str, None]:
    try:
        full_messages = []
        if system:
            full_messages.append({ "role": "system", "content": system })
        full_messages.extend(messages)

        stream = await deepseek_client.chat.completions.create(
            model="deepseek-reasoner",
            max_tokens=max_tokens,
            messages=full_messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception as e:
        print(f"[deepseek stream] error: {e}")
        async for text in claude_stream(messages, system, max_tokens):
            yield text


# ─── Router ───────────────────────────────────────────────────────────────────

async def llm_complete(
    messages: list[dict],
    system: str = "",
    mode: str = "persona",  # persona | reasoning
    max_tokens: int = 512,
) -> str:
    if mode == "reasoning":
        return await deepseek_complete(messages, system, max_tokens)
    else:
        return await claude_complete(messages, system, max_tokens)


async def llm_stream(
    messages: list[dict],
    system: str = "",
    mode: str = "persona",
    max_tokens: int = 512,
) -> AsyncGenerator[str, None]:
    if mode == "reasoning":
        async for chunk in deepseek_stream(messages, system, max_tokens):
            yield chunk
    else:
        async for chunk in claude_stream(messages, system, max_tokens):
            yield chunk