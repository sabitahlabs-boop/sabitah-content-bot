import sys
import io
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SPREADSHEET_ID = "13_BnnBjVLRcpJAiyieBqF7tnuoRZ7ij7fs0u8Z9Hd1Y"
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
    print("=" * 55)
    print("  TEST WRITE KE MASTER TRACKER")
    print("=" * 55)

    creds = authenticate()
    if not creds:
        return

    service = build("sheets", "v4", credentials=creds)
    sheets_api = service.spreadsheets()

    sheet_name = "Master Tracker"

    # Baca semua data (baris 1 = kategori, baris 2 = header, baris 3+ = data)
    result = sheets_api.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{sheet_name}'",
    ).execute()
    rows = result.get("values", [])

    if len(rows) < 3:
        print("  [ERROR] Sheet tidak punya cukup data.")
        return

    headers = rows[1]  # baris 2 = header asli
    print(f"  Sheet: {sheet_name}")
    print(f"  Total baris data: {len(rows) - 2}")

    # Cari index kolom
    headers_lower = [h.strip().lower().replace("\n", " ") for h in headers]

    col_script_status = -1
    col_script_notes = -1
    for idx, h in enumerate(headers_lower):
        if h == "script status":
            col_script_status = idx
        elif h == "script notes":
            col_script_notes = idx

    if col_script_status == -1:
        print("  [ERROR] Kolom 'Script Status' tidak ditemukan!")
        return
    if col_script_notes == -1:
        print("  [ERROR] Kolom 'Script Notes' tidak ditemukan!")
        return

    print(f"  Kolom Script Status: {chr(65 + col_script_status)} (index {col_script_status})")
    print(f"  Kolom Script Notes : {chr(65 + col_script_notes)} (index {col_script_notes})")

    # Cari baris pertama dengan Script Status = "Not Started"
    target_row = -1
    for i, row in enumerate(rows[2:], start=3):  # baris 3+ (1-indexed di Sheet)
        status = row[col_script_status].strip().lower() if len(row) > col_script_status else ""
        if status == "not started":
            target_row = i
            content_id = row[1].strip() if len(row) > 1 else "?"
            topic = row[4].strip() if len(row) > 4 else "?"
            print(f"\n  Baris pertama 'Not Started' ditemukan:")
            print(f"    Baris Sheet : {target_row}")
            print(f"    Content ID  : {content_id}")
            print(f"    Topic       : {topic[:60]}")
            break

    if target_row == -1:
        print("\n  Tidak ada baris dengan Script Status 'Not Started'.")
        return

    # Tulis ke kolom Script Notes
    col_letter = chr(65 + col_script_notes)
    cell = f"'{sheet_name}'!{col_letter}{target_row}"
    text = "test berhasil dari Claude Code"

    sheets_api.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=cell,
        valueInputOption="RAW",
        body={"values": [[text]]},
    ).execute()

    print(f"\n  Berhasil tulis ke {col_letter}{target_row}: '{text}'")

    # Verifikasi
    verify = sheets_api.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=cell,
    ).execute()
    value = verify.get("values", [[""]])[0][0]
    print(f"  Verifikasi baca {col_letter}{target_row}: '{value}'")

    print(f"\n{'=' * 55}")
    print("  Selesai!")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    main()
