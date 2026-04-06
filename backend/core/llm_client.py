from openai import OpenAI
import openai
from config import OPENROUTER_API_KEY, DEEPSEEK_API_KEY
from typing import AsyncGenerator

# ─── Clients ──────────────────────────────────────────────────────────────────


client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key= OPENROUTER_API_KEY,
)
deepseek_client = openai.AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1",
)


# ─── Qwen — persona / speech ────────────────────────────────────────────────

async def qwen_complete(
    messages: list[dict],
    system: str = "",
    max_tokens: int = 512,
) -> str:
    try:
        response = await client.chat.create(
            model="qwen/qwen-3.6-plus",
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[qwen] error: {e}")
        return "sorry, something went wrong~"


async def qwen_stream(
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
            model="qwen/qwen-3.6-plus",
            max_tokens=max_tokens,
            messages=full_messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception as e:
        print(f"[qwen stream] error: {e}")
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
        # fallback to qwen
        print("[deepseek] falling back to qwen")
        return await qwen_complete(messages, system, max_tokens)


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
        async for text in qwen_stream(messages, system, max_tokens):
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
        return await qwen_complete(messages, system, max_tokens)


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
        async for chunk in qwen_stream(messages, system, max_tokens):
            yield chunk