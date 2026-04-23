from memory.episodic_mem import (
    store_conversation,
    get_relevant_memories,
    store_memory,
)
from memory.graph import store_episode, search_graph
from memory.cartographer import map_conversation, recall_context


class MemoryManager:
    async def remember_conversation(self, user_text: str, assistant_text: str):
        await store_conversation(user_text, assistant_text)
        await map_conversation(user_text, assistant_text)

    async def remember_fact(self, fact: str):
        await store_memory(fact)
        await store_episode(fact, source="fact")

    async def recall(self, query: str) -> str:
        episodic = await get_relevant_memories(query)
        graph    = await recall_context(query)

        parts = []
        if episodic:
            parts.append(f"Past conversations:\n{episodic}")
        if graph:
            parts.append(f"Knowledge graph:\n{graph}")

        return "\n\n".join(parts) if parts else ""

    async def recall_week(self) -> str:
        from memory.cartographer import recall_week
        return await recall_week()


memory_manager = MemoryManager()