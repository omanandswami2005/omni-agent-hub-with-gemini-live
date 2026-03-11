#!/usr/bin/env python3
"""Get a Firebase ID token for testing.

Usage
-----
    # Option 1: Using a Google API key + email/password sign-in
    python scripts/get_test_token.py --api-key <WEB_API_KEY> --email test@test.com --password test123

    # Option 2: Using a service account to create a custom token, then exchange it
    python scripts/get_test_token.py --service-account firebase-sa.json --uid test-user-123

    # Then use the token:
    python scripts/test_ws_live.py --token $(python scripts/get_test_token.py ...)

Requires: requests
"""

from __future__ import annotations

import argparse
import json
import sys

def get_token_via_rest_api(api_key: str, email: str, password: str) -> str:
    """Sign in with email/password via Firebase REST API and return ID token."""
    import requests
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    resp = requests.post(url, json={
        "email": email,
        "password": password,
        "returnSecureToken": True,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["idToken"]


def get_token_via_custom_token(sa_path: str, uid: str) -> str:
    """Create a custom token via Admin SDK, then exchange it for an ID token."""
    import firebase_admin
    from firebase_admin import auth, credentials
    import requests

    cred = credentials.Certificate(sa_path)
    try:
        app = firebase_admin.get_app()
    except ValueError:
        app = firebase_admin.initialize_app(cred)

    custom_token = auth.create_custom_token(uid).decode("utf-8")

    # Exchange custom token for ID token via REST API
    # Need the web API key from Firebase console
    project_id = cred.project_id
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=AIzaSy_YOUR_WEB_API_KEY"
    print(f"NOTE: To exchange custom token, you need your Firebase Web API Key.", file=sys.stderr)
    print(f"Custom token (use with Firebase client SDK): {custom_token}", file=sys.stderr)
    return custom_token


def main():
    parser = argparse.ArgumentParser(description="Get a Firebase ID token for testing")
    parser.add_argument("--api-key", help="Firebase Web API key")
    parser.add_argument("--email", help="Email for sign-in")
    parser.add_argument("--password", help="Password for sign-in")
    parser.add_argument("--service-account", help="Path to service account JSON")
    parser.add_argument("--uid", default="test-user-ws", help="UID for custom token")
    args = parser.parse_args()

    if args.api_key and args.email and args.password:
        token = get_token_via_rest_api(args.api_key, args.email, args.password)
        print(token)
    elif args.service_account:
        token = get_token_via_custom_token(args.service_account, args.uid)
        print(token)
    else:
        print("ERROR: Provide --api-key/--email/--password OR --service-account", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
