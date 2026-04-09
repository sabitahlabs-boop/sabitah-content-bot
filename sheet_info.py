import sys
import io
import os
from collections import Counter
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
except ImportError:
    print("Library belum terinstall. Jalankan:")
    print("  pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
    sys.exit(1)

# ============================================================
# KONFIGURASI
# ============================================================
SPREADSHEET_ID = "13_BnnBjVLRcpJAiyieBqF7tnuoRZ7ij7fs0u8Z9Hd1Y"
OAUTH_CREDENTIALS_FILE = "oauth_credentials.json"
TOKEN_FILE = "token.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


# ============================================================
# AUTENTIKASI
# ============================================================
def authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Token expired, refreshing...")
            creds.refresh(Request())
        else:
            if not os.path.exists(OAUTH_CREDENTIALS_FILE):
                print(f"\n[ERROR] File '{OAUTH_CREDENTIALS_FILE}' tidak ditemukan!")
                return None
            print("Membuka browser untuk login Google...")
            flow = InstalledAppFlow.from_client_secrets_file(
                OAUTH_CREDENTIALS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
        print("Login berhasil! Token tersimpan.\n")

    return creds


def get_cell(row, col_idx):
    """Ambil nilai cell dengan aman, return string kosong jika out of range."""
    if col_idx < len(row):
        return row[col_idx].strip()
    return ""


def print_status_table(col_name, rows, col_idx, out):
    """Hitung dan tampilkan distribusi status untuk satu kolom."""
    values = []
    for row in rows:
        val = get_cell(row, col_idx)
        values.append(val.lower() if val else "(kosong)")

    counter = Counter(values)
    total = len(values)

    out(f"\n  +-- {col_name}")
    out(f"  |  {'Status':<25} {'Jumlah':>6} {'Persen':>7}  Bar")
    out(f"  |  {'─' * 50}")
    for status, count in counter.most_common():
        pct = count / total * 100
        bar = "█" * int(pct / 5)
        out(f"  |  {status:<25} {count:>6} {pct:>6.1f}%  {bar}")
    out(f"  |  {'─' * 50}")
    out(f"  |  {'TOTAL':<25} {total:>6}")
    out(f"  +{'─' * 52}")


# ============================================================
# MAIN
# ============================================================
def main():
    # Siapkan output: print ke terminal + kumpulkan ke buffer untuk file
    lines = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def out(text=""):
        print(text)
        lines.append(text)

    out("=" * 60)
    out("   GOOGLE SHEET INFO READER")
    out(f"   Generated: {timestamp}")
    out("=" * 60)

    # 1. Autentikasi
    creds = authenticate()
    if not creds:
        return

    service = build("sheets", "v4", credentials=creds)
    sheets_api = service.spreadsheets()

    # 2. Ambil metadata spreadsheet
    try:
        spreadsheet = sheets_api.get(spreadsheetId=SPREADSHEET_ID).execute()
    except Exception as e:
        out(f"\n[ERROR] Gagal membaca spreadsheet: {e}")
        return

    title = spreadsheet["properties"]["title"]
    sheets = spreadsheet["sheets"]

    out(f"\nSpreadsheet : {title}")
    out(f"ID          : {SPREADSHEET_ID}")
    out(f"Total sheet : {len(sheets)}")

    # 3. Untuk setiap sheet, baca jumlah baris dan header
    for i, sheet in enumerate(sheets, 1):
        sheet_name = sheet["properties"]["title"]

        out(f"\n{'─' * 60}")
        out(f"  Sheet #{i}: {sheet_name}")
        out(f"{'─' * 60}")

        # Baca semua data dari sheet ini
        try:
            result = (
                sheets_api.values()
                .get(
                    spreadsheetId=SPREADSHEET_ID,
                    range=f"'{sheet_name}'",
                )
                .execute()
            )
        except Exception as e:
            out(f"  [ERROR] Gagal membaca: {e}")
            continue

        rows = result.get("values", [])
        total_rows = len(rows)

        if total_rows == 0:
            out("  (Sheet kosong)")
            continue

        # Master Tracker punya 2 baris header (baris 1 = kategori, baris 2 = kolom)
        if sheet_name == "Master Tracker" and total_rows >= 2:
            category_row = rows[0]
            headers = rows[1]
            data_rows = rows[2:]
            header_count = 2
        else:
            headers = rows[0]
            data_rows = rows[1:]
            header_count = 1

        out(f"  Total baris  : {total_rows} ({len(data_rows)} data + {header_count} header)")
        out(f"  Jumlah kolom : {len(headers)}")
        out(f"  Header kolom :")
        for j, col in enumerate(headers, 1):
            col_display = col.replace("\n", " ") if col else "(kosong)"
            out(f"    {j}. {col_display}")

        # Untuk sheet "Master Tracker", cari semua kolom yang mengandung "status"
        if sheet_name == "Master Tracker":
            status_cols = []
            for col_idx, header in enumerate(headers):
                if "status" in header.strip().lower():
                    status_cols.append((col_idx, header.replace("\n", " ")))

            if not status_cols:
                out(f"\n  [INFO] Tidak ditemukan kolom status.")
            else:
                out(f"\n  Ditemukan {len(status_cols)} kolom status:")
                for col_idx, col_name in status_cols:
                    print_status_table(col_name, data_rows, col_idx, out)

    out(f"\n{'=' * 60}")
    out("  Selesai!")
    out(f"{'=' * 60}")

    # Simpan ke report.txt
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n  >> Report disimpan ke: {report_path}")


if __name__ == "__main__":
    main()
