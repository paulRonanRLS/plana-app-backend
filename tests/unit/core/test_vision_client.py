"""
Unit tests for Google Cloud Vision client.

Tests OCR functionality with mocked Vision API and stub mode.
"""

import pytest
from unittest.mock import Mock, patch

from app.core import vision_client
from app.services.extraction_service import ExtractionError


def test_ocr_image_disabled_returns_mock_text():
    """Test ocr_image returns mock text when GOOGLE_CLOUD_ENABLED=false."""
    image_bytes = b"fake-image-data"

    # Reset module state to force reinitialization
    vision_client._initialized = False
    vision_client._client = None

    # Mock settings to disable Google Cloud
    mock_settings = Mock()
    mock_settings.google_cloud_enabled = False

    with patch('app.core.vision_client.get_settings', return_value=mock_settings):
        result = vision_client.ocr_image(image_bytes)

        # Should return mock text containing "Classic Chocolate Chip Cookies"
        assert "Classic Chocolate Chip Cookies" in result
        assert "Ingredients:" in result
        assert "Instructions:" in result
        assert len(result) > 100  # Mock text is substantial


def test_ocr_image_empty_bytes_raises_error():
    """Test ocr_image raises ExtractionError for empty image data."""
    with pytest.raises(ExtractionError) as exc_info:
        vision_client.ocr_image(b"")

    assert "Image data is empty" in str(exc_info.value)


def test_ocr_image_too_large_raises_error():
    """Test ocr_image raises ExtractionError for images over 10MB."""
    # Create 11MB of fake image data
    large_image = b"x" * (11 * 1024 * 1024)

    with pytest.raises(ExtractionError) as exc_info:
        vision_client.ocr_image(large_image)

    assert "Image too large" in str(exc_info.value)
    assert "max 10MB" in str(exc_info.value)


def test_ocr_image_no_text_detected_raises_error():
    """Test ocr_image raises ExtractionError when no text is detected in image."""
    image_bytes = b"fake-image-with-no-text"

    # Reset module state
    vision_client._initialized = False
    vision_client._client = None

    # Mock settings to enable Google Cloud
    mock_settings = Mock()
    mock_settings.google_cloud_enabled = True

    # Mock Vision API client to return empty text_annotations
    mock_vision_client = Mock()
    mock_response = Mock()
    mock_response.error.message = ""
    mock_response.text_annotations = []  # No text detected
    mock_vision_client.text_detection.return_value = mock_response

    with patch('app.core.vision_client.get_settings', return_value=mock_settings), \
         patch('app.core.vision_client.vision.ImageAnnotatorClient', return_value=mock_vision_client):

        with pytest.raises(ExtractionError) as exc_info:
            vision_client.ocr_image(image_bytes)

        assert "No text detected in image" in str(exc_info.value)


def test_ocr_image_api_error_raises_error():
    """Test ocr_image raises ExtractionError when Vision API returns an error."""
    image_bytes = b"fake-image-data"

    # Reset module state
    vision_client._initialized = False
    vision_client._client = None

    # Mock settings to enable Google Cloud
    mock_settings = Mock()
    mock_settings.google_cloud_enabled = True

    # Mock Vision API client to return an error
    mock_vision_client = Mock()
    mock_response = Mock()
    mock_response.error.message = "API quota exceeded"
    mock_vision_client.text_detection.return_value = mock_response

    with patch('app.core.vision_client.get_settings', return_value=mock_settings), \
         patch('app.core.vision_client.vision.ImageAnnotatorClient', return_value=mock_vision_client):

        with pytest.raises(ExtractionError) as exc_info:
            vision_client.ocr_image(image_bytes)

        assert "Google Cloud Vision API error" in str(exc_info.value)
        assert "API quota exceeded" in str(exc_info.value)


def test_ocr_image_success():
    """Test ocr_image successfully extracts text from image when enabled."""
    image_bytes = b"fake-image-data"
    expected_text = "Recipe Title\n2 cups flour\n1 tsp salt\nBake at 350F"

    # Reset module state
    vision_client._initialized = False
    vision_client._client = None

    # Mock settings to enable Google Cloud
    mock_settings = Mock()
    mock_settings.google_cloud_enabled = True

    # Mock Vision API client to return text
    mock_vision_client = Mock()
    mock_response = Mock()
    mock_response.error.message = ""
    mock_annotation = Mock()
    mock_annotation.description = expected_text
    mock_response.text_annotations = [mock_annotation]
    mock_vision_client.text_detection.return_value = mock_response

    with patch('app.core.vision_client.get_settings', return_value=mock_settings), \
         patch('app.core.vision_client.vision.ImageAnnotatorClient', return_value=mock_vision_client):

        result = vision_client.ocr_image(image_bytes)

        assert result == expected_text
        # Verify text_detection was called
        mock_vision_client.text_detection.assert_called_once()
