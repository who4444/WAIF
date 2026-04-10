from mem0 import Memory
from config import OPENROUTER_API_KEY, QDRANT_HOST, QDRANT_PORT

# ─── Config ───────────────────────────────────────────────────────────────────

config = {
    "llm": {
        "provider": "openai",
        "config": {
            "model": "qwen3.6-plus",
            "api_key": OPENROUTER_API_KEY,
        }
    },
    "embedder": {
        "provider": "openai",
        "config": {
            "model": "bge-m3",
            "api_key": OPENROUTER_API_KEY,
        }
    },
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "host": QDRANT_HOST,
            "port": QDRANT_PORT,
        }
    },
}

memory = Memory.from_config(config)
USER_ID = "user"


# ─── Store ────────────────────────────────────────────────────────────────────

async def store_memory(text: str, metadata: dict = {}):
    try:
        memory.add(text, user_id=USER_ID, metadata=metadata)
        print(f"[memory] stored: {text[:50]}")
    except Exception as e:
        print(f"[memory] store error: {e}")


async def store_conversation(user_text: str, assistant_text: str):
    messages = [
        { "role": "user",      "content": user_text },
        { "role": "assistant", "content": assistant_text },
    ]
    try:
        memory.add(messages, user_id=USER_ID)
    except Exception as e:
        print(f"[memory] conversation store error: {e}")


# ─── Retrieve ─────────────────────────────────────────────────────────────────

async def search_memories(query: str, limit: int = 5) -> list[dict]:
    try:
        results = memory.search(query, user_id=USER_ID, limit=limit)
        return [
            {
                "text": r["memory"],
                "score": r.get("score", 0),
            }
            for r in results.get("results", [])
        ]
    except Exception as e:
        print(f"[memory] search error: {e}")
        return []


async def get_relevant_memories(query: str) -> str:
    results = await search_memories(query)
    if not results:
        return ""
    lines = [r["text"] for r in results]
    return "\n".join(lines)


# ─── All memories ─────────────────────────────────────────────────────────────

async def get_all_memories() -> list[dict]:
    try:
        results = memory.get_all(user_id=USER_ID)
        return results.get("results", [])
    except Exception as e:
        print(f"[memory] get all error: {e}")
        return []