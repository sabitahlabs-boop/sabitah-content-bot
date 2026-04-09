import sys
import io
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import anthropic

# ============================================================
# KONFIGURASI
# ============================================================
SPREADSHEET_ID = "13_BnnBjVLRcpJAiyieBqF7tnuoRZ7ij7fs0u8Z9Hd1Y"
OAUTH_CREDENTIALS_FILE = "oauth_credentials.json"
TOKEN_FILE = "token.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Load API key dari .env
def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

load_env()


# ============================================================
# AUTENTIKASI GOOGLE
# ============================================================
def authenticate_google():
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


# ============================================================
# GENERATE SCRIPT VIA CLAUDE API
# ============================================================
def generate_script_with_claude(client, brand, topik, content_type, hook):
    """Kirim prompt ke Claude API, return script carousel 7 slide."""

    prompt = f"""Kamu adalah content strategist untuk brand "{brand}" di Indonesia.

Buatkan script carousel Instagram 7 slide untuk konten berikut:

- Brand: {brand}
- Topik: {topik}
- Tipe konten: {content_type}
- Hook/opening: {hook}

ATURAN:
1. Slide 1 = Hook/Cover — gunakan hook yang sudah diberikan, tambahkan arahan visual
2. Slide 2-6 = Konten inti — edukatif, storytelling, ada insight yang actionable
3. Slide 7 = CTA — ajak save, share, follow, atau comment
4. Bahasa Indonesia casual, kayak ngobrol sama teman
5. Tone: edukatif tapi santai, cocok untuk entrepreneur muda Indonesia
6. Setiap slide tulis: judul slide, isi teks untuk di-desain, dan catatan visual singkat
7. Jangan pakai emoji berlebihan, maksimal 1 per slide

Format output:
SLIDE 1 (COVER):
[isi]

SLIDE 2:
[isi]

... sampai SLIDE 7 (CTA)"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60)
    print("  CAROUSEL SCRIPT GENERATOR (Claude AI)")
    print("  Target: 2 baris pertama 'Not Started'")
    print("=" * 60)

    # Cek API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("\n  [ERROR] ANTHROPIC_API_KEY tidak ditemukan di .env!")
        return

    print(f"\n  API Key: ...{api_key[-8:]}")

    # Init Claude client
    client = anthropic.Anthropic(api_key=api_key)

    # Auth Google
    creds = authenticate_google()
    if not creds:
        return

    service = build("sheets", "v4", credentials=creds)
    sheets_api = service.spreadsheets()
    sheet_name = "Master Tracker"

    # Baca semua data
    result = sheets_api.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{sheet_name}'",
    ).execute()
    rows = result.get("values", [])

    if len(rows) < 3:
        print("  [ERROR] Sheet tidak punya cukup data.")
        return

    # Baris 1 = kategori, baris 2 = header
    headers = rows[1]
    headers_lower = [h.strip().lower().replace("\n", " ") for h in headers]

    # Cari index kolom
    col_map = {}
    needed = {
        "brand name": "brand",
        "content topic / title": "topik",
        "content type": "content_type",
        "hook": "hook",
        "script status": "script_status",
        "script notes": "script_notes",
    }
    for idx, h in enumerate(headers_lower):
        if h in needed:
            col_map[needed[h]] = idx

    missing = [k for k, v in needed.items() if v not in col_map]
    if missing:
        print(f"  [ERROR] Kolom tidak ditemukan: {missing}")
        return

    print(f"\n  Kolom ditemukan:")
    for label, key in needed.items():
        print(f"    {label:<25} : kolom {chr(65 + col_map[key])}")

    # Cari 2 baris pertama "not started"
    targets = []
    for i, row in enumerate(rows[2:], start=3):
        status = row[col_map["script_status"]].strip().lower() if len(row) > col_map["script_status"] else ""
        if status == "not started":
            brand = row[col_map["brand"]].strip() if len(row) > col_map["brand"] else ""
            topik = row[col_map["topik"]].strip() if len(row) > col_map["topik"] else ""
            content_type = row[col_map["content_type"]].strip() if len(row) > col_map["content_type"] else ""
            hook = row[col_map["hook"]].strip() if len(row) > col_map["hook"] else ""
            content_id = row[1].strip() if len(row) > 1 else "?"
            if topik:
                targets.append({
                    "row_num": i,
                    "content_id": content_id,
                    "brand": brand,
                    "topik": topik,
                    "content_type": content_type,
                    "hook": hook or topik,
                })
            if len(targets) == 2:
                break

    if not targets:
        print("\n  Tidak ada baris dengan Script Status 'Not Started'.")
        return

    print(f"\n  Ditemukan {len(targets)} baris untuk diproses:\n")

    col_notes_letter = chr(65 + col_map["script_notes"])
    col_status_letter = chr(65 + col_map["script_status"])
    update_data = []

    for idx, t in enumerate(targets, 1):
        print(f"  [{idx}/{len(targets)}] Baris {t['row_num']} — {t['content_id']}")
        print(f"       Brand : {t['brand']}")
        print(f"       Topik : {t['topik'][:70]}")
        print(f"       Type  : {t['content_type']}")
        print(f"       Hook  : {t['hook'][:70]}")
        print(f"       Mengirim ke Claude API...", end=" ", flush=True)

        script = generate_script_with_claude(
            client, t["brand"], t["topik"], t["content_type"], t["hook"]
        )

        print(f"OK ({len(script)} chars)")
        print(f"       Preview: {script[:100]}...")
        print()

        update_data.append({
            "range": f"'{sheet_name}'!{col_notes_letter}{t['row_num']}",
            "values": [[script]],
        })
        update_data.append({
            "range": f"'{sheet_name}'!{col_status_letter}{t['row_num']}",
            "values": [["Done"]],
        })

    # Batch update ke Google Sheet
    sheets_api.values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"valueInputOption": "RAW", "data": update_data},
    ).execute()

    print(f"  {'─' * 56}")
    print(f"  {len(targets)} baris berhasil diupdate:")
    print(f"    - Script dari Claude API ditulis ke kolom {col_notes_letter} (Script Notes)")
    print(f"    - Script Status diubah ke 'Done'")
    print(f"  {'─' * 56}")

    # Verifikasi
    print(f"\n  Verifikasi:")
    for t in targets:
        v = sheets_api.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{sheet_name}'!{col_status_letter}{t['row_num']}",
        ).execute()
        status = v.get("values", [[""]])[0][0]
        print(f"    Baris {t['row_num']} ({t['content_id']}): Script Status = '{status}'")

    print(f"\n{'=' * 60}")
    print("  Selesai!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
