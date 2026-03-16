"""
Unit tests for extraction service.

Tests the recipe extraction logic with mocked external dependencies:
- Claude API (anthropic)
- Google Cloud Vision (OCR)
- Redis (caching)
- Storage (file uploads)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from io import BytesIO

from app.services import extraction_service
from app.services.extraction_service import ExtractionError
from app.schemas.recipe import DraftRecipe


# ─── EXTRACT FROM PHOTO TESTS ───────────────────────────────────────


def test_extract_photo_calls_ocr_and_claude():
    """Test extract_from_photo calls OCR, saves image, and structures with Claude."""
    # Mock image data
    image_data = b"fake-image-bytes"
    filename = "test_recipe.jpg"

    # Mock OCR to return text
    mock_ocr_text = "Recipe Title\n2 cups flour\n1 tsp salt\nMix and bake."

    # Mock Claude response
    mock_draft_dict = {
        "title": "Recipe Title",
        "description": "A test recipe",
        "cuisine": None,
        "difficulty": "easy",
        "prep_time": 10,
        "cook_time": 20,
        "total_time": 30,
        "base_servings": 4,
        "ingredients": [
            {"name": "flour", "quantity": 2, "unit": "cups", "sort_order": 0}
        ],
        "steps": [
            {"step_number": 1, "instruction": "Mix and bake."}
        ],
        "equipment": [],
        "tags": [],
        "source_type": "photo",
        "source_url": None,
        "source_image_url": "http://localhost/uploads/photos/abc123.jpg",
        "source_attribution": None,
        "extraction_metadata": {
            "ocr_confidence": "medium",
            "raw_ocr_text": mock_ocr_text,
            "extraction_method": "ocr",
            "processing_time_ms": 0,
        }
    }

    # Mock storage
    mock_storage = Mock()
    mock_storage.save.return_value = "http://localhost/uploads/photos/abc123.jpg"

    with patch('app.services.extraction_service.ocr_image', return_value=mock_ocr_text) as mock_ocr, \
         patch('app.services.extraction_service._structure_with_claude', return_value=mock_draft_dict) as mock_claude, \
         patch('app.services.extraction_service.get_storage', return_value=mock_storage):

        result = extraction_service.extract_from_photo(image_data, filename)

        # Verify OCR was called with image data
        mock_ocr.assert_called_once_with(image_data)

        # Verify Claude was called with OCR text
        mock_claude.assert_called_once_with(mock_ocr_text, "photo")

        # Verify storage.save was called
        assert mock_storage.save.called

        # Verify result is a DraftRecipe
        assert isinstance(result, DraftRecipe)
        assert result.title == "Recipe Title"
        assert result.source_type == "photo"
        assert result.extraction_metadata.extraction_method == "ocr"


def test_extract_photo_empty_bytes_raises_error():
    """Test extract_from_photo raises ExtractionError for empty image data."""
    with pytest.raises(ExtractionError) as exc_info:
        extraction_service.extract_from_photo(b"", "test.jpg")

    assert "Image data is empty" in str(exc_info.value)


def test_extract_photo_invalid_file_type_raises_error():
    """Test extract_from_photo raises ExtractionError for invalid file types."""
    image_data = b"fake-image-bytes"

    # Test with .gif
    with pytest.raises(ExtractionError) as exc_info:
        extraction_service.extract_from_photo(image_data, "test.gif")
    assert "Invalid file type: .gif" in str(exc_info.value)

    # Test with .bmp
    with pytest.raises(ExtractionError) as exc_info:
        extraction_service.extract_from_photo(image_data, "test.bmp")
    assert "Invalid file type: .bmp" in str(exc_info.value)

    # Test with no extension
    with pytest.raises(ExtractionError) as exc_info:
        extraction_service.extract_from_photo(image_data, "test")
    assert "Invalid file type:" in str(exc_info.value)


def test_extract_photo_assesses_ocr_confidence():
    """Test extract_from_photo correctly assesses OCR confidence based on text length."""
    image_data = b"fake-image-bytes"
    filename = "test.jpg"

    mock_storage = Mock()
    mock_storage.save.return_value = "http://localhost/uploads/photos/abc123.jpg"

    mock_draft_dict = {
        "title": "Test",
        "description": None,
        "cuisine": None,
        "difficulty": "easy",
        "prep_time": None,
        "cook_time": None,
        "total_time": None,
        "base_servings": 4,
        "ingredients": [],
        "steps": [],
        "equipment": [],
        "tags": [],
        "source_type": "photo",
    }

    # Test high confidence (>200 chars)
    long_text = "a" * 250
    with patch('app.services.extraction_service.ocr_image', return_value=long_text), \
         patch('app.services.extraction_service._structure_with_claude', return_value=mock_draft_dict), \
         patch('app.services.extraction_service.get_storage', return_value=mock_storage):

        result = extraction_service.extract_from_photo(image_data, filename)
        assert result.extraction_metadata.ocr_confidence == "high"

    # Test medium confidence (>50, <=200 chars)
    medium_text = "a" * 100
    with patch('app.services.extraction_service.ocr_image', return_value=medium_text), \
         patch('app.services.extraction_service._structure_with_claude', return_value=mock_draft_dict), \
         patch('app.services.extraction_service.get_storage', return_value=mock_storage):

        result = extraction_service.extract_from_photo(image_data, filename)
        assert result.extraction_metadata.ocr_confidence == "medium"

    # Test low confidence (<=50 chars)
    short_text = "a" * 30
    with patch('app.services.extraction_service.ocr_image', return_value=short_text), \
         patch('app.services.extraction_service._structure_with_claude', return_value=mock_draft_dict), \
         patch('app.services.extraction_service.get_storage', return_value=mock_storage):

        result = extraction_service.extract_from_photo(image_data, filename)
        assert result.extraction_metadata.ocr_confidence == "low"


# ─── EXTRACT FROM URL WITH CACHING TESTS ────────────────────────────


def test_extract_url_cache_hit_returns_cached_result():
    """Test extract_from_url returns cached result immediately on cache hit."""
    url = "https://example.com/recipe"

    # Mock cached data
    cached_data = {
        "title": "Cached Recipe",
        "description": "From cache",
        "cuisine": None,
        "difficulty": "easy",
        "prep_time": 10,
        "cook_time": 20,
        "total_time": 30,
        "base_servings": 4,
        "ingredients": [],
        "steps": [],
        "equipment": [],
        "tags": [],
        "source_type": "url",
        "source_url": url,
        "source_image_url": None,
        "source_attribution": None,
        "extraction_metadata": {
            "extraction_method": "json_ld",
            "cache_hit": False,  # Will be updated to True
            "processing_time_ms": 5000,
        }
    }

    import json
    cached_json = json.dumps(cached_data)

    with patch('app.services.extraction_service.cache_get', return_value=cached_json) as mock_cache_get, \
         patch('app.services.extraction_service.normalise_url', return_value=url):

        result = extraction_service.extract_from_url(url)

        # Verify cache was checked
        mock_cache_get.assert_called_once()

        # Verify result is from cache
        assert isinstance(result, DraftRecipe)
        assert result.title == "Cached Recipe"
        assert result.extraction_metadata.cache_hit is True
        assert result.extraction_metadata.processing_time_ms == 0


def test_extract_url_cache_miss_stores_result():
    """Test extract_from_url stores result in cache after successful extraction."""
    url = "https://example.com/recipe"

    mock_draft_dict = {
        "title": "Fresh Recipe",
        "description": "Newly extracted",
        "cuisine": None,
        "difficulty": "easy",
        "prep_time": 10,
        "cook_time": 20,
        "total_time": 30,
        "base_servings": 4,
        "ingredients": [],
        "steps": [],
        "equipment": [],
        "tags": [],
        "source_type": "url",
        "source_url": url,
        "source_image_url": None,
        "source_attribution": None,
        "extraction_metadata": {
            "extraction_method": "json_ld",
            "cache_hit": False,
            "processing_time_ms": 0,
        }
    }

    mock_html = "<html><body>Recipe content</body></html>"

    with patch('app.services.extraction_service.cache_get', return_value=None) as mock_cache_get, \
         patch('app.services.extraction_service.cache_set') as mock_cache_set, \
         patch('app.services.extraction_service.normalise_url', return_value=url), \
         patch('app.services.extraction_service.fetch_page', return_value=mock_html), \
         patch('app.services.extraction_service.extract_json_ld', return_value=None), \
         patch('app.services.extraction_service.extract_page_text', return_value="Recipe text"), \
         patch('app.services.extraction_service._structure_with_claude', return_value=mock_draft_dict), \
         patch('app.services.extraction_service.get_client', return_value=Mock()):

        result = extraction_service.extract_from_url(url)

        # Verify cache was checked (miss)
        mock_cache_get.assert_called_once()

        # Verify result was stored in cache
        mock_cache_set.assert_called_once()
        call_args = mock_cache_set.call_args
        assert call_args[1]['ttl_seconds'] == 2592000  # 30 days

        # Verify result
        assert isinstance(result, DraftRecipe)
        assert result.title == "Fresh Recipe"
        assert result.extraction_metadata.cache_hit is False


def test_extract_url_redis_failure_continues_without_cache():
    """Test extract_from_url continues gracefully when Redis fails."""
    url = "https://example.com/recipe"

    mock_draft_dict = {
        "title": "Recipe Without Cache",
        "description": "Extracted despite Redis failure",
        "cuisine": None,
        "difficulty": "easy",
        "prep_time": 10,
        "cook_time": 20,
        "total_time": 30,
        "base_servings": 4,
        "ingredients": [],
        "steps": [],
        "equipment": [],
        "tags": [],
        "source_type": "url",
        "source_url": url,
        "source_image_url": None,
        "source_attribution": None,
        "extraction_metadata": {
            "extraction_method": "llm_scrape",
            "cache_hit": False,
            "processing_time_ms": 0,
        }
    }

    mock_html = "<html><body>Recipe content</body></html>"

    # Mock cache_get to raise an exception
    with patch('app.services.extraction_service.cache_get', side_effect=Exception("Redis connection failed")), \
         patch('app.services.extraction_service.cache_set', side_effect=Exception("Redis connection failed")), \
         patch('app.services.extraction_service.normalise_url', return_value=url), \
         patch('app.services.extraction_service.fetch_page', return_value=mock_html), \
         patch('app.services.extraction_service.extract_json_ld', return_value=None), \
         patch('app.services.extraction_service.extract_page_text', return_value="Recipe text"), \
         patch('app.services.extraction_service._structure_with_claude', return_value=mock_draft_dict), \
         patch('app.services.extraction_service.get_client', return_value=Mock()):

        # Should not raise exception despite Redis failures
        result = extraction_service.extract_from_url(url)

        # Verify extraction still succeeded
        assert isinstance(result, DraftRecipe)
        assert result.title == "Recipe Without Cache"


# ─── EXTRACT FROM CAPTION TESTS ─────────────────────────────────────


def test_extract_caption_empty_text_raises_error():
    """Test extract_from_caption raises ExtractionError for empty caption."""
    with pytest.raises(ExtractionError) as exc_info:
        extraction_service.extract_from_caption("", None)

    assert "Caption text cannot be empty" in str(exc_info.value)

    # Test whitespace-only caption
    with pytest.raises(ExtractionError) as exc_info:
        extraction_service.extract_from_caption("   \n  \t  ", None)

    assert "Caption text cannot be empty" in str(exc_info.value)


def test_extract_caption_success():
    """Test extract_from_caption successfully extracts recipe from caption text."""
    caption_text = "Spaghetti Carbonara:\n400g spaghetti\n200g guanciale\nMix and serve!"
    source_url = "https://instagram.com/p/abc123"

    mock_draft_dict = {
        "title": "Spaghetti Carbonara",
        "description": "Classic Italian pasta",
        "cuisine": "Italian",
        "difficulty": "medium",
        "prep_time": 10,
        "cook_time": 15,
        "total_time": 25,
        "base_servings": 4,
        "ingredients": [
            {"name": "spaghetti", "quantity": 400, "unit": "g", "sort_order": 0}
        ],
        "steps": [
            {"step_number": 1, "instruction": "Mix and serve."}
        ],
        "equipment": [],
        "tags": ["pasta", "italian"],
        "source_type": "instagram",
    }

    with patch('app.services.extraction_service._structure_with_claude', return_value=mock_draft_dict):
        result = extraction_service.extract_from_caption(caption_text, source_url)

        assert isinstance(result, DraftRecipe)
        assert result.title == "Spaghetti Carbonara"
        assert result.source_type == "instagram"
        assert result.source_url == source_url
        assert result.extraction_metadata.extraction_method == "llm_caption"
