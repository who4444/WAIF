
import asyncio
from datetime import datetime
from memory.graph import get_graphiti, store_episode


# ─── Entity types ─────────────────────────────────────────────────────────────

ENTITY_EXTRACT_SYSTEM = """Extract entities and relationships from the conversation.
Return JSON only:
{
  "entities": [
    {"name": "...", "type": "person|app|project|topic|file", "description": "..."}
  ],
  "relationships": [
    {"from": "...", "to": "...", "relation": "..."}
  ]
}
If nothing worth extracting, return {"entities": [], "relationships": []}"""


async def extract_entities(text: str) -> dict:
    from core.llm_client import llm_complete
    import json

    messages = [{ "role": "user", "content": text }]
    raw = await llm_complete(
        messages=messages,
        system=ENTITY_EXTRACT_SYSTEM,
        mode="reasoning",
        max_tokens=256,
    )

    try:
        return json.loads(raw)
    except Exception:
        return { "entities": [], "relationships": [] }


# ─── Store conversation as episode ────────────────────────────────────────────

async def map_conversation(user_text: str, assistant_text: str):
    content = f"User: {user_text}\Leiwen: {assistant_text}"
    await store_episode(content, source="conversation")

    # extract entities in background
    asyncio.create_task(_extract_and_store(content))


async def _extract_and_store(content: str):
    try:
        extracted = await extract_entities(content)
        entities = extracted.get("entities", [])
        for entity in entities:
            fact = f"{entity['name']} is a {entity['type']}: {entity['description']}"
            await store_episode(fact, source="entity_extraction")
            print(f"[cartographer] entity: {fact[:60]}")
    except Exception as e:
        print(f"[cartographer] extraction error: {e}")


# ─── Query the graph ──────────────────────────────────────────────────────────

async def recall_context(query: str) -> str:
    from memory.graph import search_graph
    return await search_graph(query)


async def recall_week() -> str:
    return await recall_context("what happened this week")


async def recall_project(project_name: str) -> str:
    return await recall_context(f"project {project_name}")


async def recall_person(name: str) -> str:
    return await recall_context(f"person {name}")