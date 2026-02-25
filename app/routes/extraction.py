import time
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException

from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.recipe import (
    DraftRecipe, URLExtractionRequest, CaptionExtractionRequest,
    ExtractionMetadata, IngredientCreate, StepCreate, EquipmentCreate,
)

router = APIRouter(prefix="/extract", tags=["extraction"])

# Placeholder draft recipe used for all extraction stubs
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
        IngredientCreate(name="spaghetti", quantity=400, unit="g", sort_order=1),
        IngredientCreate(name="guanciale", quantity=200, unit="g", sort_order=2),
        IngredientCreate(name="egg yolks", quantity=4, unit=None, sort_order=3),
        IngredientCreate(name="pecorino romano", quantity=100, unit="g", sort_order=4),
        IngredientCreate(name="black pepper", quantity=2, unit="tsp", sort_order=5),
    ],
    steps=[
        StepCreate(step_number=1, instruction="Bring a large pot of salted water to boil. Cook spaghetti until al dente.", timer_seconds=480, section_label="Cook"),
        StepCreate(step_number=2, instruction="Meanwhile, cut guanciale into small strips and cook in a cold pan over medium heat until crispy.", timer_seconds=600, section_label="Cook"),
        StepCreate(step_number=3, instruction="Whisk egg yolks with grated pecorino and plenty of black pepper."),
        StepCreate(step_number=4, instruction="Toss drained pasta with guanciale and rendered fat. Remove from heat and quickly stir in egg mixture.", section_label="Combine"),
    ],
    equipment=[
        EquipmentCreate(name="Large pot", is_essential=True),
        EquipmentCreate(name="Large pan", is_essential=True),
    ],
    tags=["pasta", "italian", "quick"],
    source_type="manual",
    extraction_metadata=ExtractionMetadata(processing_time_ms=0),
)


@router.post("/photo", response_model=DraftRecipe)
async def extract_from_photo(
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Extract recipe from a photo via OCR + LLM.

    TODO: Implement real pipeline:
    1. Upload image to storage
    2. Send to Google Cloud Vision for OCR
    3. Send OCR text to Claude for structuring
    4. Return structured recipe with confidence metadata
    """
    start = time.time()

    # Validate file type
    if image.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=400, detail="Only JPEG and PNG images are supported")

    # Read file (to confirm it's valid)
    contents = await image.read()
    if len(contents) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="Image must be under 10MB")

    elapsed = int((time.time() - start) * 1000)

    draft = _MOCK_DRAFT.model_copy(update={
        "source_type": "photo",
        "source_image_url": f"https://placeholder.local/uploads/{image.filename}",
        "extraction_metadata": ExtractionMetadata(
            ocr_confidence="high",
            raw_ocr_text="[Mock OCR text would appear here]",
            processing_time_ms=elapsed,
        ),
    })
    return draft


@router.post("/url", response_model=DraftRecipe)
def extract_from_url(
    body: URLExtractionRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Extract recipe from a URL via web scraping + JSON-LD parsing + LLM fallback.

    TODO: Implement real pipeline:
    1. Normalize URL
    2. Check Redis cache (return immediately on hit)
    3. Scrape page with Trafilatura
    4. Parse JSON-LD for Schema.org Recipe data
    5. Fall back to Claude if no structured data found
    6. Cache result
    7. Return structured recipe
    """
    start = time.time()

    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    elapsed = int((time.time() - start) * 1000)

    draft = _MOCK_DRAFT.model_copy(update={
        "source_type": "url",
        "source_url": body.url,
        "source_attribution": "Mock Source",
        "extraction_metadata": ExtractionMetadata(
            cache_hit=False,
            extraction_method="llm_fallback",
            processing_time_ms=elapsed,
        ),
    })
    return draft


@router.post("/caption", response_model=DraftRecipe)
def extract_from_caption(
    body: CaptionExtractionRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Extract recipe from pasted Instagram caption via LLM.

    TODO: Implement real pipeline:
    1. Send caption text to Claude with extraction prompt
    2. Claude strips hashtags, emojis, commentary
    3. Returns structured recipe JSON
    """
    start = time.time()

    if not body.caption_text.strip():
        raise HTTPException(status_code=400, detail="Caption text cannot be empty")

    elapsed = int((time.time() - start) * 1000)

    draft = _MOCK_DRAFT.model_copy(update={
        "source_type": "instagram",
        "source_url": body.source_url,
        "extraction_metadata": ExtractionMetadata(
            processing_time_ms=elapsed,
        ),
    })
    return draft
