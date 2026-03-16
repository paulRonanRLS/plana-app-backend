"""
Integration tests for extraction endpoints - stub verification.
"""

import pytest
import io


def test_extract_from_url(test_user):
    """Test POST /extract/url returns DraftRecipe."""
    client = test_user["client"]
    headers = test_user["headers"]

    request_data = {"url": "https://example.com/recipe"}

    response = client.post("/v1/extract/url", headers=headers, json=request_data)

    assert response.status_code == 200
    data = response.json()
    # Verify DraftRecipe structure
    assert "title" in data
    assert "ingredients" in data
    assert "steps" in data
    assert "extraction_metadata" in data
    assert data["source_type"] == "url"
    assert data["source_url"] == "https://example.com/recipe"


def test_extract_from_url_invalid(test_user):
    """Test POST /extract/url rejects invalid URLs."""
    client = test_user["client"]
    headers = test_user["headers"]

    request_data = {"url": "not-a-valid-url"}

    response = client.post("/v1/extract/url", headers=headers, json=request_data)

    assert response.status_code == 400
    assert "URL must start with" in response.json()["detail"]


def test_extract_from_caption(test_user):
    """Test POST /extract/caption returns DraftRecipe."""
    client = test_user["client"]
    headers = test_user["headers"]

    request_data = {
        "caption_text": "Mix 2 cups flour with 1 cup water. Bake at 350F for 30 minutes.",
        "source_url": "https://instagram.com/p/abc123",
    }

    response = client.post("/v1/extract/caption", headers=headers, json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert "title" in data
    assert "ingredients" in data
    assert "steps" in data
    assert data["source_type"] == "instagram"


def test_extract_from_caption_empty(test_user):
    """Test POST /extract/caption rejects empty caption."""
    client = test_user["client"]
    headers = test_user["headers"]

    request_data = {"caption_text": "   ", "source_url": None}

    response = client.post("/v1/extract/caption", headers=headers, json=request_data)

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_extract_from_photo_valid(test_user):
    """Test POST /extract/photo with valid image."""
    client = test_user["client"]
    headers = test_user["headers"]

    # Create a fake JPEG file
    fake_image = io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # JPEG magic bytes
    files = {"image": ("recipe.jpg", fake_image, "image/jpeg")}

    response = client.post("/v1/extract/photo", headers=headers, files=files)

    assert response.status_code == 200
    data = response.json()
    assert "title" in data
    assert "ingredients" in data
    assert data["source_type"] == "photo"
    assert "extraction_metadata" in data


def test_extract_from_photo_invalid_type(test_user):
    """Test POST /extract/photo rejects non-image files."""
    client = test_user["client"]
    headers = test_user["headers"]

    # Create a text file
    fake_file = io.BytesIO(b"not an image")
    files = {"image": ("recipe.txt", fake_file, "text/plain")}

    response = client.post("/v1/extract/photo", headers=headers, files=files)

    assert response.status_code == 400
    assert "JPEG" in response.json()["detail"] or "PNG" in response.json()["detail"]
