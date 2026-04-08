from memory.episodic_mem import (
    store_conversation,
    get_relevant_memories,
    store_memory,
)
from memory.graph import store_episode, search_graph


class MemoryManager:
    async def remember_conversation(self, user_text: str, assistant_text: str):
        # store in both systems
        await store_conversation(user_text, assistant_text)
        await store_episode(
            f"User said: {user_text}\nKira replied: {assistant_text}"
        )

    async def remember_fact(self, fact: str):
        await store_memory(fact)
        await store_episode(fact, source="fact")

    async def recall(self, query: str) -> str:
        # search both and merge
        episodic = await get_relevant_memories(query)
        graph    = await search_graph(query)

        parts = []
        if episodic:
            parts.append(episodic)
        if graph:
            parts.append(graph)

        return "\n".join(parts) if parts else ""


memory_manager = MemoryManager()