from pydantic import BaseModel, Field
from datetime import datetime


# --- Nested schemas ---

class IngredientCreate(BaseModel):
    name: str
    quantity: float | None = None
    unit: str | None = None
    group_label: str | None = None
    is_optional: bool = False
    sort_order: int = 0


class IngredientResponse(IngredientCreate):
    id: str
    model_config = {"from_attributes": True}


class StepCreate(BaseModel):
    step_number: int
    instruction: str
    timer_seconds: int | None = None
    section_label: str | None = None


class StepResponse(StepCreate):
    id: str
    model_config = {"from_attributes": True}


class EquipmentCreate(BaseModel):
    name: str
    is_essential: bool = True


class EquipmentResponse(EquipmentCreate):
    id: str
    model_config = {"from_attributes": True}


class NutritionCreate(BaseModel):
    calories: int | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    sugar_g: float | None = None
    source: str = "manual"  # manual | ai_estimated | fetched
    confidence: str = "estimated"  # verified | estimated


class NutritionResponse(NutritionCreate):
    model_config = {"from_attributes": True}


class PairingCreate(BaseModel):
    suggestion: str
    notes: str | None = None


class PairingResponse(PairingCreate):
    model_config = {"from_attributes": True}


# --- Recipe schemas ---

class RecipeCreate(BaseModel):
    title: str
    description: str | None = None
    cover_image_url: str | None = None
    source_type: str = "manual"  # photo | manual | instagram | url
    source_url: str | None = None
    source_attribution: str | None = None
    cuisine: str | None = None
    tags: list[str] | None = None
    difficulty: str | None = None
    prep_time: int | None = None
    cook_time: int | None = None
    total_time: int | None = None
    base_servings: int = 4
    ingredients: list[IngredientCreate] = []
    steps: list[StepCreate] = []
    equipment: list[EquipmentCreate] = []
    nutrition: NutritionCreate | None = None
    pairing: PairingCreate | None = None


class RecipeUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    cover_image_url: str | None = None
    cuisine: str | None = None
    tags: list[str] | None = None
    difficulty: str | None = None
    prep_time: int | None = None
    cook_time: int | None = None
    total_time: int | None = None
    base_servings: int | None = None
    notes: str | None = None
    ingredients: list[IngredientCreate] | None = None
    steps: list[StepCreate] | None = None
    equipment: list[EquipmentCreate] | None = None
    nutrition: NutritionCreate | None = None
    pairing: PairingCreate | None = None


class CookSummary(BaseModel):
    times_cooked: int
    avg_rating: float | None
    last_cooked_at: datetime | None


class RecipeListItem(BaseModel):
    id: str
    title: str
    cover_image_url: str | None
    cuisine: str | None
    difficulty: str | None
    total_time: int | None
    tags: list[str] | None
    avg_rating: float | None = None
    times_cooked: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class RecipeResponse(BaseModel):
    id: str
    title: str
    description: str | None
    cover_image_url: str | None
    source_type: str
    source_url: str | None
    source_attribution: str | None
    cuisine: str | None
    tags: list[str] | None
    difficulty: str | None
    prep_time: int | None
    cook_time: int | None
    total_time: int | None
    base_servings: int
    notes: str | None
    ingredients: list[IngredientResponse]
    steps: list[StepResponse]
    equipment: list[EquipmentResponse]
    nutrition: NutritionResponse | None
    pairing: PairingResponse | None
    cook_summary: CookSummary | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecipeListResponse(BaseModel):
    recipes: list[RecipeListItem]
    next_cursor: str | None
    has_more: bool
    total_count: int


class NoteCreate(BaseModel):
    text: str


# --- Extraction schemas ---

class ExtractionMetadata(BaseModel):
    ocr_confidence: str | None = None  # high | medium | low
    raw_ocr_text: str | None = None
    cache_hit: bool | None = None
    extraction_method: str | None = None  # json_ld | llm_fallback
    processing_time_ms: int | None = None


class DraftRecipe(BaseModel):
    """Returned by extraction endpoints. Same shape as RecipeCreate plus metadata."""
    title: str | None = None
    description: str | None = None
    cuisine: str | None = None
    difficulty: str | None = None
    prep_time: int | None = None
    cook_time: int | None = None
    total_time: int | None = None
    base_servings: int | None = None
    ingredients: list[IngredientCreate] = []
    steps: list[StepCreate] = []
    equipment: list[EquipmentCreate] = []
    nutrition: NutritionCreate | None = None
    pairing: PairingCreate | None = None
    tags: list[str] | None = None
    source_type: str
    source_url: str | None = None
    source_attribution: str | None = None
    source_image_url: str | None = None
    extraction_metadata: ExtractionMetadata


class URLExtractionRequest(BaseModel):
    url: str


class CaptionExtractionRequest(BaseModel):
    caption_text: str
    source_url: str | None = None
