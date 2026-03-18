#!/usr/bin/env python3
"""
Development script to obtain a Firebase ID token.

Uses Firebase REST API to sign in with email/password and retrieve an ID token
that can be used for testing authenticated API endpoints.

Usage:
    python scripts/get_firebase_token.py

Environment variables required:
    FIREBASE_WEB_API_KEY - Firebase Web API key from Firebase Console
    FIREBASE_TEST_EMAIL - Test user email
    FIREBASE_TEST_PASSWORD - Test user password
"""

import os
import sys
import requests
from datetime import datetime, timedelta


def get_firebase_token():
    """
    Sign in with Firebase REST API and return the ID token.

    Returns:
        tuple: (idToken, expiresIn) or (None, None) on error
    """
    # Read credentials from environment
    api_key = os.getenv("FIREBASE_WEB_API_KEY")
    email = os.getenv("FIREBASE_TEST_EMAIL")
    password = os.getenv("FIREBASE_TEST_PASSWORD")

    # Validate environment variables
    if not api_key:
        print("❌ Error: FIREBASE_WEB_API_KEY environment variable not set", file=sys.stderr)
        return None, None

    if not email:
        print("❌ Error: FIREBASE_TEST_EMAIL environment variable not set", file=sys.stderr)
        return None, None

    if not password:
        print("❌ Error: FIREBASE_TEST_PASSWORD environment variable not set", file=sys.stderr)
        return None, None

    # Firebase REST API endpoint
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"

    # Request payload
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }

    try:
        print(f"🔐 Signing in to Firebase as {email}...", file=sys.stderr)

        # Make the request
        response = requests.post(url, json=payload)

        # Check for errors
        if response.status_code != 200:
            error_data = response.json()
            error_message = error_data.get("error", {}).get("message", "Unknown error")
            print(f"❌ Firebase authentication failed: {error_message}", file=sys.stderr)
            return None, None

        # Parse response
        data = response.json()
        id_token = data.get("idToken")
        expires_in = int(data.get("expiresIn", 3600))

        if not id_token:
            print("❌ Error: No idToken in response", file=sys.stderr)
            return None, None

        return id_token, expires_in

    except requests.exceptions.RequestException as e:
        print(f"❌ Network error: {e}", file=sys.stderr)
        return None, None
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        return None, None


def main():
    """Main entry point."""
    id_token, expires_in = get_firebase_token()

    if not id_token:
        sys.exit(1)

    # Calculate expiry time
    expiry_time = datetime.now() + timedelta(seconds=expires_in)

    # Print results to stderr for information
    print("✅ Successfully obtained Firebase ID token", file=sys.stderr)
    print(f"⏰ Token expires in {expires_in} seconds ({expiry_time.strftime('%H:%M:%S')})", file=sys.stderr)
    print(file=sys.stderr)

    # Print token to stdout (so it can be captured by scripts)
    print(id_token)


if __name__ == "__main__":
    main()
