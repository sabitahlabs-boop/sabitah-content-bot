"""
Create CA-005 — Ci Angel emotional POV keluh kesah as new comer agen property
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from googleapiclient.discovery import build
from telegram_bot import (
    read_sheet_info, get_header_index, get_sheets_service, col_to_letter,
    get_google_credentials, SPREADSHEET_ID, SHEET_NAME,
)

SCRIPT_CONTENT = """🎬 REELS SCRIPT – CA-005 (Ci Angel)
Angle: Emotional POV — keluh kesah new comer di dunia property

🎯 HOOK (0–5 detik)
Visual: Ci Angel duduk sendirian, muka capek, pegang HP, helaan napas pelan
Speaker: "Guys… ini cerita yang jarang banget Ci Angel share."
(pause, senyum pahit) "Jadi agen property baru itu… ga semudah yang keliatan."

🎯 STORY 1 — FAKE BUYER (5–22 detik)
Visual: close-up HP, scroll chat WA yang penuh pertanyaan detail
Speaker: "Kemaren ada yang DM ke Ci Angel…"
"'Ci, yang di BSD itu sertifikatnya apa? Boleh minta alamat lengkap plus ukuran kavling?'"
(beat) "Ci Angel semangat banget balesin…"
"Siapa tau ketemu client serius kan guys."
(pause, senyum pahit) "Ternyata… dia itu agen property juga."
"Cuma lagi cari data listingan gratis buat dia tawarin ke client dia sendiri."

🎯 STORY 2 — BYPASS KE OWNER (22–38 detik)
Visual: foto rumah, transisi ke ekspresi kecewa, close-up mata yang sedih
Speaker: "Yang lebih sakit lagi guys…"
"Ada client yang udah Ci Angel temenin survey 3 kali."
"Ci Angel jelasin area-nya, plus minusnya…"
"Sampe harga pasaran wajarnya berapa, tanpa ditutup-tutupi."
(beat) "Terus tiba-tiba… dia ilang kontak."
"Seminggu kemudian Ci Angel denger dari temen…"
"Dia deal langsung ke owner rumahnya."
(pause pelan) "Biar ga bayar komisi Ci Angel."

🎯 REFLECTION (38–52 detik)
Visual: Ci Angel eye contact, tone lebih tenang tapi jujur
Speaker: "Guys… Ci Angel baru mulai di dunia ini."
"Dan jujur aja… ini capek."
(beat) "Bukan capek kerjanya."
"Tapi capek ngeliat effort orang dianggap gratis."
(pause) "Ci Angel kira jadi agen property tuh cuma soal jualan rumah."
"Ternyata… soal ketahanan hati juga."

🎯 CLOSING (52–62 detik)
Visual: Ci Angel tersenyum pelan, lebih tegar, sunlight soft
Speaker: "Tapi ya guys…"
"Ci Angel masih di sini."
"Masih percaya… masih banyak orang yang bisa hargain kerja orang lain."
(beat, senyum kecil) "Dan buat yang kebetulan baca ini…"
"Kalau pernah di posisi yang sama… Ci Angel ngerti banget perasaan kamu."
(pause) "Kita sama-sama jalan pelan-pelan ya."

🎯 END FRAME (62–65 detik)
Visual: Ci Angel profile + soft background properti
Text overlay: "Ci Angel — Property Partner Jabodetabek"
"""


def main():
    print("=" * 60)
    print("CREATE CA-005 — Ci Angel Emotional POV")
    print("=" * 60)

    creds = get_google_credentials()
    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)
    sheets_service = get_sheets_service()

    # Metadata
    cid = "CA-005"
    brand = "Ci Angel"
    ctype = "Reel"
    topic = "Keluh Kesah Agen Property Baru — Fake Buyer & Di-bypass ke Owner"
    hook = "Ci Angel baru di dunia property… dan ini cerita yang jarang di-share"
    brief = "POV emosional Ci Angel as new comer. Cerita soal (1) fake customer yang ternyata agen lain cari data listingan, (2) client yang di-bypass langsung ke owner untuk skip komisi. Tone vulnerable tapi tidak lebay, hopeful closing."

    # Step 1: Create Google Doc
    print("\n[1/3] Creating Google Doc...")
    doc_title = f"[{cid}] {brand} - {hook[:60]}"
    doc = docs_service.documents().create(body={"title": doc_title}).execute()
    doc_id = doc["documentId"]

    sep = "=" * 40
    full_text = (
        f"Content ID: {cid}\n"
        f"Brand: {brand}\n"
        f"Tipe: {ctype}\n"
        f"Topik: {topic}\n"
        f"Hook: {hook}\n"
        f"{sep}\n\n"
        f"{SCRIPT_CONTENT}\n"
    )

    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{
            "insertText": {"location": {"index": 1}, "text": full_text}
        }]},
    ).execute()

    # Make shareable
    drive_service.permissions().create(
        fileId=doc_id,
        body={"type": "anyone", "role": "writer"},
    ).execute()

    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"  Doc created: {doc_url}")

    # Step 2: Add row to Master Tracker
    print("\n[2/3] Adding row to Master Tracker...")
    headers, data, _ = read_sheet_info()
    col_map = get_header_index(headers)

    # Build row with all fields
    new_row = [""] * len(headers)

    def set_field(field, value):
        idx = col_map.get(field)
        if idx is not None:
            new_row[idx] = value

    # Next post date: 3 days from today
    post_date = (datetime.now() + timedelta(days=3)).strftime("%d %b")

    set_field("brand", brand)
    set_field("content_id", cid)
    set_field("date", post_date)
    set_field("content_type", ctype)
    set_field("topik", topic)
    set_field("hook", hook)
    set_field("brief", brief)
    set_field("script_status", "Need to Review")
    set_field("script_owner", "Dimas")
    set_field("script_link", doc_url)
    set_field("production_status", "Not Started")
    set_field("asset_status", "Missing")
    set_field("editing_status", "Not Started")
    set_field("approval_status", "Pending")
    set_field("caption_status", "Not Started")
    set_field("posting_status", "Not Started")
    set_field("priority", "High")  # Emotional content = important
    set_field("difficulty", "Medium")
    set_field("effort", "Medium")
    set_field("visual_status", "Skip - Video Manual")  # Reel needs shooting
    set_field("notes", "Emotional POV content - new comer keluh kesah")

    # Append row
    sheets_service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{SHEET_NAME}'!A:A",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [new_row]},
    ).execute()
    print(f"  Row added: {cid} | {brand} | {topic[:50]}")

    # Step 3: Refresh My Tasks
    print("\n[3/3] Refreshing My Tasks sheet...")
    from telegram_bot import rebuild_my_tasks_sheet
    result = rebuild_my_tasks_sheet()
    print(f"  My Tasks refreshed: {result}")

    print()
    print("=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"Content ID: {cid}")
    print(f"Doc URL: {doc_url}")
    print(f"Status: Need to Review")
    print(f"Post date: {post_date}")
    print(f"Priority: High")


if __name__ == "__main__":
    main()
