"""Canva OAuth2 + PKCE flow — jalankan di lokal untuk dapat access token."""
import http.server
import urllib.parse
import webbrowser
import threading
import base64
import hashlib
import secrets
import json
import urllib.request

CLIENT_ID = "OC-AZ1nSLjepCu5"
PORT = 3000
REDIRECT_URI = f"http://127.0.0.1:{PORT}/callback"
SCOPES = "design:content:write design:content:read design:meta:read asset:write"
TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"

auth_code = None


def generate_pkce():
    """Generate PKCE code_verifier and code_challenge (S256)."""
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/callback" and "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>OK! Authorization code received.</h1><p>Kembali ke terminal.</p>")
        else:
            error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<h1>Error: {error}</h1>".encode())

    def log_message(self, fmt, *args):
        pass  # suppress logs


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

    try:
        server = http.server.HTTPServer(("127.0.0.1", PORT), CallbackHandler)
    except OSError as e:
        print(f"[ERROR] Tidak bisa start server di port {PORT}: {e}")
        print("Coba tutup aplikasi lain yang pakai port ini, atau ganti PORT di script.")
        return

    print(f"\nServer BERHASIL jalan di http://127.0.0.1:{PORT}")
    print(f"\n===== COPY URL INI DAN BUKA DI BROWSER =====")
    print(authorize_url)
    print("=============================================\n")
    print("Buka URL di atas di Chrome/Edge, approve, lalu kembali ke sini.")
    print("Menunggu...\n")

    while auth_code is None:
        server.handle_request()
    server.server_close()

    if not auth_code:
        print("\n[ERROR] Tidak dapat authorization code. Timeout atau user cancel.")
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
