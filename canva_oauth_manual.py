"""Canva OAuth2 + PKCE — versi manual (tanpa local server)."""
import urllib.parse
import base64
import hashlib
import secrets
import json
import urllib.request

CLIENT_ID = "OC-AZ1nSLjepCu5"
REDIRECT_URI = "http://127.0.0.1:3000/callback"
SCOPES = "design:content:write design:content:read design:meta:read asset:write"
TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"


def generate_pkce():
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


def main():
    client_secret = input("Masukkan Canva Client Secret: ")

    code_verifier, code_challenge = generate_pkce()

    authorize_url = (
        f"https://www.canva.com/api/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&scope={urllib.parse.quote(SCOPES)}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&code_challenge_method=s256"
        f"&code_challenge={code_challenge}"
    )

    print(f"\n===== STEP 1: BUKA URL INI DI BROWSER =====")
    print(authorize_url)
    print("=============================================\n")

    print("Setelah klik Allow, browser akan error 'connection refused'.")
    print("Itu NORMAL. Lihat ADDRESS BAR browser — URL-nya akan seperti:")
    print("  http://127.0.0.1:3000/callback?code=XXXXXXXX\n")
    print("===== STEP 2: COPY SELURUH URL DARI ADDRESS BAR =====\n")

    callback_url = input("Paste URL dari address bar di sini: ").strip()

    parsed = urllib.parse.urlparse(callback_url)
    params = urllib.parse.parse_qs(parsed.query)
    auth_code = params.get("code", [None])[0]

    if not auth_code:
        print("\n[ERROR] Tidak ada 'code' di URL. Pastikan copy seluruh URL dari address bar.")
        return

    print(f"\nAuthorization code: {auth_code[:20]}...")
    print("Exchanging code for access token...\n")

    credentials = base64.b64encode(f"{CLIENT_ID}:{client_secret}".encode()).decode()
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": auth_code,
        "code_verifier": code_verifier,
        "redirect_uri": REDIRECT_URI,
    }).encode()

    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())

        print("=" * 60)
        print("  ACCESS TOKEN:")
        print(f"  {result.get('access_token', 'N/A')}")
        print()
        print("  REFRESH TOKEN:")
        print(f"  {result.get('refresh_token', 'N/A')}")
        print()
        print(f"  EXPIRES IN: {result.get('expires_in', '?')} seconds")
        print("=" * 60)
        print()
        print("Copy ACCESS TOKEN di atas, lalu set di Railway:")
        print("  CANVA_ACCESS_TOKEN = <paste di sini>")

    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[ERROR] {e.code}: {body}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] {e}")
    input("\nTekan Enter untuk keluar...")
