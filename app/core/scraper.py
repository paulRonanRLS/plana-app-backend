"""
Web scraping utilities for recipe URL extraction.

Handles URL normalization, page fetching, JSON-LD parsing, and content extraction.
"""

import json
import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
import requests
from bs4 import BeautifulSoup
import trafilatura


# Tracking parameters to remove from URLs
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "ref",
    "source",
    "mc_cid",
    "mc_eid",
}


def normalise_url(url: str) -> str:
    """
    Normalize a URL for consistent caching and deduplication.

    - Lowercase scheme and host
    - Remove tracking parameters
    - Remove trailing slashes
    - Remove fragment (#...)
    - Standardize to https

    Args:
        url: Raw URL string

    Returns:
        Normalized URL string
    """
    # Parse the URL
    parsed = urlparse(url)

    # Lowercase scheme and netloc (host)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Standardize to https if http
    if scheme == "http":
        scheme = "https"

    # Remove tracking parameters from query string
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        # Filter out tracking parameters
        clean_params = {k: v for k, v in params.items() if k not in TRACKING_PARAMS}
        # Rebuild query string
        query = urlencode(clean_params, doseq=True) if clean_params else ""
    else:
        query = ""

    # Remove trailing slash from path
    path = parsed.path.rstrip("/") if parsed.path != "/" else "/"

    # Remove fragment
    fragment = ""

    # Reconstruct the URL
    normalized = urlunparse((scheme, netloc, path, parsed.params, query, fragment))

    return normalized


def fetch_page(url: str) -> str:
    """
    Fetch raw HTML from a URL with proper headers and timeout.

    Args:
        url: URL to fetch

    Returns:
        Raw HTML content as string

    Raises:
        requests.RequestException: On network or HTTP errors
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()

    return response.text


def extract_json_ld(html: str) -> dict | None:
    """
    Parse JSON-LD structured data from HTML and find Recipe objects.

    Looks for <script type="application/ld+json"> tags containing
    Schema.org Recipe data.

    Args:
        html: Raw HTML content

    Returns:
        Recipe dict if found, None otherwise
    """
    soup = BeautifulSoup(html, "lxml")

    # Find all JSON-LD script tags
    json_ld_scripts = soup.find_all("script", type="application/ld+json")

    for script in json_ld_scripts:
        try:
            data = json.loads(script.string)

            # Handle both single objects and arrays
            if isinstance(data, list):
                # Search through array for Recipe
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Recipe":
                        return item
            elif isinstance(data, dict):
                # Check if it's a Recipe
                if data.get("@type") == "Recipe":
                    return data
                # Check if it has a @graph with a Recipe
                if "@graph" in data and isinstance(data["@graph"], list):
                    for item in data["@graph"]:
                        if isinstance(item, dict) and item.get("@type") == "Recipe":
                            return item

        except (json.JSONDecodeError, AttributeError):
            # Skip malformed JSON-LD
            continue

    return None


def format_json_ld_as_text(json_ld: dict) -> str:
    """
    Convert a JSON-LD Recipe object into clean readable text.

    Even when we have structured JSON-LD, we send it through Claude
    to ensure consistent output schema and handle variations in
    JSON-LD formatting across sites.

    Args:
        json_ld: Recipe object from JSON-LD

    Returns:
        Formatted text representation
    """
    lines = []

    # Title
    if "name" in json_ld:
        lines.append(f"Recipe: {json_ld['name']}")
        lines.append("")

    # Description
    if "description" in json_ld:
        lines.append(f"Description: {json_ld['description']}")
        lines.append("")

    # Author
    if "author" in json_ld:
        author = json_ld["author"]
        if isinstance(author, dict):
            author_name = author.get("name", "")
        else:
            author_name = str(author)
        if author_name:
            lines.append(f"Author: {author_name}")
            lines.append("")

    # Times
    if "prepTime" in json_ld:
        lines.append(f"Prep Time: {json_ld['prepTime']}")
    if "cookTime" in json_ld:
        lines.append(f"Cook Time: {json_ld['cookTime']}")
    if "totalTime" in json_ld:
        lines.append(f"Total Time: {json_ld['totalTime']}")
    if any(k in json_ld for k in ["prepTime", "cookTime", "totalTime"]):
        lines.append("")

    # Servings
    if "recipeYield" in json_ld:
        yield_value = json_ld["recipeYield"]
        if isinstance(yield_value, list):
            yield_value = yield_value[0] if yield_value else ""
        lines.append(f"Servings: {yield_value}")
        lines.append("")

    # Ingredients
    if "recipeIngredient" in json_ld:
        lines.append("Ingredients:")
        ingredients = json_ld["recipeIngredient"]
        if isinstance(ingredients, list):
            for ing in ingredients:
                lines.append(f"- {ing}")
        lines.append("")

    # Instructions
    if "recipeInstructions" in json_ld:
        lines.append("Instructions:")
        instructions = json_ld["recipeInstructions"]

        if isinstance(instructions, str):
            lines.append(instructions)
        elif isinstance(instructions, list):
            for i, step in enumerate(instructions, 1):
                if isinstance(step, str):
                    lines.append(f"{i}. {step}")
                elif isinstance(step, dict):
                    # HowToStep format
                    text = step.get("text") or step.get("itemListElement", "")
                    if text:
                        lines.append(f"{i}. {text}")
        lines.append("")

    # Categories/Keywords
    if "recipeCategory" in json_ld:
        category = json_ld["recipeCategory"]
        if isinstance(category, list):
            category = ", ".join(category)
        lines.append(f"Category: {category}")

    if "recipeCuisine" in json_ld:
        cuisine = json_ld["recipeCuisine"]
        if isinstance(cuisine, list):
            cuisine = ", ".join(cuisine)
        lines.append(f"Cuisine: {cuisine}")

    if "keywords" in json_ld:
        keywords = json_ld["keywords"]
        if isinstance(keywords, list):
            keywords = ", ".join(keywords)
        lines.append(f"Keywords: {keywords}")

    return "\n".join(lines)


def extract_page_text(html: str) -> str:
    """
    Extract main content text from HTML using trafilatura.

    Falls back to BeautifulSoup if trafilatura fails.

    Args:
        html: Raw HTML content

    Returns:
        Extracted text content
    """
    # Try trafilatura first (best at extracting main content)
    text = trafilatura.extract(html)

    if text:
        return text

    # Fallback to BeautifulSoup
    soup = BeautifulSoup(html, "lxml")

    # Remove script, style, nav, footer tags
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    # Get text from body
    body = soup.find("body")
    if body:
        text = body.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    # Clean up excessive whitespace
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    return text
