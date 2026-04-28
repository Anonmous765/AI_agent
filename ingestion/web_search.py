import os
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

_tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

def web_search(query: str, topic: str = "news", time_range: str = "week") -> dict:
    """
    Search the live web for current events, breaking news, and real-time information.

    Use this tool when the user asks about topics that may not be covered by the
    local knowledge base, or when data may be outdated. Especially useful for
    recent Kentucky weather events, emergency incidents, or local news.

    Args:
        query: The search query string. Be specific and include 'Kentucky' when relevant.
        topic: Search category — "news" for headlines, "general" for broad web search,
               "finance" for financial data. Defaults to "news".
        time_range: How far back to search — "day", "week", "month", or "year".
                    Defaults to "week" for recency.

    Returns:
        A dict with:
        - "answer": AI-generated summary of the top results.
        - "results": list of dicts, each with title, url, and content snippet.
    """

    print("[TOOL CALLED] web search")
    response = _tavily.search(
        query=query,
        search_depth="basic",
        topic=topic,
        time_range=time_range,
        max_results=5,
        include_answer=True,
        include_usage=True,
    )

    results = [
        {"title": r["title"], "url": r["url"], "content": r["content"]}
        for r in response.get("results", [])
    ]

    print(f"answer: {response.get('answer', '')}")
    print(f"results: {results}")
    return {
        "answer": response.get("answer", ""),
        "results": results,
    }
