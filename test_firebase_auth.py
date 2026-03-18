"""
Test script for Firebase authentication.

This script demonstrates how to test the Firebase authentication implementation.

Prerequisites:
1. Firebase credentials file exists at the path specified in .env
2. FIREBASE_ENABLED=true in .env
3. Server is running (poetry run uvicorn app.main:app)

Usage:
    python test_firebase_auth.py <firebase_id_token>

Where <firebase_id_token> is a valid Firebase ID token obtained from your frontend app.
"""

import sys
import requests


def test_firebase_auth(token: str, base_url: str = "http://localhost:8000"):
    """
    Test Firebase authentication by calling the /users/me endpoint.

    Args:
        token: Firebase ID token from your frontend
        base_url: API base URL
    """
    print(f"🔥 Testing Firebase authentication")
    print(f"Token: {token[:20]}..." if len(token) > 20 else f"Token: {token}")
    print(f"API: {base_url}")
    print()

    # Test 1: Call /users/me with the token
    print("📝 Test 1: GET /v1/users/me")
    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(f"{base_url}/v1/users/me", headers=headers)

        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            user = response.json()
            print("✅ Authentication successful!")
            print()
            print("User profile:")
            print(f"  ID: {user.get('id')}")
            print(f"  Name: {user.get('name')}")
            print(f"  Email: {user.get('email')}")
            print(f"  Firebase UID: {user.get('firebase_uid')}")
            print(f"  Avatar URL: {user.get('avatar_url')}")
            print()

            # Test 2: Try creating a recipe
            print("📝 Test 2: POST /v1/recipes")
            recipe_data = {
                "title": "Test Recipe from Firebase Auth",
                "source_type": "manual",
                "base_servings": 4,
                "ingredients": [
                    {"name": "test ingredient", "quantity": 1, "unit": "cup"}
                ],
                "steps": [
                    {"step_number": 1, "instruction": "Test step"}
                ]
            }

            recipe_response = requests.post(
                f"{base_url}/v1/recipes",
                headers=headers,
                json=recipe_data
            )

            print(f"Status: {recipe_response.status_code}")
            if recipe_response.status_code == 201:
                recipe = recipe_response.json()
                print("✅ Recipe created successfully!")
                print(f"  Recipe ID: {recipe.get('id')}")
                print(f"  Title: {recipe.get('title')}")
            else:
                print(f"❌ Recipe creation failed: {recipe_response.json()}")

        elif response.status_code == 401:
            error = response.json()
            print(f"❌ Authentication failed: {error.get('detail')}")
            print()
            print("Possible reasons:")
            print("  - Token is invalid or expired")
            print("  - Token was generated for a different Firebase project")
            print("  - Firebase credentials file is incorrect")

        else:
            print(f"❌ Unexpected response: {response.json()}")

    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to the API server")
        print(f"   Make sure the server is running at {base_url}")
        print("   Start it with: poetry run uvicorn app.main:app")
    except Exception as e:
        print(f"❌ Error: {e}")


def test_stub_mode():
    """Test authentication in stub mode (FIREBASE_ENABLED=false)"""
    print("🔥 Testing stub mode authentication")
    print()

    # In stub mode, any token is accepted as the UID
    test_token = "test-user-stub-mode-123"

    print("📝 Test: GET /v1/users/me with stub token")
    headers = {"Authorization": f"Bearer {test_token}"}

    try:
        response = requests.get("http://localhost:8000/v1/users/me", headers=headers)

        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            user = response.json()
            print("✅ Stub authentication successful!")
            print()
            print("User profile:")
            print(f"  ID: {user.get('id')}")
            print(f"  Name: {user.get('name')}")
            print(f"  Firebase UID: {user.get('firebase_uid')}")
            print()
            print("Note: In stub mode, the token is used directly as the Firebase UID")
        else:
            print(f"❌ Request failed: {response.json()}")

    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to the API server")
        print("   Start it with: FIREBASE_ENABLED=false poetry run uvicorn app.main:app")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Test with provided Firebase token
        token = sys.argv[1]
        test_firebase_auth(token)
    else:
        print("Usage: python test_firebase_auth.py <firebase_id_token>")
        print()
        print("To get a Firebase ID token:")
        print("1. Sign in to your app (web or mobile)")
        print("2. In the browser console or mobile debugger, get the token:")
        print("   JavaScript: firebase.auth().currentUser.getIdToken()")
        print()
        print("Or test in stub mode (no Firebase token needed):")
        print("  FIREBASE_ENABLED=false poetry run uvicorn app.main:app")
        print("  python test_firebase_auth.py stub")
        print()

        # If 'stub' argument, test stub mode
        if len(sys.argv) > 1 and sys.argv[1] == "stub":
            test_stub_mode()
