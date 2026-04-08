import asyncio
from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from datetime import datetime
from config import OPENROUTER_API_KEY, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# ─── Client ───────────────────────────────────────────────────────────────────

_graphiti = None

async def get_graphiti() -> Graphiti:
    global _graphiti
    if _graphiti is None:
        _graphiti = Graphiti(
            NEO4J_URI,
            NEO4J_USER,
            NEO4J_PASSWORD,
        )
        await _graphiti.build_indices_and_constraints()
        print("[graph] graphiti connected")
    return _graphiti


# ─── Store episode ────────────────────────────────────────────────────────────

async def store_episode(content: str, source: str = "conversation"):
    try:
        g = await get_graphiti()
        await g.add_episode(
            name=f"{source}_{datetime.now().isoformat()}",
            episode_body=content,
            source=EpisodeType.message,
            source_description=source,
            reference_time=datetime.now(),
        )
        print(f"[graph] episode stored: {content[:50]}")
    except Exception as e:
        print(f"[graph] store error: {e}")


# ─── Search ───────────────────────────────────────────────────────────────────

async def search_graph(query: str, limit: int = 5) -> str:
    try:
        g = await get_graphiti()
        results = await g.search(query, num_results=limit)
        if not results:
            return ""
        lines = []
        for r in results:
            if hasattr(r, "fact"):
                lines.append(r.fact)
            elif hasattr(r, "name"):
                lines.append(r.name)
        return "\n".join(lines)
    except Exception as e:
        print(f"[graph] search error: {e}")
        return ""