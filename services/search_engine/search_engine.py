

import requests

from services.string_handlers.string_handler import KEYWORDS, SERPAPI_API_KEY


def _build_search_query() -> str:
    """
    Build a Google‑friendly search query from your profile & keywords.
    This tells the AI search engine exactly what you're looking for.
    """
    # Use the most important technologies as required terms
    # must_include = ' AND '.join(f'"{kw}"' for kw in ['.net', 'c#', 'react'])
    optional_include = ' OR '.join(KEYWORDS)  # just in case

    return optional_include
    # return f'({must_include}) ({optional_include}) (engineer OR developer)'

def _fetch_jobs_from_serpapi():
    """
    Use SerpAPI's google_jobs engine to get structured job listings.
    (SerpAPI uses machine learning to extract the fields.)
    """
    if not SERPAPI_API_KEY:
        print("WARNING: SERPAPI_API_KEY not set. Returning empty job list.")
        return []

    query = _build_search_query()
    print(f"Searching for jobs with query: {query}")

    params = {
        "engine": "google_jobs",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "hl": "en",
        "google_domain": "google.co.ke",
        "location": "Kenya"
    }

    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"SerpAPI request failed: {e}")
        return []

    jobs = []
    for result in data.get("jobs_results", []):
        title = result.get("title", "")
        company = result.get("company_name", "")
        location = result.get("location", "")
        
        source_title = result.get("via")
        source_link = result.get("source_link") or result.get("share_link", "")

        apply_options = []
        for url_option in result.get("apply_options") or {}.values():
            apply_options.append({
                "title": url_option.get("title"),
                "url": url_option.get("link")
            })

        # Attempt to grab a raw posting date
        posted_raw = None
        detected = result.get("detected_extensions", {})
        for key in ("posted", "date", "schedule", "posted_at", "posted_date", "posted_at"):
            if key in detected:
                posted_raw = detected[key]
                break
        if not posted_raw:
            posted_raw = result.get("posted") or result.get("date")
        
        description_parts = []

        for det in result.get("detected_extensions", {}).values():
            if isinstance(det, str):
                description_parts.append(det)
        description = " ".join(description_parts) if description_parts else ""

        jobs.append({
            "title": title,
            "company": company,
            "location": location,
            "description": description,
            "apply_options": apply_options,
            "posted_raw": posted_raw,
            "source_link": [{
                "title": source_title,
                "url": source_link
            }]

        })

    print(f"Found {len(jobs)} jobs via SerpAPI.")
    return jobs

def fetch_jobs():
    """Main entry point – returns a list of job dicts."""
    return _fetch_jobs_from_serpapi()