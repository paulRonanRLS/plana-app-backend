"""
Extraction endpoints - convert various inputs into structured recipes.

All endpoints return DraftRecipe schemas that the client can review/edit
before saving as a full recipe.
"""

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import ValidationError
import requests

from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.recipe import DraftRecipe, URLExtractionRequest, CaptionExtractionRequest
from app.services import extraction_service
from app.services.extraction_service import ExtractionError

router = APIRouter(prefix="/extract", tags=["extraction"])


@router.post("/photo", response_model=DraftRecipe)
async def extract_from_photo(
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Extract recipe from a photo via OCR + LLM.

    STUB: Returns mock data. Real implementation will:
    1. Upload image to storage
    2. Send to Google Cloud Vision for OCR
    3. Send OCR text to Claude for structuring
    4. Return structured recipe with confidence metadata
    """
    # Validate file type
    if image.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=400, detail="Only JPEG and PNG images are supported")

    # Read file contents
    contents = await image.read()

    # Validate file size
    if len(contents) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="Image must be under 10MB")

    try:
        # Extract recipe using service
        draft = extraction_service.extract_from_photo(contents, image.filename or "photo.jpg")
        return draft
    except requests.Timeout:
        raise HTTPException(
            status_code=504, detail={"code": "EXTRACTION_TIMEOUT", "message": "Extraction request timed out"}
        )
    except ExtractionError as e:
        raise HTTPException(
            status_code=500, detail={"code": "EXTRACTION_FAILED", "message": str(e)}
        )
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/url", response_model=DraftRecipe)
def extract_from_url(
    body: URLExtractionRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Extract recipe from a URL via web scraping + JSON-LD parsing + LLM fallback.

    Real implementation:
    1. Normalize URL
    2. Check Redis cache (return immediately on hit) - TODO
    3. Scrape page with Trafilatura
    4. Parse JSON-LD for Schema.org Recipe data
    5. Fall back to Claude if no structured data found
    6. Cache result - TODO
    7. Return structured recipe
    """
    # Validate URL format
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    try:
        # Extract recipe using service
        draft = extraction_service.extract_from_url(body.url)
        return draft
    except requests.Timeout:
        raise HTTPException(
            status_code=504, detail={"code": "EXTRACTION_TIMEOUT", "message": "Extraction request timed out"}
        )
    except ExtractionError as e:
        raise HTTPException(
            status_code=500, detail={"code": "EXTRACTION_FAILED", "message": str(e)}
        )
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/caption", response_model=DraftRecipe)
def extract_from_caption(
    body: CaptionExtractionRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Extract recipe from pasted Instagram caption via LLM.

    Implementation:
    1. Send caption text to Claude with extraction prompt
    2. Claude strips hashtags, emojis, commentary
    3. Returns structured recipe JSON
    """
    # Validate caption is not empty
    if not body.caption_text.strip():
        raise HTTPException(status_code=400, detail="Caption text cannot be empty")

    try:
        # Extract recipe using service
        draft = extraction_service.extract_from_caption(body.caption_text, body.source_url)
        return draft
    except requests.Timeout:
        raise HTTPException(
            status_code=504, detail={"code": "EXTRACTION_TIMEOUT", "message": "Extraction request timed out"}
        )
    except ExtractionError as e:
        raise HTTPException(
            status_code=500, detail={"code": "EXTRACTION_FAILED", "message": str(e)}
        )
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
