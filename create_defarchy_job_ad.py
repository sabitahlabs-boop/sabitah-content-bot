"""
Create Defarchy recruitment Reels script + add to Master Tracker.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from googleapiclient.discovery import build
from telegram_bot import (
    read_sheet_info, get_header_index, get_sheets_service,
    get_google_credentials, SPREADSHEET_ID, SHEET_NAME,
)

SCRIPT = """🎬 REELS SCRIPT – DF-XXX (Defarchy)
Angle: Recruitment ad — direct, honest, Defarchy voice. Gak pakai fear-mongering, tapi juga gak lebay.

🎯 HOOK (0–5 detik)
Visual: [showroom Defarchy, tim kompak, sepeda listrik berjejer rapi]
Speaker: "Lu cowok, umur 22 ke bawah, belum punya pengalaman kerja?"
(pause, senyum dikit) "Justru itu yang kami cari."

🎯 OPENING (5–15 detik)
Visual: [cut ke tim Defarchy di bengkel, aktivitas harian, smile]
Speaker: "Defarchy lagi buka lowongan."
"Buat lu yang baru lulus… atau lagi cari kerja pertama."
"Kami gak minta lu jago dari awal. Kami gak minta pengalaman."
(beat) "Yang kami minta cuma dua hal."

🎯 REQUIREMENTS (15–28 detik)
Visual: [close up wajah, lalu potongan aktivitas teknisi belajar & kerja]
Speaker: "Satu… lu mau belajar."
"Dua… lu punya daya juang yang tinggi."
(pause) "Itu aja."
"Karena skill bisa diajarin. Tools bisa kami sediakan."
"Tapi semangat dan mau belajar… itu dari diri lu sendiri."

🎯 FACILITIES (28–45 detik)
Visual: [showroom, suasana makan bareng tim, mess yang rapi & bersih]
Speaker: "Dan Defarchy gak main-main sama tim kami."
"Lu dapet gaji pokok."
(beat) "1 bulan pertama… makan lu kami tanggung."
"Dan lu dapet mess buat tempat tinggal."
(pause) "Jadi lu fokus belajar… urusan yang lainnya, kami yang handle."

🎯 CTA (45–58 detik)
Visual: [logo Defarchy + info kontak/DM di layar]
Speaker: "Kalau lu ngerasa ini lu…"
"DM Defarchy sekarang."
"Kirim data diri lu, kami respond."
(beat, senyum) "Jangan cuma mikir… ambil langkahnya."

🎯 END FRAME (58–60 detik)
Visual: [logo Defarchy + tagline]
Text overlay: "Defarchy — Beli nyaman, service aman. Dan sekarang, kerja pun nyaman."

---
CAPTION:
🚨 DEFARCHY LAGI BUKA LOWONGAN! 🚨

Buat lu cowok umur 22 ke bawah yang lagi cari kerja pertama… ini kesempatan lu.

REQUIREMENTS:
✓ Pria, max 22 tahun
✓ Gak perlu pengalaman
✓ Yang penting MAU BELAJAR
✓ Punya daya juang tinggi

FASILITAS:
💰 Gaji pokok
🍱 Bonus makan 1 bulan pertama (full-covered)
🏠 Mess disediakan

Kami gak cari yang udah jago. Kami cari yang mau tumbuh bareng Defarchy.

DM sekarang untuk apply, atau langsung datang ke showroom kami. 🔥

#Defarchy #LowonganKerja #KarirDefarchy #SepedaListrik #LowonganCowok
"""


def get_next_df_cid():
    headers, data, _ = read_sheet_info()
    col_map = get_header_index(headers)
    cid_col = col_map.get("content_id", 1)
    max_num = 0
    for row in data:
        if cid_col >= len(row):
            continue
        cid = row[cid_col].strip()
        if cid.startswith("DF-"):
            try:
                num = int(cid[3:])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return f"DF-{max_num + 1:03d}"


def main():
    print("=" * 60)
    print("CREATE DEFARCHY RECRUITMENT AD")
    print("=" * 60)

    creds = get_google_credentials()
    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)
    sheets_service = get_sheets_service()

    cid = get_next_df_cid()
    brand = "Defarchy"
    ctype = "Reel"
    topic = "Lowongan Kerja Defarchy — Cowok Max 22 Tahun, Mau Belajar & Daya Juang Tinggi"
    hook = "Lu cowok, umur 22 ke bawah, belum punya pengalaman kerja? Justru itu yang kami cari."
    brief = "Recruitment ad reel. Target: cowok max 22 tahun, no experience. Emphasize: mau belajar + daya juang. Facilities: gaji pokok, makan 1 bulan pertama, mess. Tone: direct honest Defarchy voice, gak lebay."

    # Create Google Doc
    print(f"\n[1/3] Creating Google Doc ({cid})...")
    doc_title = f"[{cid}] {brand} - Lowongan Kerja Cowok Max 22 Tahun"
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
        f"{SCRIPT}\n"
    )

    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{
            "insertText": {"location": {"index": 1}, "text": full_text}
        }]},
    ).execute()

    # Shareable
    drive_service.permissions().create(
        fileId=doc_id,
        body={"type": "anyone", "role": "writer"},
    ).execute()

    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"  Doc: {doc_url}")

    # Add to Master Tracker
    print("\n[2/3] Adding to Master Tracker...")
    headers, data, _ = read_sheet_info()
    col_map = get_header_index(headers)
    new_row = [""] * len(headers)

    def set_field(field, value):
        idx = col_map.get(field)
        if idx is not None:
            new_row[idx] = value

    # Post date: 2 days from now (urgent - recruitment)
    post_date = (datetime.now() + timedelta(days=2)).strftime("%d %b")

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
    set_field("priority", "High")
    set_field("difficulty", "Easy")
    set_field("effort", "Medium")
    set_field("visual_status", "Skip - Video Manual")
    set_field("notes", "Recruitment ad - iklan lowongan kerja")

    sheets_service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{SHEET_NAME}'!A:A",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [new_row]},
    ).execute()
    print(f"  Row added: {cid}")

    # Refresh My Tasks + Production Tasks
    print("\n[3/3] Refreshing task sheets...")
    from telegram_bot import rebuild_my_tasks_sheet, rebuild_production_tasks_sheet
    r1 = rebuild_my_tasks_sheet()
    r2 = rebuild_production_tasks_sheet()
    print(f"  My Tasks: {r1}")
    print(f"  Production Tasks: {r2}")

    print()
    print("=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"Content ID: {cid}")
    print(f"Doc URL: {doc_url}")
    print(f"Post date: {post_date}")


if __name__ == "__main__":
    main()
