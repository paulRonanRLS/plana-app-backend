"""
Google Cloud Vision API client for OCR.

Provides text detection from recipe card images. When GOOGLE_CLOUD_ENABLED=false,
returns mock OCR text for testing.
"""

import logging
from google.cloud import vision
from app.config import get_settings

logger = logging.getLogger(__name__)

_client: vision.ImageAnnotatorClient | None = None
_initialized = False
_enabled = True

# Mock OCR text returned when Google Cloud Vision is disabled
_MOCK_OCR_TEXT = """Classic Chocolate Chip Cookies

Ingredients:
- 2 1/4 cups all-purpose flour
- 1 tsp baking soda
- 1 tsp salt
- 1 cup butter, softened
- 3/4 cup granulated sugar
- 3/4 cup packed brown sugar
- 2 large eggs
- 2 tsp vanilla extract
- 2 cups chocolate chips

Instructions:
1. Preheat oven to 375°F (190°C).
2. Mix flour, baking soda, and salt in a bowl.
3. Beat butter and sugars until creamy. Add eggs and vanilla.
4. Gradually blend in flour mixture. Stir in chocolate chips.
5. Drop rounded tablespoons onto ungreased baking sheets.
6. Bake for 9-11 minutes or until golden brown.
7. Cool on baking sheet for 2 minutes, then remove to wire racks.

Makes about 5 dozen cookies
Prep time: 15 minutes
Bake time: 10 minutes per batch
"""


def _get_client() -> vision.ImageAnnotatorClient | None:
    """
    Get the Google Cloud Vision client instance.

    Returns None if GOOGLE_CLOUD_ENABLED=false.
    GOOGLE_APPLICATION_CREDENTIALS is read automatically by Google SDK.

    Returns:
        vision.ImageAnnotatorClient | None: Configured client or None if disabled
    """
    global _client, _initialized, _enabled

    if _initialized:
        return _client

    settings = get_settings()

    # Check if Google Cloud Vision is enabled
    google_cloud_enabled = getattr(settings, 'google_cloud_enabled', False)

    if not google_cloud_enabled:
        logger.info("Google Cloud Vision is disabled (GOOGLE_CLOUD_ENABLED=false) - using mock OCR")
        _enabled = False
        _client = None
        _initialized = True
        return _client

    # Set GOOGLE_APPLICATION_CREDENTIALS environment variable if provided
    # The Google Cloud SDK looks for this in os.environ, not in settings
    import os
    if settings.google_application_credentials and isinstance(settings.google_application_credentials, str):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = settings.google_application_credentials
        logger.info(f"Set GOOGLE_APPLICATION_CREDENTIALS to: {settings.google_application_credentials}")

    # Initialize Vision client (reads GOOGLE_APPLICATION_CREDENTIALS automatically)
    try:
        _client = vision.ImageAnnotatorClient()
        _enabled = True
        logger.info("Google Cloud Vision client initialized successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize Google Cloud Vision client: {e} - using mock OCR")
        _enabled = False
        _client = None

    _initialized = True
    return _client


def ocr_image(image_bytes: bytes) -> str:
    """
    Extract text from an image using Google Cloud Vision API.

    When GOOGLE_CLOUD_ENABLED=false, returns mock OCR text.

    Args:
        image_bytes: Raw image bytes (JPEG or PNG)

    Returns:
        str: Extracted text from the image

    Raises:
        ValueError: If image is too large (>10MB) or empty
        RuntimeError: If OCR fails or no text is detected
    """
    # Import here to avoid issues if service is being imported before ExtractionError is defined
    from app.services.extraction_service import ExtractionError

    # Validate image size
    if not image_bytes:
        raise ExtractionError("Image data is empty")

    image_size_mb = len(image_bytes) / (1024 * 1024)
    if image_size_mb > 10:
        raise ExtractionError(f"Image too large: {image_size_mb:.1f}MB (max 10MB)")

    client = _get_client()

    # If disabled, return mock text
    if not _enabled or client is None:
        logger.debug("Using mock OCR text (Google Cloud Vision disabled)")
        return _MOCK_OCR_TEXT

    try:
        # Create Vision API image object
        image = vision.Image(content=image_bytes)

        # Call text detection
        response = client.text_detection(image=image)

        # Check for API errors
        if response.error.message:
            raise ExtractionError(f"Google Cloud Vision API error: {response.error.message}")

        # Check if any text was detected
        if not response.text_annotations:
            raise ExtractionError("No text detected in image")

        # Return full document text (first annotation contains all text)
        full_text = response.text_annotations[0].description

        logger.debug(f"OCR extracted {len(full_text)} characters")

        return full_text

    except ExtractionError:
        raise
    except Exception as e:
        raise ExtractionError(f"OCR failed: {e}") from e
