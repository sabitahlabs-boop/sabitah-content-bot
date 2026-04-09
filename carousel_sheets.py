import sys
import io
import os
import random

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
OAUTH_CREDENTIALS_FILE = "oauth_credentials.json"
TOKEN_FILE = "token.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


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


# ============================================================
# CAROUSEL GENERATOR (dengan topik + angle)
# ============================================================
def generate_carousel(topik, angle):
    """Generate 1 ide carousel 7 slide berdasarkan topik dan angle."""

    templates = [
        [
            f"{angle}: {topik} yang Wajib Kamu Tahu (Cover)",
            f"Kenapa {topik} penting? Karena {angle} bisa mengubah cara kamu melihat hal ini",
            f"Fakta 1: Kebanyakan orang salah paham soal {topik} dari sudut {angle}",
            f"Fakta 2: Data menunjukkan {angle} adalah kunci sukses di {topik}",
            f"Fakta 3: Cara praktis menerapkan {angle} dalam {topik} sehari-hari",
            f"Studi kasus: Mereka yang berhasil di {topik} dengan pendekatan {angle}",
            f"Save & share ke teman yang butuh insight tentang {topik}! (CTA)",
        ],
        [
            f"Stop! Jangan Mulai {topik} Sebelum Baca Ini (Cover)",
            f"Masalah utama: Banyak yang gagal di {topik} karena mengabaikan {angle}",
            f"Langkah 1: Pahami dasar {angle} sebelum terjun ke {topik}",
            f"Langkah 2: Buat rencana {topik} dengan framework {angle}",
            f"Langkah 3: Eksekusi {topik} secara konsisten dengan prinsip {angle}",
            f"Langkah 4: Evaluasi & optimasi {topik} berdasarkan {angle}",
            f"Mau panduan lengkapnya? Follow & nyalakan notifikasi! (CTA)",
        ],
        [
            f"{topik} x {angle} = Kombinasi Powerful! (Cover)",
            f"Apa hubungan {topik} dengan {angle}? Lebih erat dari yang kamu kira",
            f"Kesalahan #1: Fokus {topik} tanpa mempertimbangkan {angle}",
            f"Kesalahan #2: Menganggap {angle} tidak relevan dengan {topik}",
            f"Solusi: Framework sederhana menggabungkan {topik} dan {angle}",
            f"Hasil nyata: Apa yang terjadi setelah menerapkan {angle} di {topik}",
            f"Setuju? Comment pendapat kamu! Share ke yang butuh (CTA)",
        ],
        [
            f"Rahasia {topik} yang Jarang Dibahas: Perspektif {angle} (Cover)",
            f"Kebanyakan konten {topik} hanya bahas permukaan. Ini yang lebih dalam",
            f"Sudut pandang {angle}: Mengapa {topik} bukan soal teknis saja",
            f"Insight 1: {angle} mengajarkan kita tentang mindset di {topik}",
            f"Insight 2: Pola sukses {topik} selalu melibatkan aspek {angle}",
            f"Action plan: 3 hal yang bisa kamu lakukan hari ini",
            f"Bookmark sekarang! Tag teman yang harus baca ini (CTA)",
        ],
        [
            f"5 Alasan {angle} Penting untuk {topik} (Cover)",
            f"Alasan 1: {angle} membantu kamu memahami akar masalah di {topik}",
            f"Alasan 2: Tanpa {angle}, strategi {topik} kamu tidak akan bertahan lama",
            f"Alasan 3: {angle} membedakan pemula dan expert di {topik}",
            f"Alasan 4: Tren terbaru {topik} semakin mengarah ke {angle}",
            f"Alasan 5: Investasi waktu belajar {angle} = ROI besar di {topik}",
            f"Mana alasan yang paling relate? Tulis di komentar! (CTA)",
        ],
        [
            f"Dari Nol ke Pro: {topik} dengan Pendekatan {angle} (Cover)",
            f"Level 1 (Pemula): Kenali dasar {topik} dan hubungannya dengan {angle}",
            f"Level 2 (Menengah): Terapkan prinsip {angle} dalam praktik {topik}",
            f"Level 3 (Mahir): Kombinasikan multiple strategi {angle} di {topik}",
            f"Level 4 (Expert): Ciptakan pendekatan unik {topik} berbasis {angle}",
            f"Shortcut: Resource gratis terbaik untuk belajar {topik} + {angle}",
            f"Kamu di level berapa? Comment di bawah! Follow untuk next part (CTA)",
        ],
        [
            f"Checklist {topik} 2026: Versi {angle} (Cover)",
            f"Checklist 1: Audit posisi kamu sekarang di {topik}",
            f"Checklist 2: Identifikasi gap antara {topik} kamu dan standar {angle}",
            f"Checklist 3: Buat roadmap {topik} dengan milestone {angle}",
            f"Checklist 4: Cari mentor/komunitas yang paham {topik} + {angle}",
            f"Checklist 5: Review & adjust setiap bulan",
            f"Screenshot checklist ini! Share ke partner belajar kamu (CTA)",
        ],
    ]

    random.shuffle(templates)
    slides = templates[0]

    # Format: Slide 1 | Slide 2 | ... | Slide 7
    return " | ".join(f"Slide {i+1}: {s}" for i, s in enumerate(slides))


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60)
    print("   CAROUSEL GENERATOR + GOOGLE SHEETS")
    print("   Filter: status = 'draft'")
    print("=" * 60)

    # 1. Autentikasi
    creds = authenticate()
    if not creds:
        input("\nTekan Enter untuk keluar...")
        return

    service = build("sheets", "v4", credentials=creds)
    sheets_api = service.spreadsheets()

    # 2. Baca metadata spreadsheet
    try:
        spreadsheet = sheets_api.get(spreadsheetId=SPREADSHEET_ID).execute()
    except Exception as e:
        print(f"\n[ERROR] Gagal membaca spreadsheet: {e}")
        input("\nTekan Enter untuk keluar...")
        return

    first_sheet = spreadsheet["sheets"][0]["properties"]["title"]
    print(f"\nSheet: {first_sheet}")

    # 3. Baca semua data (header + isi)
    result = (
        sheets_api.values()
        .get(spreadsheetId=SPREADSHEET_ID, range=f"'{first_sheet}'")
        .execute()
    )
    rows = result.get("values", [])

    if len(rows) <= 1:
        print("\n[ERROR] Sheet kosong atau hanya ada header.")
        input("\nTekan Enter untuk keluar...")
        return

    # 4. Cari index kolom berdasarkan header
    headers = [h.strip().lower() for h in rows[0]]
    print(f"Header ditemukan: {rows[0]}")

    def find_col(name):
        try:
            return headers.index(name.lower())
        except ValueError:
            return -1

    col_topik = find_col("topik")
    col_angle = find_col("angle")
    col_status = find_col("status")
    col_hasil = find_col("hasil_carousel")

    # Validasi kolom wajib
    missing = []
    if col_topik == -1:
        missing.append("topik")
    if col_angle == -1:
        missing.append("angle")
    if col_status == -1:
        missing.append("status")

    if missing:
        print(f"\n[ERROR] Kolom tidak ditemukan: {', '.join(missing)}")
        print(f"Header yang ada: {rows[0]}")
        input("\nTekan Enter untuk keluar...")
        return

    # Jika kolom hasil_carousel belum ada, tambahkan di header
    if col_hasil == -1:
        col_hasil = len(rows[0])
        # Tulis header baru
        col_letter = chr(ord("A") + col_hasil)
        sheets_api.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{first_sheet}'!{col_letter}1",
            valueInputOption="RAW",
            body={"values": [["hasil_carousel"]]},
        ).execute()
        print(f"Kolom 'hasil_carousel' ditambahkan di kolom {col_letter}")

    # 5. Cari baris dengan status = "draft"
    draft_rows = []
    for i, row in enumerate(rows[1:], start=2):  # baris 2 dst (1-indexed di Sheet)
        # Pastikan row cukup panjang
        status = row[col_status].strip().lower() if len(row) > col_status else ""
        if status == "draft":
            topik = row[col_topik].strip() if len(row) > col_topik else ""
            angle = row[col_angle].strip() if len(row) > col_angle else ""
            if topik and angle:
                draft_rows.append({"row_num": i, "topik": topik, "angle": angle})

    if not draft_rows:
        print("\nTidak ada baris dengan status 'draft'.")
        input("\nTekan Enter untuk keluar...")
        return

    print(f"\nDitemukan {len(draft_rows)} baris dengan status 'draft'\n")

    # 6. Generate carousel & update sheet per baris
    col_hasil_letter = chr(ord("A") + col_hasil)
    col_status_letter = chr(ord("A") + col_status)

    # Kumpulkan semua update dalam batch
    update_data = []
    for item in draft_rows:
        row_num = item["row_num"]
        topik = item["topik"]
        angle = item["angle"]

        carousel_text = generate_carousel(topik, angle)

        # Update hasil_carousel
        update_data.append({
            "range": f"'{first_sheet}'!{col_hasil_letter}{row_num}",
            "values": [[carousel_text]],
        })
        # Update status -> done
        update_data.append({
            "range": f"'{first_sheet}'!{col_status_letter}{row_num}",
            "values": [["done"]],
        })

        print(f"  [{draft_rows.index(item)+1}/{len(draft_rows)}] Baris {row_num}")
        print(f"       Topik: {topik}")
        print(f"       Angle: {angle}")
        print(f"       Carousel: {carousel_text[:80]}...")
        print()

    # 7. Batch update ke Google Sheet
    sheets_api.values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={
            "valueInputOption": "RAW",
            "data": update_data,
        },
    ).execute()

    print(f"{'=' * 60}")
    print(f"  SELESAI!")
    print(f"  {len(draft_rows)} baris diproses:")
    print(f"  - Carousel ditulis ke kolom '{col_hasil_letter}' (hasil_carousel)")
    print(f"  - Status diupdate dari 'draft' -> 'done'")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
    input("\nTekan Enter untuk keluar...")
