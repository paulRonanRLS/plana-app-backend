"""
Extraction service for converting various inputs into structured recipe data.

Integrates with:
- Anthropic Claude API (for LLM structuring)
- Trafilatura (for web scraping)
- Google Cloud Vision API (for OCR - to be implemented)
- Redis (for URL caching - to be implemented)
"""

import json
import logging
import time
import uuid
import os
from io import BytesIO
from hashlib import sha256
from pydantic import ValidationError
import requests

logger = logging.getLogger(__name__)

from app.core.prompts import EXTRACTION_PROMPT
from app.core.claude_client import get_client
from app.core.vision_client import ocr_image
from app.core.redis_client import cache_get, cache_set
from app.core.storage import get_storage
from app.core.scraper import (
    normalise_url,
    fetch_page,
    extract_json_ld,
    format_json_ld_as_text,
    extract_page_text,
)
from app.schemas.recipe import (
    DraftRecipe,
    ExtractionMetadata,
    IngredientCreate,
    StepCreate,
    EquipmentCreate,
)


class ExtractionError(Exception):
    """Raised when recipe extraction fails."""

    pass


# Mock draft recipe used when CLAUDE_ENABLED=false
_MOCK_DRAFT = DraftRecipe(
    title="Mock Extracted Recipe",
    description="This is a placeholder recipe returned during development. Real extraction will use OCR, web scraping, and Claude.",
    cuisine="Italian",
    difficulty="medium",
    prep_time=15,
    cook_time=20,
    total_time=35,
    base_servings=4,
    ingredients=[
        IngredientCreate(name="spaghetti", quantity=400, unit="g", sort_order=0),
        IngredientCreate(name="guanciale", quantity=200, unit="g", sort_order=1),
        IngredientCreate(name="egg yolks", quantity=4, unit=None, sort_order=2),
        IngredientCreate(name="pecorino romano", quantity=100, unit="g", sort_order=3),
        IngredientCreate(name="black pepper", quantity=2, unit="tsp", sort_order=4),
    ],
    steps=[
        StepCreate(
            step_number=1,
            instruction="Bring a large pot of salted water to boil. Cook spaghetti until al dente.",
            timer_seconds=480,
            section_label="Cook",
        ),
        StepCreate(
            step_number=2,
            instruction="Meanwhile, cut guanciale into small strips and cook in a cold pan over medium heat until crispy.",
            timer_seconds=600,
            section_label="Cook",
        ),
        StepCreate(
            step_number=3,
            instruction="Whisk egg yolks with grated pecorino and plenty of black pepper.",
        ),
        StepCreate(
            step_number=4,
            instruction="Toss drained pasta with guanciale and rendered fat. Remove from heat and quickly stir in egg mixture.",
            section_label="Combine",
        ),
    ],
    equipment=[
        EquipmentCreate(name="Large pot", is_essential=True),
        EquipmentCreate(name="Large pan", is_essential=True),
    ],
    tags=["pasta", "italian", "quick"],
    source_type="manual",
    extraction_metadata=ExtractionMetadata(processing_time_ms=0),
)


def _structure_with_claude(text: str, source_type: str) -> dict:
    """
    Send text to Claude API for structuring into DraftRecipe format.

    When CLAUDE_ENABLED=false, returns mock data for testing.

    Args:
        text: Recipe text to structure
        source_type: Source type for the recipe (url, instagram, photo)

    Returns:
        Validated DraftRecipe dict

    Raises:
        ExtractionError: If Claude returns invalid JSON or validation fails
    """
    client = get_client()

    # If Claude is disabled, return mock data
    if client is None:
        return _MOCK_DRAFT.model_dump()

    # Replace {text} placeholder with actual text
    # Using replace() instead of format() to avoid treating JSON braces as placeholders
    prompt = EXTRACTION_PROMPT.replace("{text}", text)

    try:
        # Call Claude API with system message to reinforce JSON-only output
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system="You are a recipe extraction API. You must respond with valid JSON only. No explanations, no markdown, no code fences. Just the raw JSON object.",
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract the response text
        response_text = message.content[0].text

        # Log the raw response for debugging
        logger.debug(f"Raw Claude response: {response_text[:500]}...")  # First 500 chars

        # Defensive cleaning before parsing
        response_text = response_text.strip()

        # Check for empty response
        if not response_text:
            raise ExtractionError("Claude returned empty response")

        # Remove markdown code fences if present
        if response_text.startswith("```json"):
            response_text = response_text[7:]  # Remove ```json
            if response_text.endswith("```"):
                response_text = response_text[:-3]  # Remove closing ```
            response_text = response_text.strip()
        elif response_text.startswith("```"):
            response_text = response_text[3:]  # Remove ```
            if response_text.endswith("```"):
                response_text = response_text[:-3]  # Remove closing ```
            response_text = response_text.strip()

        # Parse as JSON
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON. Response was: {response_text[:1000]}")
            raise ExtractionError(f"Claude returned invalid JSON: {e}") from e

        # Validate against DraftRecipe schema
        try:
            # Add required fields that aren't part of Claude's response
            data["source_type"] = source_type
            data["extraction_metadata"] = {}

            # Validate with Pydantic
            draft = DraftRecipe(**data)
            return draft.model_dump()

        except ValidationError as e:
            raise ExtractionError(f"Claude response failed validation: {e}") from e

    except Exception as e:
        if isinstance(e, ExtractionError):
            raise
        raise ExtractionError(f"Error calling Claude API: {e}") from e


def extract_from_caption(caption_text: str, source_url: str | None = None) -> DraftRecipe:
    """
    Extract recipe from pasted Instagram caption via LLM.

    Args:
        caption_text: Raw caption text from Instagram
        source_url: Optional Instagram post URL for attribution

    Returns:
        DraftRecipe with extracted data and metadata

    Raises:
        ExtractionError: If extraction fails
    """
    start_time = time.time()

    # Validate caption is not empty
    if not caption_text.strip():
        raise ExtractionError("Caption text cannot be empty")

    # Structure with Claude
    data = _structure_with_claude(caption_text, "instagram")

    # Calculate elapsed time
    elapsed_ms = int((time.time() - start_time) * 1000)

    # Set metadata fields
    data["source_type"] = "instagram"
    data["source_url"] = source_url
    data["extraction_metadata"] = ExtractionMetadata(
        extraction_method="llm_caption",
        processing_time_ms=elapsed_ms,
    ).model_dump()

    return DraftRecipe(**data)


def extract_from_url(url: str) -> DraftRecipe:
    """
    Extract recipe from a URL via web scraping + JSON-LD parsing + LLM fallback.

    Implements Redis caching with 30-day TTL. Cache key is based on normalized URL hash.

    Args:
        url: Recipe URL to extract from

    Returns:
        DraftRecipe with extracted data and metadata

    Raises:
        ExtractionError: If extraction fails
    """
    start_time = time.time()

    # Validate URL format
    if not url.startswith(("http://", "https://")):
        raise ExtractionError("URL must start with http:// or https://")

    # Normalize URL and compute cache key
    normalized_url = normalise_url(url)
    cache_key = f"extraction:url:{sha256(normalized_url.encode()).hexdigest()}"

    # Try to get from cache
    try:
        cached_result = cache_get(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for URL: {url}")
            # Parse cached JSON back into DraftRecipe
            data = json.loads(cached_result)
            # Update metadata to reflect cache hit
            data["extraction_metadata"]["cache_hit"] = True
            data["extraction_metadata"]["processing_time_ms"] = 0
            return DraftRecipe(**data)
    except Exception as e:
        logger.warning(f"Redis cache GET failed: {e} - continuing without cache")

    # If Claude is disabled (test mode), return mock data immediately
    client = get_client()
    if client is None:
        elapsed_ms = int((time.time() - start_time) * 1000)
        draft = _MOCK_DRAFT.model_copy(
            update={
                "source_type": "url",
                "source_url": url,
                "source_attribution": "Mock Source",
                "extraction_metadata": ExtractionMetadata(
                    cache_hit=False,
                    extraction_method="llm_fallback",
                    processing_time_ms=elapsed_ms,
                ),
            }
        )
        return draft

    try:
        # Fetch page HTML
        html = fetch_page(normalized_url)
    except requests.Timeout as e:
        raise ExtractionError(f"Request timed out: {e}") from e
    except requests.RequestException as e:
        raise ExtractionError(f"Failed to fetch URL: {e}") from e

    # Try to extract JSON-LD first
    json_ld = extract_json_ld(html)
    extraction_method = None
    source_image_url = None
    source_attribution = None

    if json_ld:
        # Found JSON-LD structured data
        text = format_json_ld_as_text(json_ld)
        extraction_method = "json_ld"

        # Extract cover image from JSON-LD
        if "image" in json_ld:
            image = json_ld["image"]
            if isinstance(image, str):
                source_image_url = image
            elif isinstance(image, dict):
                source_image_url = image.get("url")
            elif isinstance(image, list) and image:
                first_image = image[0]
                if isinstance(first_image, str):
                    source_image_url = first_image
                elif isinstance(first_image, dict):
                    source_image_url = first_image.get("url")

        # Extract author from JSON-LD
        if "author" in json_ld:
            author = json_ld["author"]
            if isinstance(author, dict):
                source_attribution = author.get("name")
            elif isinstance(author, str):
                source_attribution = author
    else:
        # No JSON-LD found, extract page text
        text = extract_page_text(html)
        extraction_method = "llm_scrape"

        # Try to find og:image for cover image
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            source_image_url = og_image["content"]

        # Try to find author in meta tags
        author_meta = soup.find("meta", attrs={"name": "author"})
        if author_meta and author_meta.get("content"):
            source_attribution = author_meta["content"]

    # Structure with Claude
    data = _structure_with_claude(text, "url")

    # Calculate elapsed time
    elapsed_ms = int((time.time() - start_time) * 1000)

    # Set metadata fields
    data["source_type"] = "url"
    data["source_url"] = url  # Use original URL, not normalized
    data["source_image_url"] = source_image_url
    data["source_attribution"] = source_attribution
    data["extraction_metadata"] = ExtractionMetadata(
        extraction_method=extraction_method,
        cache_hit=False,
        processing_time_ms=elapsed_ms,
    ).model_dump()

    # Create DraftRecipe to return
    result = DraftRecipe(**data)

    # Store in cache (30-day TTL = 2592000 seconds)
    try:
        cache_set(cache_key, result.model_dump_json(), ttl_seconds=2592000)
        logger.debug(f"Cached extraction result for URL: {url}")
    except Exception as e:
        logger.warning(f"Redis cache SET failed: {e} - continuing without caching")

    return result


def extract_from_photo(image_data: bytes, filename: str) -> DraftRecipe:
    """
    Extract recipe from a photo via OCR + LLM.

    Real implementation:
    1. Validates image data and file extension
    2. Performs OCR using Google Cloud Vision
    3. Assesses OCR confidence based on text length
    4. Saves image to storage
    5. Sends OCR text to Claude for structuring
    6. Returns structured recipe with metadata

    Args:
        image_data: Raw image bytes
        filename: Original filename

    Returns:
        DraftRecipe with extracted data and metadata

    Raises:
        ExtractionError: If validation or OCR fails
    """
    start_time = time.time()

    # Validate image data
    if not image_data:
        raise ExtractionError("Image data is empty")

    # Validate file extension
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in ['.jpg', '.jpeg', '.png']:
        raise ExtractionError(f"Invalid file type: {file_ext}. Only JPG and PNG are supported.")

    # Perform OCR
    ocr_text = ocr_image(image_data)

    # Assess OCR confidence based on text length
    text_length = len(ocr_text)
    if text_length > 200:
        ocr_confidence = "high"
    elif text_length > 50:
        ocr_confidence = "medium"
    else:
        ocr_confidence = "low"

    # Save image to storage
    storage = get_storage()
    image_file = BytesIO(image_data)
    # Generate unique filename: photos/{uuid}.{ext}
    image_uuid = str(uuid.uuid4())
    storage_path = f"photos/{image_uuid}{file_ext}"
    source_image_url = storage.save(image_file, storage_path)

    # Structure with Claude
    data = _structure_with_claude(ocr_text, "photo")

    # Calculate elapsed time
    elapsed_ms = int((time.time() - start_time) * 1000)

    # Set metadata fields
    data["source_type"] = "photo"
    data["source_image_url"] = source_image_url
    data["extraction_metadata"] = ExtractionMetadata(
        ocr_confidence=ocr_confidence,
        raw_ocr_text=ocr_text,
        extraction_method="ocr",
        processing_time_ms=elapsed_ms,
    ).model_dump()

    return DraftRecipe(**data)
