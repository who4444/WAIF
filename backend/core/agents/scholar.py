import arxiv
from tavily import TavilyClient
from firecrawl import FirecrawlApp
from core.llm_client import llm_complete
from config import TAVILY_API_KEY

tavily = TavilyClient(api_key=TAVILY_API_KEY)

# ─── Search ───────────────────────────────────────────────────────────────────

async def search_web(query: str) -> list[dict]:
    try:
        results = tavily.search(query=query, max_results=5)
        return [
            {
                "title": r["title"],
                "url": r["url"],
                "content": r["content"][:500],
            }
            for r in results.get("results", [])
        ]
    except Exception as e:
        print(f"[scholar] tavily error: {e}")
        return []


async def search_arxiv(query: str) -> list[dict]:
    try:
        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=5,
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )
        results = []
        for paper in client.results(search):
            results.append({
                "title": paper.title,
                "authors": [a.name for a in paper.authors[:3]],
                "summary": paper.summary[:400],
                "url": paper.entry_id,
                "published": str(paper.published.date()),
            })
        return results
    except Exception as e:
        print(f"[scholar] arxiv error: {e}")
        return []


async def fetch_page(url: str) -> str:
    try:
        app = FirecrawlApp()
        result = app.scrape_url(url, params={ "formats": ["markdown"] })
        return result.get("markdown", "")[:3000]
    except Exception as e:
        print(f"[scholar] firecrawl error: {e}")
        return ""


# ─── Synthesize ───────────────────────────────────────────────────────────────

SCHOLAR_SYSTEM = """You are a research assistant that synthesizes information clearly and concisely.

Your response must include TWO summaries with clear delineation:

1. **Written Summary**: Detailed but concise, including all key information and important details.
2. **Spoken Summary**: Maximum 3 sentences, optimized for reading aloud, no markdown or bullet points.

Format your response as:
WRITTEN:
[detailed summary here]

SPOKEN:
[3-sentence spoken summary here]"""


async def scholar_respond(query: str) -> str:
    print(f"[scholar] researching: {query}")

    is_academic = any(w in query.lower() for w in [
        "paper", "arxiv", "research", "study", "published"
    ])

    if is_academic:
        results = await search_arxiv(query)
        source_text = "\n\n".join([
            f"Title: {r['title']}\nPublished: {r['published']}\nSummary: {r['summary']}"
            for r in results
        ])
    else:
        results = await search_web(query)
        source_text = "\n\n".join([
            f"Title: {r['title']}\nContent: {r['content']}"
            for r in results
        ])

    if not source_text:
        return "hmm, I couldn't find anything on that~ try rephrasing?"

    messages = [{
        "role": "user",
        "content": f"Query: {query}\n\nSources:\n{source_text}\n\nSummarize for spoken response."
    }]

    response = await llm_complete(
        messages=messages,
        system=SCHOLAR_SYSTEM,
        mode="reasoning",
        max_tokens=512,
    )

    return response