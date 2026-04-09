import sys
import io
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except ImportError:
    print("Library belum terinstall. Jalankan:")
    print("  pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
    input("\nTekan Enter untuk keluar...")
    sys.exit(1)

# ============================================================
# KONFIGURASI
# ============================================================
SPREADSHEET_ID = "1UsZEPs9t0UOyzuhX3iP7_PdLaf-IITvrpsQ3UrEBisM"
OAUTH_CREDENTIALS_FILE = "oauth_credentials.json"  # dari Google Cloud Console
TOKEN_FILE = "token.json"  # token disimpan otomatis setelah login pertama
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def authenticate():
    """Login via OAuth2. Buka browser di pertama kali, selanjutnya otomatis."""
    creds = None

    # Cek apakah sudah pernah login (token tersimpan)
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # Kalau belum login atau token expired
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Token expired, refreshing...")
            creds.refresh(Request())
        else:
            if not os.path.exists(OAUTH_CREDENTIALS_FILE):
                print(f"\n[ERROR] File '{OAUTH_CREDENTIALS_FILE}' tidak ditemukan!")
                print("Download dari Google Cloud Console > APIs & Services > Credentials")
                print("Pilih OAuth client ID > Download JSON")
                return None

            print("Membuka browser untuk login Google...")
            flow = InstalledAppFlow.from_client_secrets_file(
                OAUTH_CREDENTIALS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Simpan token untuk next time
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
        print("Login berhasil! Token tersimpan.\n")

    return creds


def main():
    print("=" * 60)
    print("   GOOGLE SHEETS READER")
    print("=" * 60)

    # 1. Autentikasi
    creds = authenticate()
    if not creds:
        input("\nTekan Enter untuk keluar...")
        return

    # 2. Konek ke Google Sheets API
    service = build("sheets", "v4", credentials=creds)
    sheets_api = service.spreadsheets()

    # 3. Ambil metadata spreadsheet (semua sheet names)
    try:
        spreadsheet = sheets_api.get(spreadsheetId=SPREADSHEET_ID).execute()
    except Exception as e:
        print(f"\n[ERROR] Gagal membaca spreadsheet: {e}")
        input("\nTekan Enter untuk keluar...")
        return

    sheet_names = [s["properties"]["title"] for s in spreadsheet["sheets"]]

    print(f"\nSpreadsheet: {spreadsheet['properties']['title']}")
    print(f"Total sheets: {len(sheet_names)}")
    print(f"\n{'─' * 60}")
    print("  DAFTAR SHEET:")
    print(f"{'─' * 60}")
    for i, name in enumerate(sheet_names, 1):
        print(f"  {i}. {name}")

    # 4. Baca 5 baris pertama dari sheet pertama
    first_sheet = sheet_names[0]
    result = (
        sheets_api.values()
        .get(spreadsheetId=SPREADSHEET_ID, range=f"'{first_sheet}'!A1:Z5")
        .execute()
    )

    rows = result.get("values", [])

    print(f"\n{'─' * 60}")
    print(f"  5 BARIS PERTAMA dari sheet: \"{first_sheet}\"")
    print(f"{'─' * 60}")

    if not rows:
        print("  (kosong)")
    else:
        for i, row in enumerate(rows, 1):
            print(f"  Baris {i}: {row}")

    print(f"\n{'=' * 60}")
    print("  Selesai!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
    input("\nTekan Enter untuk keluar...")
