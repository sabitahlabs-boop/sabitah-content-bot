"""
Insert 9 new Oma Hera Reels scripts (written manually by Dimas).
Set status to 'Ready for Client Review' directly (skip Need to Review).
Auto-assign next OH- CID starting from OH-020.
Create Google Doc per script, add row to Master Tracker, refresh client review doc.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from googleapiclient.discovery import build
from telegram_bot import (
    read_sheet_info, get_header_index, get_sheets_service,
    get_google_credentials, build_or_update_client_review_doc,
    SPREADSHEET_ID, SHEET_NAME,
)

# 9 scripts extracted from Dimas's HTML
SCRIPTS = [
    {
        "title": "Kebangkitan = Kemenangan dan Harapan Baru",
        "hook_visual": "tangan tua memegang lilin kecil yang menyala di ruangan gelap",
        "hook_tone": "Suara pelan Oma Hera membuka dengan pertanyaan reflektif",
        "monolog": """OMA HERA: "Cucu Oma… pernahkah kamu merasa hidup ini sudah sampai di ujung?"

"Merasa dosamu terlalu besar… lukamu terlalu dalam… dan tidak ada jalan keluar lagi?"

"Oma juga pernah merasa begitu…"

"Tapi ada satu hal yang mengubah segalanya. Yesus tidak hanya mati di kayu salib… Dia bangkit. Dia hidup."

"Rasul Paulus menulis dalam Surat 1 Korintus 15 ayat 17… 'Jika Kristus tidak dibangkitkan, maka sia-sialah kepercayaanmu.' Artinya… kebangkitan itu bukan cerita tambahan. Itu inti dari segalanya."

"Kalau Yesus bangkit… berarti kematian bukan akhir. Berarti tidak ada dosa yang terlalu besar untuk diampuni. Tidak ada kegelapan yang tidak bisa dikalahkan."

"Dan buat cucu Oma yang hari ini sedang di titik paling berat… ingat ini… selalu ada hari ketiga. Selalu ada kebangkitan setelah penderitaan."

"Hidup bisa dipulihkan. Luka bisa disembuhkan. Masa lalu tidak menentukan masa depanmu."

"Pegang itu erat-erat hari ini, cucu Oma."

"Tuhan memberkati cucu Oma.\"""",
        "caption": "Kadang hidup terasa gelap… tapi kebangkitan Yesus mengingatkan kita bahwa selalu ada hari ketiga. Selalu ada pemulihan yang Tuhan sediakan. Cucu Oma tidak pernah berjalan sendirian. ✝️🌿\n\n#OmaHera #Kebangkitan #HarapanBaru #ImanKristen #CucuOma",
        "source": "Sumber: Dokumen 'Arti Kebangkitan Yesus bagi Umat Kristen' — Poin 1 & 2",
    },
    {
        "title": "Kebangkitan Mengubah Cara Hidup",
        "hook_visual": "cahaya pagi masuk melalui jendela tua, menyinari meja kayu sederhana",
        "hook_tone": "Suara tenang Oma Hera dengan nada mengajak berpikir",
        "monolog": """OMA HERA: "Cucu Oma… kalau Yesus sudah bangkit… kenapa kita masih hidup seperti orang yang kalah?"

"Masih menyimpan dendam… masih membenci… masih hidup dalam gelap."

"Oma mau bicara jujur hari ini. Kebangkitan itu bukan hanya peristiwa dua ribu tahun lalu. Kebangkitan itu adalah panggilan… panggilan untuk hidup dengan cara yang berbeda."

"Rasul Paulus menulis dalam Surat Kolose 3 ayat 1… 'Jika kamu telah dibangkitkan bersama Kristus, carilah perkara yang di atas.' Artinya… cara berpikir kita harus berubah. Cara kita memperlakukan orang lain harus berubah."

"Hidup dalam terang, bukan kegelapan. Mengasihi, bukan membenci. Mengampuni, bukan menyimpan luka."

"Itu bukan hal yang mudah… Oma tahu. Tapi justru di situlah kuasa kebangkitan bekerja. Bukan dari kekuatan kita sendiri… tapi dari Dia yang sudah menang."

"Cucu Oma… hari ini, ada satu hal yang bisa kamu ubah? Satu luka yang bisa kamu lepaskan? Satu orang yang bisa kamu ampuni?"

"Mulai dari situ."

"Tuhan memberkati cucu Oma.\"""",
        "caption": "Kalau kita percaya Yesus bangkit… hidup kita seharusnya juga berubah. Bukan jadi sempurna — tapi jadi lebih berani mengasihi, lebih berani mengampuni. Itu buah kebangkitan yang nyata. 🌿✝️\n\n#OmaHera #HidupBaru #Kebangkitan #Mengampuni #CucuOma",
        "source": "Sumber: Dokumen 'Arti Kebangkitan Yesus bagi Umat Kristen' — Poin 3 (hidup dalam terang)",
    },
    {
        "title": "Masih di Jumat Agung atau Sudah di Hari Kebangkitan?",
        "hook_visual": "salib kayu sederhana dengan cahaya lembut di belakangnya, suasana hening",
        "hook_tone": "Suara pelan dan kontemplatif",
        "monolog": """OMA HERA: "Cucu Oma… Oma mau bertanya satu hal hari ini."

"Apakah kamu masih hidup di Jumat Agung… atau sudah masuk ke Hari Kebangkitan?"

"Jumat Agung itu hari penderitaan. Hari kegelapan. Hari di mana semuanya terasa hancur."

"Dan jujur… banyak dari kita yang masih tinggal di sana. Masih meratapi yang sudah lewat. Masih terjebak dalam rasa sakit yang lama."

"Tapi Yesus tidak tinggal di kubur, cucu Oma. Dia bangkit di hari ketiga."

"Dalam Injil Yohanes 11 ayat 25, Yesus berkata… 'Akulah kebangkitan dan hidup. Barangsiapa percaya kepada-Ku, ia akan hidup walaupun ia sudah mati.'"

"Artinya… kita tidak perlu tinggal di Jumat Agung selamanya. Ada Minggu Paskah yang menanti."

"Hari ini… tinggalkan yang lama. Bangkit dalam iman. Hidup dalam kasih."

"Karena Yesus hidup… dan itu mengubah segalanya."

"Tuhan memberkati cucu Oma.\"""",
        "caption": "Pertanyaan yang sederhana tapi dalam… apakah kita masih hidup dalam penderitaan lama, atau sudah berani melangkah ke hari kebangkitan? Yesus sudah bangkit — kita pun dipanggil untuk bangkit. 🌅✝️\n\n#OmaHera #JumatAgung #HariKebangkitan #CucuOma #ImanKristen",
        "source": "Sumber: Dokumen 'Arti Kebangkitan Yesus bagi Umat Kristen' — Bagian penutup/refleksi",
    },
    {
        "title": "Baptisan = Lahir Baru, Diampuni, Jadi Anak Tuhan",
        "hook_visual": "tetesan air jatuh pelan ke permukaan air tenang, riak kecil melebar",
        "hook_tone": "Suara lembut dan penuh kehangatan",
        "monolog": """OMA HERA: "Cucu Oma… kamu pernah bertanya tidak… kenapa Tuhan ingin kita dibaptis?"

"Apakah itu hanya tradisi? Hanya upacara? Hanya formalitas gereja?"

"Bukan, cucu Oma… baptisan itu jauh lebih dalam dari itu."

"Melalui baptisan… kita mati terhadap dosa yang lama… dan lahir baru dalam Kristus. Seperti yang tertulis dalam Surat Roma 6 ayat 4… 'Kita telah dikuburkan bersama-sama dengan Dia oleh baptisan… supaya kita hidup dalam hidup yang baru.'"

"Baptisan itu tanda bahwa dosamu sudah diampuni. Hubunganmu dengan Tuhan sudah dipulihkan."

"Dan yang paling indah… kamu diangkat menjadi anak Tuhan. Bukan hamba. Bukan orang asing. Tapi anak-Nya."

"Kamu juga tidak berjalan sendirian. Lewat baptisan, kamu masuk ke dalam keluarga Tuhan… menjadi bagian dari tubuh Kristus."

"Itu bukan hal yang kecil, cucu Oma. Itu adalah permulaan yang luar biasa."

"Tuhan memberkati cucu Oma.\"""",
        "caption": "Baptisan bukan sekadar ritual — itu momen di mana kita lahir baru, diampuni, dan resmi menjadi anak Tuhan. Kalau kamu sudah dibaptis, ingat lagi janji indah itu. Kalau belum… Tuhan menunggumu. 💧🌿\n\n#OmaHera #Baptisan #LahirBaru #AnakTuhan #CucuOma",
        "source": "Sumber: Dokumen 'Mengapa Tuhan Ingin Kita Dibaptis' — Poin 1-4",
    },
    {
        "title": "Dibaptis Bukan Berhenti di Berkat, Tapi Diutus",
        "hook_visual": "kaki melangkah keluar dari pintu rumah menuju jalan setapak yang terang",
        "hook_tone": "Suara Oma Hera dengan nada tegas tapi penuh kasih",
        "monolog": """OMA HERA: "Cucu Oma… ada satu hal tentang baptisan yang sering kita lupakan."

"Kita ingat bahwa baptisan itu tentang diselamatkan… diampuni… menerima Roh Kudus."

"Itu semua benar. Tapi baptisan tidak berhenti di situ."

"Setelah dibaptis… kita bukan hanya penerima berkat. Kita menjadi pembawa kabar baik."

"Yesus sendiri berkata dalam Injil Matius 28 ayat 19… 'Pergilah, jadikanlah semua bangsa murid-Ku dan baptislah mereka.' Itu bukan saran, cucu Oma… itu perintah."

"Artinya… hidupmu setelah baptisan harus menjadi kesaksian nyata. Di keluargamu… di tempat kerjamu… bahkan di dunia maya tempat kamu sering membuka layar setiap hari."

"Kamu tidak perlu jadi pengkhotbah besar. Cukup hidup dengan cara yang memancarkan kasih Kristus."

"Kita diselamatkan… diperbarui… dan diutus. Itulah baptisan yang utuh."

"Tuhan memberkati cucu Oma.\"""",
        "caption": "Dibaptis itu bukan garis akhir — itu garis start. Setelah menerima, kita dipanggil untuk memberi. Setelah diselamatkan, kita diutus untuk menjadi terang. Di mana pun kita berada. 🕊️🌿\n\n#OmaHera #Baptisan #Diutus #TerangDunia #CucuOma",
        "source": "Sumber: Dokumen 'Mengapa Tuhan Ingin Kita Dibaptis' — Poin 5-7, mewartakan Injil",
    },
    {
        "title": "Jawaban Yesus untuk Kamu yang Suka Membandingkan",
        "hook_visual": "dua jalan setapak bercabang di tengah kebun hijau, satu terang satu teduh",
        "hook_tone": "Suara Oma Hera, pelan tapi langsung menohok",
        "monolog": """OMA HERA: "Cucu Oma… jujur ya. Kamu sering tidak… lihat hidup orang lain terus bertanya dalam hati…"

"Kenapa dia lebih berhasil? Kenapa dia lebih cepat? Kenapa jalannya kelihatan lebih mudah?"

"Oma mau cerita. Petrus juga pernah begitu."

"Waktu melihat murid yang lain, Petrus bertanya kepada Yesus… 'Tuhan, bagaimana dengan dia?' Kamu tahu Yesus jawab apa?"

"Dalam Injil Yohanes 21 ayat 22… Yesus berkata… 'Itu bukan urusanmu. Engkau… ikutlah Aku.'"

"Keras? Iya. Tapi justru itu yang kita butuhkan."

"Tuhan tidak pernah menyuruh kita sibuk mengurusi jalan orang lain. Tuhan mau kita fokus pada langkah kita sendiri."

"Tidak semua orang punya cerita yang sama. Tidak semua orang punya waktu yang sama. Tidak semua orang punya panggilan yang sama."

"Jadi berhenti membandingkan… dan mulai bertanya… 'Tuhan, apa yang Engkau mau dalam hidupku?'"

"Tuhan memberkati cucu Oma.\"""",
        "caption": "Petrus bertanya soal orang lain. Yesus menjawab: itu bukan urusanmu. Yang penting adalah ketaatanmu sendiri. Hari ini, daripada menengok ke kiri dan kanan… coba tengadah ke atas. 🌿✝️\n\n#OmaHera #JanganBandingkan #IkutlahAku #Yohanes21 #CucuOma",
        "source": "Sumber: Dokumen 'Jangan Kepo Sama Jalan Orang Lain' — kisah Petrus (Yohanes 21:21-22)",
    },
    {
        "title": "Jalan Setiap Orang Berbeda — Dan Itu Urusan Tuhan",
        "hook_visual": "tangan tua menulis di buku catatan, sinar matahari sore masuk lewat jendela",
        "hook_tone": "Suara kontemplatif dan bijak",
        "monolog": """OMA HERA: "Cucu Oma… Oma sudah hidup cukup lama untuk tahu satu hal."

"Jalan setiap orang memang berbeda. Waktu setiap orang berbeda. Cerita setiap orang berbeda."

"Ada yang dipanggil cepat… ada yang harus menunggu lama. Ada yang jalannya lurus… ada yang harus memutar dulu."

"Tapi satu hal yang sama untuk kita semua… kita dipanggil untuk setia."

"Dalam Mazmur 37 ayat 5 tertulis… 'Serahkanlah jalanmu kepada Tuhan, percayalah kepada-Nya, dan Ia akan bertindak.'"

"Jalan orang lain itu urusan Tuhan. Tapi hidupmu… responmu… ketaatanmu… itu tanggung jawabmu."

"Jangan habiskan waktumu untuk iri dengan perjalanan orang lain… sementara Tuhan sudah menyiapkan jalan yang indah khusus untukmu."

"Yang paling penting bukan 'bagaimana dengan dia?' Tapi… 'apakah aku sungguh mengikuti Tuhan?'"

"Tuhan memberkati cucu Oma.\"""",
        "caption": "Setiap orang punya jalan, waktu, dan cerita yang berbeda. Tugas kita bukan membandingkan — tapi setia di jalan yang Tuhan berikan. Serahkan, percaya, dan terus melangkah. 🛤️🌿\n\n#OmaHera #SetiaDiJalanTuhan #Mazmur37 #CucuOma #Percaya",
        "source": "Sumber: Dokumen 'Jangan Kepo Sama Jalan Orang Lain' — refleksi tentang kesetiaan",
    },
    {
        "title": "Di Rumah Ada Suara yang Penuh Hikmat",
        "hook_visual": "tangan keriput memegang tangan muda dengan lembut, latar belakang taman hijau",
        "hook_tone": "Suara hangat dan penuh kerinduan",
        "monolog": """OMA HERA: "Cucu Oma… di dunia yang serba cepat ini… kita sibuk mendengar banyak suara."

"Suara dari layar… suara dari dunia luar… suara dari sana-sini."

"Tapi sering kali kita lupa… bahwa di rumah… ada suara yang paling penuh hikmat. Suara kakek dan nenekmu."

"Mereka bukan beban masa lalu, cucu Oma. Mereka adalah penjaga memori keluarga. Mereka adalah akar yang membuat kamu tetap kuat saat dunia mengguncang."

"Dalam Kitab Amsal 16 ayat 31 tertulis… 'Uban adalah mahkota keindahan, yang didapat pada jalan kebenaran.' Artinya… usia tua itu bukan kelemahan. Itu adalah kebijaksanaan."

"Dari kakek dan nenek… kamu belajar tentang kasih yang setia. Tentang iman yang bertahan. Tentang pengorbanan yang diam-diam tapi nyata."

"Maka hari ini… duduklah sebentar. Dengarkan cerita mereka. Tanyakan pengalaman mereka. Hargai nasihat mereka."

"Karena lewat kakek dan nenek… sering kali Tuhan sedang mengajar kita tentang cinta, kesabaran, dan kehidupan."

"Tuhan memberkati cucu Oma.\"""",
        "caption": "Di balik cerita yang mungkin terdengar berulang dari kakek-nenek kita… ada hikmat yang tidak bisa digantikan oleh teknologi mana pun. Mereka adalah akar kita. Hargai selagi masih bisa. 🌿🤍\n\n#OmaHera #DengarkanKakekNenek #AkarKeluarga #CucuOma #Hikmat",
        "source": "Sumber: Dokumen 'Dengarkan Kakek-Nenek' — kakek nenek sebagai penjaga memori keluarga",
    },
    {
        "title": "Jangan Tunggu Mereka Tiada, Baru Menyesal",
        "hook_visual": "kursi goyang kosong di teras rumah tua, angin pelan menggerakkan dedaunan",
        "hook_tone": "Suara pelan, emosional, sedikit serak",
        "monolog": """OMA HERA: "Cucu Oma… pernahkah kamu duduk diam… dan benar-benar mendengarkan kakek atau nenekmu?"

"Bukan sekadar hadir di ruangan yang sama. Tapi sungguh-sungguh… mendengar."

"Di balik cerita yang mungkin terdengar berulang… ada luka yang pernah mereka lewati. Ada doa yang diam-diam mereka panjatkan untukmu setiap malam."

"Mereka mungkin tidak mengerti dunia yang kamu jalani hari ini. Tapi mereka mengerti arti setia… arti sabar… arti bertahan."

"Dalam Kitab Imamat 19 ayat 32 tertulis… 'Hormatilah orang yang sudah tua, dan takutlah akan Tuhanmu.'"

"Oma ingin cucu Oma tahu… suatu hari nanti… yang tersisa dari mereka hanyalah kenangan. Kursi itu akan kosong. Suara itu akan sunyi."

"Jadi hari ini… jangan hanya lewat. Jangan hanya sibuk dengan layar."

"Pegang tangan mereka… dan dengarkan."

"Selagi masih bisa."

"Tuhan memberkati cucu Oma.\"""",
        "caption": "Oma tahu betul… waktu bersama orang tua yang kita cintai itu terbatas. Jangan sampai menyesal karena tidak sempat mendengar. Hari ini masih ada kesempatan. Gunakan dengan baik. 🤍🌿\n\n#OmaHera #JanganMenyesal #DengarkanMereka #CucuOma #KasihKeluarga",
        "source": "Sumber: Dokumen 'Dengarkan Kakek-Nenek' — refleksi tentang penyesalan",
    },
]


def get_next_oh_cid():
    headers, data, _ = read_sheet_info()
    col_map = get_header_index(headers)
    cid_col = col_map.get("content_id", 1)
    max_num = 0
    for row in data:
        if cid_col >= len(row):
            continue
        cid = row[cid_col].strip()
        if cid.startswith("OH-"):
            try:
                num = int(cid[3:])
                if num > max_num:
                    max_num = num
            except ValueError:
                pass
    return max_num + 1


def build_script_text(s):
    """Build the full script text for Google Doc."""
    return (
        f"HOOK (visual + suara pelan) (visual: {s['hook_visual']})\n"
        f"{s['hook_tone']}\n\n"
        f"{s['monolog']}\n\n"
        f"---\n"
        f"CAPTION:\n{s['caption']}\n"
    )


def create_doc(docs_service, drive_service, cid, script_data):
    """Create Google Doc for a script."""
    title = script_data["title"][:80]
    doc_title = f"[{cid}] Oma Hera - {title}"
    doc = docs_service.documents().create(body={"title": doc_title}).execute()
    doc_id = doc["documentId"]

    sep = "=" * 40
    hook_line = f"HOOK (visual: {script_data['hook_visual']})"
    full_text = (
        f"Content ID: {cid}\n"
        f"Brand: Oma Hera\n"
        f"Tipe: Reel\n"
        f"Topik: {script_data['title']}\n"
        f"Hook: {hook_line}\n"
        f"{script_data['source']}\n"
        f"{sep}\n\n"
        f"{build_script_text(script_data)}\n"
    )

    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{
            "insertText": {"location": {"index": 1}, "text": full_text}
        }]},
    ).execute()

    # Make shareable
    try:
        drive_service.permissions().create(
            fileId=doc_id,
            body={"type": "anyone", "role": "writer"},
        ).execute()
    except Exception:
        pass

    return f"https://docs.google.com/document/d/{doc_id}/edit"


def main():
    print("=" * 60)
    print("INSERT 9 OMA HERA SCRIPTS (Dimas manual)")
    print("=" * 60)

    creds = get_google_credentials()
    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)
    sheets_service = get_sheets_service()

    headers, data, _ = read_sheet_info()
    col_map = get_header_index(headers)

    start_num = get_next_oh_cid()
    print(f"Starting CID: OH-{start_num:03d}")
    print()

    # Build new rows
    new_rows = []
    created_docs = []  # For client review doc

    base_date = datetime(2026, 4, 20)  # 5 days from today (Apr 15)

    for i, s in enumerate(SCRIPTS):
        cid = f"OH-{start_num + i:03d}"
        print(f"[{i+1}/{len(SCRIPTS)}] {cid}: {s['title'][:50]}")

        # Create doc
        doc_url = create_doc(docs_service, drive_service, cid, s)
        print(f"  Doc: {doc_url}")

        # Build row
        new_row = [""] * len(headers)

        def set_field(field, value, row=new_row):
            idx = col_map.get(field)
            if idx is not None:
                row[idx] = value

        post_date = (base_date + timedelta(days=i*2)).strftime("%d %b")

        set_field("brand", "Oma Hera", new_row)
        set_field("content_id", cid, new_row)
        set_field("date", post_date, new_row)
        set_field("content_type", "Reel", new_row)
        set_field("topik", s["title"], new_row)
        set_field("hook", f"(visual: {s['hook_visual'][:60]})", new_row)
        set_field("brief", s["source"], new_row)
        set_field("script_status", "Ready for Client Review", new_row)
        set_field("script_owner", "Dimas", new_row)
        set_field("script_link", doc_url, new_row)
        set_field("production_status", "Not Started", new_row)
        set_field("asset_status", "Missing", new_row)
        set_field("editing_status", "Not Started", new_row)
        set_field("approval_status", "Pending", new_row)
        set_field("caption_status", "Not Started", new_row)
        set_field("posting_status", "Not Started", new_row)
        set_field("priority", "High", new_row)
        set_field("difficulty", "Medium", new_row)
        set_field("effort", "Medium", new_row)
        set_field("visual_status", "Skip - Video Manual", new_row)
        set_field("notes", "Manual by Dimas - ready for client review", new_row)

        new_rows.append(new_row)
        created_docs.append({
            "content_id": cid,
            "topic": s["title"],
            "content_type": "Reel",
            "hook": f"(visual: {s['hook_visual'][:60]})",
            "script_text": build_script_text(s),
        })

    # Batch append all rows
    print("\nAppending to Master Tracker...")
    sheets_service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{SHEET_NAME}'!A:A",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": new_rows},
    ).execute()
    print(f"  Added {len(new_rows)} rows")

    # Update client review doc for Oma Hera
    # First get ALL Oma Hera scripts that are Ready for Client Review (including the old 17)
    print("\nUpdating client review doc for Oma Hera...")
    from telegram_bot import fetch_doc_text
    headers2, data2, _ = read_sheet_info()
    col_map2 = get_header_index(headers2)

    def col2(row, name):
        idx = col_map2.get(name)
        if idx is not None and idx < len(row):
            return row[idx].strip()
        return ""

    all_oh_scripts = []
    for row in data2:
        if col2(row, "brand").lower() != "oma hera":
            continue
        if "ready for client review" not in col2(row, "script_status").lower():
            continue
        script_text = ""
        link = col2(row, "script_link")
        if link:
            script_text = fetch_doc_text(docs_service, link)
        all_oh_scripts.append({
            "content_id": col2(row, "content_id"),
            "topic": col2(row, "topik"),
            "content_type": col2(row, "content_type"),
            "hook": col2(row, "hook"),
            "script_text": script_text,
        })

    client_doc_url = build_or_update_client_review_doc("Oma Hera", all_oh_scripts)

    # Refresh task sheets
    from telegram_bot import rebuild_my_tasks_sheet, rebuild_production_tasks_sheet
    rebuild_my_tasks_sheet()
    rebuild_production_tasks_sheet()

    print()
    print("=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"Created: {len(new_rows)} new Oma Hera scripts (OH-{start_num:03d} to OH-{start_num + len(SCRIPTS) - 1:03d})")
    print(f"Status: Ready for Client Review")
    print(f"Total Oma Hera in client review: {len(all_oh_scripts)}")
    print(f"Client review doc: {client_doc_url}")


if __name__ == "__main__":
    main()
