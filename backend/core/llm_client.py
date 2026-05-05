import openai
from config import OPENROUTER_API_KEY, OPENROUTER_LLM_MODEL,DEEPSEEK_API_KEY
from typing import AsyncGenerator

# ─── Clients ──────────────────────────────────────────────────────────────────


client = openai.AsyncOpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key= OPENROUTER_API_KEY,
)
deepseek_client = openai.AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
)


# ─── OpenRouter — persona / speech ────────────────────────────────────────────────

async def openrouter_complete(
    messages: list[dict],
    system: str = "",
    max_tokens: int = 512,
) -> str:
    try:
        full_messages = []
        if system:
            full_messages.append({ "role": "system", "content": system })
        full_messages.extend(messages)

        response = await client.chat.completions.create(
            model=OPENROUTER_LLM_MODEL,
            max_tokens=max_tokens,
            messages=full_messages,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[openrouter] error: {e}")
        return "sorry, something went wrong~"


async def openrouter_stream(
    messages: list[dict],
    system: str = "",
    max_tokens: int = 512,
) -> AsyncGenerator[str, None]:
    try:
        full_messages = []
        if system:
            full_messages.append({ "role": "system", "content": system })
        full_messages.extend(messages)

        stream = await client.chat.completions.create(
            model=OPENROUTER_LLM_MODEL,
            max_tokens=max_tokens,
            messages=full_messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception as e:
        print(f"[openrouter stream] error: {e}")
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
        # fallback to openrouter
        print("[deepseek] falling back to openrouter")
        return await openrouter_complete(messages, system, max_tokens)


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
        async for text in openrouter_stream(messages, system, max_tokens):
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
        return await openrouter_complete(messages, system, max_tokens)


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
        async for chunk in openrouter_stream(messages, system, max_tokens):
            yield chunk