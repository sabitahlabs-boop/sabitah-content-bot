import sys
import io
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SPREADSHEET_ID = "1UsZEPs9t0UOyzuhX3iP7_PdLaf-IITvrpsQ3UrEBisM"
OAUTH_CREDENTIALS_FILE = "oauth_credentials.json"
TOKEN_FILE = "token.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(OAUTH_CREDENTIALS_FILE):
                print(f"[ERROR] File '{OAUTH_CREDENTIALS_FILE}' tidak ditemukan!")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return creds


def main():
    print("=" * 50)
    print("  TEST WRITE KE GOOGLE SHEET")
    print("=" * 50)

    creds = authenticate()
    if not creds:
        return

    service = build("sheets", "v4", credentials=creds)
    sheets_api = service.spreadsheets()

    # Tulis "test berhasil" ke sel E2
    result = sheets_api.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="E2",
        valueInputOption="RAW",
        body={"values": [["test berhasil"]]},
    ).execute()

    updated = result.get("updatedCells", 0)
    print(f"\n  Sel E2 berhasil ditulis: 'test berhasil'")
    print(f"  Updated cells: {updated}")

    # Verifikasi dengan membaca ulang
    verify = sheets_api.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="E2",
    ).execute()
    value = verify.get("values", [[""]])[0][0]
    print(f"  Verifikasi baca E2: '{value}'")

    print(f"\n{'=' * 50}")
    print("  Selesai!")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
