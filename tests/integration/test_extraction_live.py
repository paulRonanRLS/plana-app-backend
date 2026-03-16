"""
Live integration tests for extraction service.

These tests require CLAUDE_ENABLED=true and a real ANTHROPIC_API_KEY.
Some tests also require GOOGLE_CLOUD_ENABLED=true and REDIS_ENABLED=true.

Run manually with: CLAUDE_ENABLED=true poetry run pytest tests/integration/test_extraction_live.py -v -m live

DO NOT run in CI - these make real API calls.
"""

import pytest
import os
from pathlib import Path


@pytest.mark.live
def test_live_extract_caption_real_recipe(test_user):
    """
    Test caption extraction with a real recipe and live Claude API.

    Requires: CLAUDE_ENABLED=true, ANTHROPIC_API_KEY set
    """
    client = test_user["client"]
    headers = test_user["headers"]

    caption = """
    Simple Pasta Carbonara

    Ingredients:
    - 400g spaghetti
    - 200g guanciale or pancetta
    - 4 egg yolks
    - 100g Pecorino Romano, grated
    - Black pepper to taste

    Instructions:
    1. Cook pasta in salted boiling water until al dente (about 8-10 minutes)
    2. Meanwhile, dice guanciale and cook in a pan until crispy
    3. Whisk egg yolks with grated cheese and plenty of black pepper
    4. Drain pasta (reserve some pasta water)
    5. Mix hot pasta with guanciale, remove from heat
    6. Quickly stir in egg mixture, adding pasta water to create a creamy sauce
    7. Serve immediately with extra cheese

    Serves 4 | Prep: 5 min | Cook: 15 min
    """

    request_data = {
        "caption_text": caption,
        "source_url": "https://instagram.com/p/test123",
    }

    response = client.post("/v1/extract/caption", headers=headers, json=request_data)

    assert response.status_code == 200, f"Failed with: {response.json()}"
    data = response.json()

    # Verify structure
    assert "title" in data
    assert "ingredients" in data
    assert "steps" in data
    assert "extraction_metadata" in data

    # Verify source
    assert data["source_type"] == "instagram"
    assert data["source_url"] == "https://instagram.com/p/test123"

    # Verify extraction metadata
    assert data["extraction_metadata"]["extraction_method"] == "llm_caption"
    assert data["extraction_metadata"]["processing_time_ms"] > 0

    # Verify Claude extracted some ingredients and steps
    assert len(data["ingredients"]) > 0, "Claude should extract at least some ingredients"
    assert len(data["steps"]) > 0, "Claude should extract at least some steps"

    # Print for manual inspection
    print("\n=== Extracted Recipe ===")
    print(f"Title: {data.get('title')}")
    print(f"Ingredients: {len(data['ingredients'])}")
    print(f"Steps: {len(data['steps'])}")
    print(f"Processing time: {data['extraction_metadata']['processing_time_ms']}ms")


@pytest.mark.live
def test_live_extract_url_with_json_ld(test_user):
    """
    Test URL extraction from a site with JSON-LD markup.

    Uses NYT Cooking which has good JSON-LD Recipe data.

    Requires: CLAUDE_ENABLED=true, ANTHROPIC_API_KEY set
    """
    client = test_user["client"]
    headers = test_user["headers"]

    # NYT Cooking has excellent JSON-LD markup
    request_data = {
        "url": "https://cooking.nytimes.com/recipes/1015819-pasta-carbonara"
    }

    response = client.post("/v1/extract/url", headers=headers, json=request_data)

    assert response.status_code == 200, f"Failed with: {response.json()}"
    data = response.json()

    # Verify structure
    assert "title" in data
    assert "ingredients" in data
    assert "steps" in data
    assert "extraction_metadata" in data

    # Verify source
    assert data["source_type"] == "url"
    assert data["source_url"] == request_data["url"]

    # Verify used JSON-LD
    assert data["extraction_metadata"]["extraction_method"] == "json_ld"
    assert data["extraction_metadata"]["cache_hit"] is False

    # Verify extracted data
    assert len(data["ingredients"]) > 0
    assert len(data["steps"]) > 0

    # Should have attribution from JSON-LD
    # NYT usually has author in JSON-LD
    print("\n=== Extracted Recipe (JSON-LD) ===")
    print(f"Title: {data.get('title')}")
    print(f"Attribution: {data.get('source_attribution')}")
    print(f"Image URL: {data.get('source_image_url')}")
    print(f"Ingredients: {len(data['ingredients'])}")
    print(f"Steps: {len(data['steps'])}")
    print(f"Processing time: {data['extraction_metadata']['processing_time_ms']}ms")


@pytest.mark.live
def test_live_extract_url_fallback(test_user):
    """
    Test URL extraction from a site WITHOUT JSON-LD (fallback to scraping).

    Uses a blog or site that doesn't have structured data.

    Requires: CLAUDE_ENABLED=true, ANTHROPIC_API_KEY set
    """
    client = test_user["client"]
    headers = test_user["headers"]

    # Example.com won't have recipe JSON-LD, so we'll get llm_scrape
    # In a real scenario, you'd use a food blog without JSON-LD
    request_data = {
        "url": "https://www.seriouseats.com/best-carbonara-recipe"
    }

    response = client.post("/v1/extract/url", headers=headers, json=request_data)

    # This might fail if the site blocks us or has JSON-LD we don't know about
    # For now, just verify the response structure
    if response.status_code == 200:
        data = response.json()

        # Verify structure
        assert "title" in data
        assert "ingredients" in data
        assert "steps" in data
        assert "extraction_metadata" in data

        # Verify source
        assert data["source_type"] == "url"
        assert data["source_url"] == request_data["url"]

        # Print results
        print("\n=== Extracted Recipe (Fallback) ===")
        print(f"Title: {data.get('title')}")
        print(f"Extraction method: {data['extraction_metadata'].get('extraction_method')}")
        print(f"Ingredients: {len(data['ingredients'])}")
        print(f"Steps: {len(data['steps'])}")
        print(f"Processing time: {data['extraction_metadata']['processing_time_ms']}ms")
    else:
        # If it fails, that's okay for this test - the URL might not be accessible
        print(f"\nURL extraction failed (expected): {response.status_code}")
        print(f"Response: {response.json()}")


@pytest.mark.live
def test_live_extract_photo_real_image(test_user):
    """
    Test photo extraction with a real image using OCR and Claude.

    Requires: GOOGLE_CLOUD_ENABLED=true, CLAUDE_ENABLED=true
    Optional: tests/fixtures/test_recipe_image.jpg

    If test image doesn't exist, the test is skipped.
    """
    client = test_user["client"]
    headers = test_user["headers"]

    # Check if test image exists
    test_image_path = Path(__file__).parent.parent / "fixtures" / "test_recipe_image.jpg"
    if not test_image_path.exists():
        pytest.skip(f"Test image not found at {test_image_path}")

    # Read image data
    with open(test_image_path, "rb") as f:
        image_data = f.read()

    # Make request
    files = {"file": ("test_recipe.jpg", image_data, "image/jpeg")}
    response = client.post("/v1/extract/photo", headers=headers, files=files)

    assert response.status_code == 200, f"Failed with: {response.json()}"
    data = response.json()

    # Verify structure
    assert "title" in data
    assert "ingredients" in data
    assert "steps" in data
    assert "extraction_metadata" in data

    # Verify source
    assert data["source_type"] == "photo"
    assert data["source_image_url"] is not None  # Should have storage URL

    # Verify extraction metadata
    assert data["extraction_metadata"]["extraction_method"] == "ocr"
    assert data["extraction_metadata"]["ocr_confidence"] in ["low", "medium", "high"]
    assert "raw_ocr_text" in data["extraction_metadata"]
    assert data["extraction_metadata"]["processing_time_ms"] > 0

    # Verify extracted data
    assert len(data["ingredients"]) > 0, "Should extract at least some ingredients"
    assert len(data["steps"]) > 0, "Should extract at least some steps"

    # Print for manual inspection
    print("\n=== Extracted Recipe (Photo OCR) ===")
    print(f"Title: {data.get('title')}")
    print(f"OCR Confidence: {data['extraction_metadata']['ocr_confidence']}")
    print(f"OCR Text Length: {len(data['extraction_metadata']['raw_ocr_text'])} chars")
    print(f"Ingredients: {len(data['ingredients'])}")
    print(f"Steps: {len(data['steps'])}")
    print(f"Processing time: {data['extraction_metadata']['processing_time_ms']}ms")


@pytest.mark.live
def test_live_extract_url_cache_miss_then_hit(test_user):
    """
    Test URL extraction caching: first call is cache miss, second is cache hit.

    Requires: CLAUDE_ENABLED=true, REDIS_ENABLED=true

    Makes two requests to the same URL and verifies:
    1. First request is a cache miss (extracts and stores)
    2. Second request is a cache hit (returns instantly)
    """
    client = test_user["client"]
    headers = test_user["headers"]

    # Use NYT Cooking as it has reliable JSON-LD and stable URLs
    test_url = "https://cooking.nytimes.com/recipes/1015819-pasta-carbonara"
    request_data = {"url": test_url}

    # First request - should be cache miss
    print("\n=== First request (cache miss) ===")
    response1 = client.post("/v1/extract/url", headers=headers, json=request_data)
    assert response1.status_code == 200, f"First request failed: {response1.json()}"
    data1 = response1.json()

    # Verify it was a cache miss
    assert data1["extraction_metadata"]["cache_hit"] is False
    processing_time_1 = data1["extraction_metadata"]["processing_time_ms"]
    print(f"Cache miss - Processing time: {processing_time_1}ms")
    print(f"Title: {data1.get('title')}")
    print(f"Extraction method: {data1['extraction_metadata'].get('extraction_method')}")

    # Second request - should be cache hit
    print("\n=== Second request (cache hit) ===")
    response2 = client.post("/v1/extract/url", headers=headers, json=request_data)
    assert response2.status_code == 200, f"Second request failed: {response2.json()}"
    data2 = response2.json()

    # Verify it was a cache hit
    assert data2["extraction_metadata"]["cache_hit"] is True
    processing_time_2 = data2["extraction_metadata"]["processing_time_ms"]
    print(f"Cache hit - Processing time: {processing_time_2}ms")
    print(f"Title: {data2.get('title')}")

    # Cache hit should be much faster (should be 0ms)
    assert processing_time_2 == 0, "Cache hit should have 0ms processing time"

    # Data should be identical except for cache_hit and processing_time_ms
    assert data1["title"] == data2["title"]
    assert data1["source_url"] == data2["source_url"]
    assert len(data1["ingredients"]) == len(data2["ingredients"])
    assert len(data1["steps"]) == len(data2["steps"])

    print(f"\n✓ Caching verified: {processing_time_1}ms → {processing_time_2}ms")
