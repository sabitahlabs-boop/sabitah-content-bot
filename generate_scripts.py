import sys
import io
import os
import random

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


def generate_carousel_script(topik, hook):
    """Generate script carousel 7 slide dalam bahasa Indonesia casual."""

    # Bersihkan hook dari kutip berlebih
    hook_clean = hook.strip().strip('"').strip("'")

    templates = [
        (
            f'[COVER] "{hook_clean}"\n'
            f"Visual: Teks bold di atas background aesthetic, ekspresi relatable.\n"
            f"Musik: Lo-fi / trending audio yang cocok dengan mood.",

            f"[SLIDE 2] Kenapa {topik} itu penting banget?\n"
            f"Banyak orang ngerasa ini sepele, padahal dampaknya gede ke kehidupan sehari-hari. "
            f"Coba deh pikir, kapan terakhir kali kamu beneran take action soal ini?",

            f"[SLIDE 3] Masalah utama yang sering terjadi\n"
            f"Kebanyakan orang gagal di {topik} karena:\n"
            f"- Overthinking, kebanyakan mikir tapi nggak mulai-mulai\n"
            f"- Nggak punya framework yang jelas\n"
            f"- Terlalu dengerin opini orang yang belum pernah ngalamin",

            f"[SLIDE 4] Cara simpel buat mulai sekarang\n"
            f"Step 1: Tentuin dulu tujuan kamu — mau ngapain dengan {topik}?\n"
            f"Step 2: Mulai dari yang kecil, nggak perlu sempurna\n"
            f"Step 3: Konsisten 15 menit/hari, itu udah lebih dari cukup",

            f"[SLIDE 5] Mindset yang perlu kamu ubah\n"
            f"Stop nunggu 'waktu yang tepat'. Nggak ada waktu yang sempurna.\n"
            f"Yang ada cuma: sekarang atau nanti-nanti (dan nanti biasanya = nggak pernah).\n"
            f"Orang yang berhasil di {topik} bukan yang paling jago, tapi yang paling konsisten.",

            f"[SLIDE 6] Real talk: ini yang bakal kamu rasain\n"
            f"Kalau kamu beneran komit sama {topik}, dalam 30 hari kamu bakal:\n"
            f"- Ngerasa lebih pede karena udah punya progress nyata\n"
            f"- Punya clarity yang lebih jelas tentang arah kamu\n"
            f"- Bisa inspire orang lain yang masih stuck",

            f"[SLIDE 7 - CTA] Relate nggak sama konten ini?\n"
            f"Kalau iya, SAVE buat reminder & SHARE ke teman yang butuh.\n"
            f"Follow buat konten-konten seputar {topik} lainnya!\n"
            f"Comment: kamu di tahap mana sekarang? Yuk diskusi!"
        ),
        (
            f'[COVER] "{hook_clean}"\n'
            f"Visual: POV style, close-up wajah atau tangan, teks overlay gede.\n"
            f"Musik: Upbeat / catchy audio.",

            f"[SLIDE 2] Fakta yang jarang orang mau akui\n"
            f"{topik} itu bukan soal talent. Bukan soal privilege.\n"
            f"Ini soal siapa yang berani mulai duluan dan nggak berhenti di tengah jalan.",

            f"[SLIDE 3] 3 kesalahan fatal yang harus kamu hindari\n"
            f"1. Copy-paste cara orang lain tanpa adaptasi ke situasi kamu\n"
            f"2. Terlalu fokus teori, lupa praktik — {topik} butuh action\n"
            f"3. Bandingin progress kamu sama orang yang udah jalan 3 tahun",

            f"[SLIDE 4] Framework yang actually works\n"
            f"Ini bukan teori doang — ini udah dipake banyak orang:\n"
            f"- Observe: lihat apa yang udah berhasil di {topik}\n"
            f"- Adapt: sesuaiin sama gaya & situasi kamu\n"
            f"- Execute: jalanin minimal 2 minggu sebelum evaluasi",

            f"[SLIDE 5] Yang membedakan yang berhasil vs yang nyerah\n"
            f"Bukan skill. Bukan tools. Bukan modal.\n"
            f"Tapi kemampuan buat tetap jalan waktu hasilnya belum keliatan.\n"
            f"Di {topik}, 90% orang berhenti sebelum momentum datang.",

            f"[SLIDE 6] Action plan kamu mulai hari ini\n"
            f"Hari 1-7: Riset & tentuin fokus utama di {topik}\n"
            f"Hari 8-14: Eksekusi rencana pertama kamu, dokumentasiin hasilnya\n"
            f"Hari 15-30: Evaluasi, adjust, dan scale up yang udah jalan",

            f"[SLIDE 7 - CTA] Ini konten yang perlu kamu save!\n"
            f"Jangan cuma scroll — take action sekarang.\n"
            f"Tag teman yang lagi butuh motivasi soal {topik}.\n"
            f"Follow buat dapet tips actionable tiap minggu!"
        ),
        (
            f'[COVER] "{hook_clean}"\n'
            f"Visual: Split screen / before-after, warna kontras.\n"
            f"Musik: Dramatic intro lalu switch ke upbeat.",

            f"[SLIDE 2] Kenyataan pahit tentang {topik}\n"
            f"Nggak ada shortcut. Nggak ada 'rahasia' yang disembunyiin.\n"
            f"Yang ada cuma: effort yang konsisten + arah yang bener.\n"
            f"Dan kebanyakan orang gagal karena salah di keduanya.",

            f"[SLIDE 3] Apa yang sebenarnya kamu butuhkan\n"
            f"Bukan course mahal. Bukan mentor celebrity.\n"
            f"Kamu butuh:\n"
            f"- Kejelasan: apa goals kamu di {topik}?\n"
            f"- Sistem: rutinitas kecil yang bisa kamu jalanin tiap hari\n"
            f"- Komunitas: orang-orang yang supportif, bukan judgmental",

            f"[SLIDE 4] Strategi yang underrated banget\n"
            f"Belajar {topik} dari orang yang BARU berhasil, bukan yang udah di puncak.\n"
            f"Kenapa? Karena mereka masih inget struggle-nya, advice-nya lebih relevan.\n"
            f"Plus, gap antara kamu dan mereka nggak terlalu jauh — lebih achievable.",

            f"[SLIDE 5] Tanda kamu udah di jalur yang bener\n"
            f"- Kamu mulai ngerasa uncomfortable (growth zone!)\n"
            f"- Orang-orang mulai notice perubahan kamu\n"
            f"- Kamu punya progress kecil yang bisa diukur di {topik}\n"
            f"Kalau belum ngerasa ini, saatnya adjust strategi.",

            f"[SLIDE 6] Pelajaran yang worth it banget\n"
            f"Di {topik}, proses > hasil.\n"
            f"Setiap kegagalan itu feedback. Setiap progress kecil itu bukti.\n"
            f"Yang penting bukan seberapa cepat kamu sampai, tapi kamu nggak berhenti.",

            f"[SLIDE 7 - CTA] Konten ini free, tapi nilainya mahal.\n"
            f"SAVE sekarang sebelum tenggelam di feed.\n"
            f"SHARE ke orang yang lagi berjuang di {topik}.\n"
            f"Follow & nyalain notif buat konten kayak gini lainnya!"
        ),
    ]

    chosen = random.choice(templates)
    return "\n\n".join(chosen)


def main():
    print("=" * 60)
    print("  CAROUSEL SCRIPT GENERATOR — MASTER TRACKER")
    print("  Target: 3 baris pertama 'Not Started'")
    print("=" * 60)

    creds = authenticate()
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

    # Baris 1 = kategori, baris 2 = header, baris 3+ = data
    headers = rows[1]
    headers_lower = [h.strip().lower().replace("\n", " ") for h in headers]

    # Cari index kolom yang dibutuhkan
    col_map = {}
    needed = {
        "content topic / title": "topik",
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
    print(f"    Content Topic / Title : kolom {chr(65 + col_map['topik'])}")
    print(f"    Hook                  : kolom {chr(65 + col_map['hook'])}")
    print(f"    Script Status         : kolom {chr(65 + col_map['script_status'])}")
    print(f"    Script Notes          : kolom {chr(65 + col_map['script_notes'])}")

    # Cari 3 baris pertama dengan Script Status = "not started"
    targets = []
    for i, row in enumerate(rows[2:], start=3):
        status = row[col_map["script_status"]].strip().lower() if len(row) > col_map["script_status"] else ""
        if status == "not started":
            topik = row[col_map["topik"]].strip() if len(row) > col_map["topik"] else ""
            hook = row[col_map["hook"]].strip() if len(row) > col_map["hook"] else ""
            content_id = row[1].strip() if len(row) > 1 else "?"
            if topik:
                targets.append({
                    "row_num": i,
                    "content_id": content_id,
                    "topik": topik,
                    "hook": hook or topik,
                })
            if len(targets) == 3:
                break

    if not targets:
        print("\n  Tidak ada baris dengan Script Status 'Not Started'.")
        return

    print(f"\n  Ditemukan {len(targets)} baris untuk diproses:\n")

    # Generate script & kumpulkan batch update
    update_data = []
    col_notes_letter = chr(65 + col_map["script_notes"])
    col_status_letter = chr(65 + col_map["script_status"])

    for idx, t in enumerate(targets, 1):
        print(f"  [{idx}/{len(targets)}] Baris {t['row_num']} — {t['content_id']}")
        print(f"       Topik: {t['topik'][:70]}")
        print(f"       Hook : {t['hook'][:70]}")

        script = generate_carousel_script(t["topik"], t["hook"])

        # Update Script Notes
        update_data.append({
            "range": f"'{sheet_name}'!{col_notes_letter}{t['row_num']}",
            "values": [[script]],
        })
        # Update Script Status -> Done
        update_data.append({
            "range": f"'{sheet_name}'!{col_status_letter}{t['row_num']}",
            "values": [["Done"]],
        })

        print(f"       Script: {script[:80]}...")
        print()

    # Batch update
    sheets_api.values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"valueInputOption": "RAW", "data": update_data},
    ).execute()

    print(f"  {'─' * 56}")
    print(f"  {len(targets)} baris berhasil diupdate:")
    print(f"    - Script carousel ditulis ke kolom {col_notes_letter} (Script Notes)")
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
