import os

# Debug: tampilkan env var names yang relevan (tanpa nilai) untuk verifikasi di Railway logs
_debug_env_keys = sorted(k for k in os.environ if any(x in k.upper() for x in ("TELEGRAM", "ANTHROPIC", "GOOGLE")))
print(f"[DEBUG] Env vars tersedia: {_debug_env_keys}", flush=True)

import sys
import io
import re
import json
import logging
import tempfile
import base64
import httpx
from datetime import datetime

if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Semua credentials dibaca dari os.environ (Railway / terminal)
# Untuk development lokal, set env var manual di terminal sebelum jalankan script

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import anthropic
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest

# ============================================================
# FFMPEG PATH (lokal Windows, di Railway ffmpeg ada di PATH)
# ============================================================
FFMPEG_DIR = r"C:\Users\ASUS\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
if os.path.exists(FFMPEG_DIR):
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

# ============================================================
# KONFIGURASI
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SPREADSHEET_ID = os.environ.get("GOOGLE_SPREADSHEET_ID", "13_BnnBjVLRcpJAiyieBqF7tnuoRZ7ij7fs0u8Z9Hd1Y")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_NAME = "Master Tracker"

# Paths untuk file lokal (development)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BRAND_GUIDELINES_FILE = os.path.join(SCRIPT_DIR, "brand_guidelines.json")

CONTENT_TYPES = ["Carousel", "Reel", "Single Post", "Story"]
MAX_QA_RETRIES = 2

# Conversation states
STATE_IDLE = "idle"
STATE_WAIT_BRAND = "wait_brand"
STATE_WAIT_TOPIK = "wait_topik"
STATE_WAIT_ANGLE = "wait_angle"
STATE_WAIT_DATE = "wait_date"
STATE_WAIT_CONTENT_TYPE = "wait_content_type"
STATE_WAIT_CONFIRM_NEW_BRAND = "wait_confirm_new_brand"
STATE_WAIT_LINK_BRAND = "wait_link_brand"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ============================================================
# BRAND GUIDELINES
# ============================================================
def load_brand_guidelines():
    """Load brand guidelines dari env var atau JSON file."""
    # Prioritas 1: Env var (Railway)
    guidelines_json = os.environ.get("BRAND_GUIDELINES_JSON", "")
    if guidelines_json:
        return json.loads(guidelines_json)

    # Prioritas 2: File lokal
    if os.path.exists(BRAND_GUIDELINES_FILE):
        with open(BRAND_GUIDELINES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_guidelines_for_brand(brand):
    """Ambil guidelines untuk brand tertentu (case-insensitive match)."""
    guidelines = load_brand_guidelines()
    for key, val in guidelines.items():
        if key.lower() == brand.lower():
            return val
    return None


def format_guidelines_text(brand, guidelines):
    """Format guidelines jadi teks untuk prompt."""
    if not guidelines:
        return f"Tidak ada guidelines khusus untuk brand {brand}."
    return (
        f"Brand: {brand}\n"
        f"Tone: {guidelines['tone']}\n"
        f"Target audience: {guidelines['target']}\n"
        f"CTA: {guidelines['cta']}\n"
        f"Bahasa: {guidelines['bahasa']}\n"
        f"Rules:\n" + "\n".join(f"- {r}" for r in guidelines.get('rules', []))
    )


# ============================================================
# GOOGLE SHEETS
# ============================================================
def get_google_credentials():
    """Buat Google credentials dari env vars atau file lokal."""
    # Prioritas 1: Env vars (Railway deployment)
    google_token_json = os.environ.get("GOOGLE_TOKEN_JSON", "")
    if google_token_json:
        creds = Credentials.from_authorized_user_info(
            json.loads(google_token_json), SCOPES
        )
        if not creds.valid and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Update env var dengan token baru (untuk session ini)
            os.environ["GOOGLE_TOKEN_JSON"] = creds.to_json()
        return creds

    # Prioritas 2: File lokal (development)
    token_file = os.path.join(SCRIPT_DIR, "token.json")
    oauth_file = os.path.join(SCRIPT_DIR, "oauth_credentials.json")

    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(oauth_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return creds


def get_sheets_service():
    creds = get_google_credentials()
    return build("sheets", "v4", credentials=creds)


def read_sheet_info():
    """Baca header (baris 2) dan semua data dari Master Tracker."""
    service = get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{SHEET_NAME}'",
    ).execute()
    rows = result.get("values", [])

    if len(rows) < 2:
        return [], [], set()

    headers = [h.strip().replace("\n", " ") for h in rows[1]]
    data_rows = rows[2:]

    brands = set()
    for row in data_rows:
        if row and row[0].strip():
            brands.add(row[0].strip())

    return headers, data_rows, brands


def get_header_index(headers):
    """Return dict mapping field name -> column index."""
    mapping = {}
    target = {
        "brand name": "brand",
        "content id": "content_id",
        "date (planned post)": "date",
        "content type": "content_type",
        "content topic / title": "topik",
        "hook": "hook",
        "content brief": "brief",
        "script status": "script_status",
        "script owner": "script_owner",
        "script notes": "script_notes",
        "script link (google doc url)": "script_link",
        "production status": "production_status",
        "production pic": "production_pic",
        "shooting date": "shooting_date",
        "asset status": "asset_status",
        "editing status": "editing_status",
        "editor": "editor",
        "approval status": "approval_status",
        "caption status": "caption_status",
        "caption pic": "caption_pic",
        "scheduled date": "scheduled_date",
        "posting status": "posting_status",
        "priority level": "priority",
        "difficulty": "difficulty",
        "est. effort": "effort",
        "notes / keterangan": "notes",
        "bottleneck / issue": "bottleneck",
        "revision notes": "revision",
    }
    for idx, h in enumerate(headers):
        key = h.strip().lower()
        if key in target:
            mapping[target[key]] = idx
    return mapping


def get_next_content_id(data_rows, brand):
    """Cari Content ID terakhir untuk brand ini."""
    brand_upper = brand.strip().upper()
    prefixes = {
        "PLAYPOD": "PP", "SABITAH": "SB", "COUNTY": "CT",
        "LEGUS": "LG", "DEFARCHY": "DF", "HAPPY BABY": "HB",
        "PERSONAL BRAND DIMAS": "DM",
    }
    prefix = prefixes.get(brand_upper, brand_upper[:2].upper())

    max_num = 0
    for row in data_rows:
        if len(row) > 1:
            cid = row[1].strip()
            match = re.match(rf"^{prefix}-(\d+)$", cid)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num

    return f"{prefix}-{max_num + 1:03d}"


def extract_brief_and_script(full_output):
    """Pisahkan content brief dan script dari output Claude."""
    brief = ""
    script = full_output

    if "=== CONTENT BRIEF ===" in full_output and "=== SCRIPT ===" in full_output:
        parts = full_output.split("=== SCRIPT ===")
        brief_part = parts[0].replace("=== CONTENT BRIEF ===", "").strip()
        script_part = parts[1].strip() if len(parts) > 1 else ""
        return brief_part, script_part

    return brief, script


def append_to_sheet(headers, col_map, brand, content_id, date_str,
                    content_type, topik, angle, full_output, qa_status):
    """Tambah baris baru sesuai kolom header yang ada."""
    brief, script = extract_brief_and_script(full_output)
    new_row = [""] * len(headers)

    field_values = {
        "brand": brand,
        "content_id": content_id,
        "date": date_str,
        "content_type": content_type,
        "topik": topik,
        "hook": angle,
        "brief": brief,
        "script_status": "Done",
        "script_owner": "Claude AI",
        "script_notes": script or full_output,
        "production_status": "Not Started",
        "asset_status": "Missing",
        "editing_status": "Not Started",
        "approval_status": "Pending",
        "caption_status": "Not Started",
        "posting_status": "Not Started",
        "priority": "Medium",
        "difficulty": "Medium",
        "effort": "Medium",
        "notes": f"QA: {qa_status}",
    }

    for field, value in field_values.items():
        if field in col_map:
            new_row[col_map[field]] = value

    service = get_sheets_service()
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{SHEET_NAME}'!A:Z",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [new_row]},
    ).execute()

    return new_row


# ============================================================
# CLAUDE API
# ============================================================
def extract_content_info(client, raw_text):
    """Minta Claude extract brand, topik, angle, date, content_type."""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": f"""Dari pesan berikut, extract informasi untuk konten Instagram:

PESAN:
\"\"\"{raw_text}\"\"\"

Extract (isi null kalau tidak disebutkan):
- brand: nama brand/bisnis
- topik: topik utama konten
- angle: sudut pandang / hook
- date: tanggal posting (format: "Apr 15" atau sejenisnya)
- content_type: tipe konten (Carousel / Reel / Single Post / Story)

PENTING:
- Hanya respond "UNCLEAR" kalau pesan tidak ada hubungannya dengan konten/marketing
- Isi null untuk field yang benar-benar tidak disebutkan, jangan mengarang

Respond HANYA dalam JSON (tanpa markdown code block):
{{"brand": "..." or null, "topik": "..." or null, "angle": "..." or null, "date": "..." or null, "content_type": "..." or null}}"""}],
    )
    return message.content[0].text.strip()


def analyze_image(client, image_bytes, media_type, caption=""):
    """Analisis gambar via Claude Vision API, extract ide konten."""
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    user_content = []

    # Tambahkan gambar
    user_content.append({
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": image_b64,
        },
    })

    # Tambahkan caption kalau ada
    caption_text = f"\nCaption dari user: \"{caption}\"" if caption else ""

    user_content.append({
        "type": "text",
        "text": f"""Analisis gambar ini untuk keperluan pembuatan konten Instagram carousel.
{caption_text}

Dari gambar ini, extract:
- brand: nama brand/bisnis yang terlihat di gambar (kalau ada logo/nama brand). Isi null kalau tidak ada.
- topik: ide topik konten yang bisa dibuat berdasarkan gambar ini
- angle: sudut pandang / hook menarik yang terinspirasi dari gambar ini
- content_type: tipe konten yang cocok (Carousel / Reel / Single Post / Story). Isi null kalau tidak jelas.
- image_description: deskripsi singkat apa yang terlihat di gambar (1-2 kalimat)

Respond HANYA dalam JSON (tanpa markdown code block):
{{"brand": "..." or null, "topik": "...", "angle": "...", "content_type": "..." or null, "image_description": "..."}}""",
    })

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": user_content}],
    )
    return message.content[0].text.strip()


# ============================================================
# LINK DETECTION & CONTENT EXTRACTION
# ============================================================
YOUTUBE_REGEX = re.compile(
    r'(?:https?://)?(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([\w-]{11})'
)
INSTAGRAM_REGEX = re.compile(
    r'(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|reels)/([A-Za-z0-9_-]+)'
)
TIKTOK_REGEX = re.compile(
    r'(?:https?://)?(?:www\.)?(?:tiktok\.com/@[\w.]+/video/(\d+)|vm\.tiktok\.com/([\w-]+)|vt\.tiktok\.com/([\w-]+)|tiktok\.com/t/([\w-]+))'
)


def detect_links(text):
    """Detect YouTube, Instagram, dan TikTok links. Return list of (type, url, id)."""
    links = []
    for m in YOUTUBE_REGEX.finditer(text):
        links.append(("youtube", m.group(0), m.group(1)))
    for m in INSTAGRAM_REGEX.finditer(text):
        links.append(("instagram", m.group(0), m.group(1)))
    for m in TIKTOK_REGEX.finditer(text):
        # Ambil ID pertama yang tidak None
        tiktok_id = m.group(1) or m.group(2) or m.group(3) or m.group(4) or ""
        links.append(("tiktok", m.group(0), tiktok_id))
    return links


def get_youtube_content(video_id):
    """Ambil transcript atau info dari video YouTube."""
    content_parts = []

    # Coba ambil transcript
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Coba bahasa Indonesia dulu, lalu English, lalu apapun
        transcript = None
        for lang in ["id", "en"]:
            try:
                transcript = transcript_list.find_transcript([lang])
                break
            except Exception:
                continue

        if not transcript:
            transcript = transcript_list.find_generated_transcript(["id", "en"])

        if transcript:
            entries = transcript.fetch()
            full_text = " ".join(e.text for e in entries)
            # Truncate kalau terlalu panjang
            if len(full_text) > 3000:
                full_text = full_text[:3000] + "..."
            content_parts.append(f"TRANSCRIPT:\n{full_text}")

    except Exception as e:
        logger.info(f"No transcript for {video_id}: {e}")

    # Ambil judul & deskripsi via yt-dlp
    try:
        import subprocess
        result = subprocess.run(
            ["yt-dlp", "--get-title", "--get-description",
             "--no-download", "--no-warnings",
             f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True, text=True, timeout=30, encoding="utf-8"
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if lines:
                title = lines[0]
                description = "\n".join(lines[1:])[:1500]
                content_parts.insert(0, f"TITLE: {title}")
                if description.strip():
                    content_parts.insert(1, f"DESCRIPTION:\n{description}")
    except Exception as e:
        logger.info(f"yt-dlp failed for {video_id}: {e}")

    return "\n\n".join(content_parts) if content_parts else None


async def get_instagram_content(url):
    """Coba scrape caption dari Instagram post/reel."""
    try:
        # Approach: fetch halaman IG dan extract dari meta tags
        async with httpx.AsyncClient(
            timeout=15.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
            },
            follow_redirects=True,
        ) as client:
            # Tambahkan trailing slash kalau belum ada
            clean_url = url.rstrip("/") + "/"
            resp = await client.get(clean_url)
            html = resp.text

            # Extract dari og:description meta tag
            og_match = re.search(
                r'<meta\s+(?:property|name)="og:description"\s+content="([^"]*)"',
                html
            )
            if not og_match:
                og_match = re.search(
                    r'content="([^"]*)"\s+(?:property|name)="og:description"',
                    html
                )

            og_title = re.search(
                r'<meta\s+(?:property|name)="og:title"\s+content="([^"]*)"',
                html
            )
            if not og_title:
                og_title = re.search(
                    r'content="([^"]*)"\s+(?:property|name)="og:title"',
                    html
                )

            parts = []
            if og_title:
                parts.append(f"TITLE: {og_title.group(1)}")
            if og_match:
                desc = og_match.group(1).replace("&amp;", "&").replace("&#039;", "'")
                parts.append(f"CAPTION:\n{desc}")

            return "\n\n".join(parts) if parts else None

    except Exception as e:
        logger.info(f"Instagram scrape failed: {e}")
        return None


def get_tiktok_content(url):
    """Ambil judul dan deskripsi dari TikTok video via yt-dlp."""
    try:
        import subprocess
        # Pastikan URL lengkap
        if not url.startswith("http"):
            url = "https://" + url

        result = subprocess.run(
            ["yt-dlp", "--get-title", "--get-description",
             "--no-download", "--no-warnings", url],
            capture_output=True, text=True, timeout=30, encoding="utf-8"
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            title = lines[0] if lines else ""
            description = "\n".join(lines[1:])[:1500] if len(lines) > 1 else ""

            parts = []
            if title:
                parts.append(f"TITLE: {title}")
            if description.strip():
                parts.append(f"DESCRIPTION:\n{description}")
            return "\n\n".join(parts) if parts else None

    except Exception as e:
        logger.info(f"yt-dlp TikTok failed: {e}")

    # Fallback: coba scrape meta tags
    try:
        import subprocess as sp
        r = sp.run(
            ["yt-dlp", "--dump-json", "--no-download", "--no-warnings", url],
            capture_output=True, text=True, timeout=30, encoding="utf-8"
        )
        if r.returncode == 0:
            data = json.loads(r.stdout)
            parts = []
            if data.get("title"):
                parts.append(f"TITLE: {data['title']}")
            if data.get("description"):
                parts.append(f"DESCRIPTION:\n{data['description'][:1500]}")
            if data.get("uploader"):
                parts.append(f"CREATOR: {data['uploader']}")
            return "\n\n".join(parts) if parts else None
    except Exception as e:
        logger.info(f"yt-dlp JSON TikTok failed: {e}")

    return None


def analyze_link_content(client, content_text, source_type, source_url):
    """Analisa konten dari link via Claude API."""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=600,
        messages=[{"role": "user", "content": f"""Analisa konten {source_type} berikut yang diambil dari: {source_url}

KONTEN:
\"\"\"{content_text}\"\"\"

Identifikasi:
- topik: topik utama konten ini
- angle: sudut pandang / hook yang dipakai
- hook: kalimat hook pembuka yang digunakan
- struktur: bagaimana konten ini disusun (poin-poin utama)
- insight: pelajaran yang bisa diambil untuk bikin konten serupa

Respond HANYA dalam JSON (tanpa markdown code block):
{{"topik": "...", "angle": "...", "hook": "...", "struktur": "...", "insight": "..."}}"""}],
    )
    return message.content[0].text.strip()


def generate_inspired_script(client, brand, inspiration_data, content_type="Carousel"):
    """Generate script yang TERINSPIRASI dari konten link, sesuai brand guidelines."""
    guidelines = get_guidelines_for_brand(brand)
    guidelines_text = format_guidelines_text(brand, guidelines)

    prompt = f"""Kamu adalah content strategist untuk brand "{brand}" di Indonesia.

BRAND GUIDELINES:
{guidelines_text}

INSPIRASI KONTEN (dari konten orang lain — JANGAN copy, jadikan INSPIRASI saja):
- Topik: {inspiration_data.get('topik', 'N/A')}
- Angle: {inspiration_data.get('angle', 'N/A')}
- Hook: {inspiration_data.get('hook', 'N/A')}
- Struktur: {inspiration_data.get('struktur', 'N/A')}
- Insight: {inspiration_data.get('insight', 'N/A')}

Buatkan CONTENT BRIEF dan SCRIPT {content_type} Instagram 7 slide yang TERINSPIRASI dari konten di atas tapi DISESUAIKAN untuk brand {brand}.

PENTING:
- JANGAN menjiplak konten asli — buat versi original untuk brand {brand}
- Sesuaikan tone, bahasa, dan CTA dengan brand guidelines
- Buat angle yang fresh tapi terinspirasi dari konsep aslinya

BAGIAN 1 — CONTENT BRIEF:
- Objective, Target Audience, Key Message, Tone & Style, CTA Goal
- Sumber inspirasi: [sebutkan konten aslinya sebagai referensi]

BAGIAN 2 — SCRIPT 7 SLIDE:
1. Slide 1 = Hook/Cover
2. Slide 2-6 = Konten inti
3. Slide 7 = CTA sesuai brand guidelines
4. Maksimal 50 kata per slide

Format:
=== CONTENT BRIEF ===
[isi brief]

=== SCRIPT ===
SLIDE 1 (COVER):
[isi]
... sampai SLIDE 7 (CTA)"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def generate_script(client, brand, topik, angle, content_type):
    """Generate content brief + script dengan brand guidelines."""
    guidelines = get_guidelines_for_brand(brand)
    guidelines_text = format_guidelines_text(brand, guidelines)

    prompt = f"""Kamu adalah content strategist untuk brand "{brand}" di Indonesia.

BRAND GUIDELINES:
{guidelines_text}

Buatkan CONTENT BRIEF dan SCRIPT {content_type} Instagram 7 slide:

- Brand: {brand}
- Topik: {topik}
- Angle/Hook: {angle}

BAGIAN 1 — CONTENT BRIEF:
Tulis content brief singkat yang mencakup:
- Objective: tujuan konten ini
- Target Audience: siapa yang dituju
- Key Message: pesan utama yang ingin disampaikan
- Tone & Style: tone yang dipakai
- CTA Goal: apa yang diharapkan audience lakukan

BAGIAN 2 — SCRIPT 7 SLIDE:
1. Slide 1 = Hook/Cover — gunakan angle yang diberikan, tambahkan arahan visual
2. Slide 2-6 = Konten inti — edukatif, storytelling, insight actionable
3. Slide 7 = CTA — HARUS sesuai brand guidelines CTA di atas
4. Bahasa HARUS sesuai guidelines bahasa di atas
5. Tone HARUS sesuai guidelines tone di atas
6. Target audience: sesuai guidelines
7. Setiap slide tulis: judul slide, isi teks, dan catatan visual singkat
8. Maksimal 50 kata per slide
9. Jangan pakai emoji berlebihan, maksimal 1-2 per slide

Format output:

=== CONTENT BRIEF ===
[isi brief]

=== SCRIPT ===
SLIDE 1 (COVER):
[isi]

SLIDE 2:
[isi]

... sampai SLIDE 7 (CTA)"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def qa_review_script(client, brand, script):
    """QA Agent: review script terhadap brand guidelines."""
    guidelines = get_guidelines_for_brand(brand)
    guidelines_text = format_guidelines_text(brand, guidelines)

    prompt = f"""Review script carousel Instagram berikut untuk brand "{brand}".

BRAND GUIDELINES:
{guidelines_text}

SCRIPT:
\"\"\"
{script}
\"\"\"

CEK:
1. Apakah tone sesuai brand guidelines? (tone: {guidelines['tone'] if guidelines else 'N/A'})
2. Apakah CTA di slide 7 sesuai guidelines? (CTA: {guidelines['cta'] if guidelines else 'N/A'})
3. Apakah bahasa sesuai? (bahasa: {guidelines['bahasa'] if guidelines else 'N/A'})
4. Apakah ada slide yang lebih dari 50 kata? (hitung per slide)
5. Apakah target audience sesuai? (target: {guidelines['target'] if guidelines else 'N/A'})
6. Apakah semua rules brand dipatuhi?

Respond dalam format:
Baris pertama HARUS salah satu dari: "APPROVED" atau "REVISION NEEDED"
Kalau REVISION NEEDED, lanjutkan dengan catatan spesifik apa yang harus diperbaiki (per poin)."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def revise_script(client, brand, original_script, qa_notes):
    """Perbaiki script berdasarkan catatan QA."""
    guidelines = get_guidelines_for_brand(brand)
    guidelines_text = format_guidelines_text(brand, guidelines)

    prompt = f"""Perbaiki script carousel berikut berdasarkan catatan QA reviewer.

BRAND GUIDELINES:
{guidelines_text}

SCRIPT ORIGINAL:
\"\"\"
{original_script}
\"\"\"

CATATAN QA (harus diperbaiki):
{qa_notes}

ATURAN PERBAIKAN:
- Perbaiki HANYA bagian yang disebutkan di catatan QA
- Pertahankan struktur 7 slide
- Pastikan setiap slide maksimal 50 kata
- Pastikan CTA sesuai brand guidelines
- Pastikan tone & bahasa sesuai guidelines

Tulis ulang script yang sudah diperbaiki, dalam format yang sama:
SLIDE 1 (COVER):
[isi]
... sampai SLIDE 7 (CTA)"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


async def generate_with_qa(client, update, brand, topik, angle, content_type):
    """Generate script + QA review loop. Return (final_script, qa_status_text)."""

    # Step 1: Generate script
    await update.message.reply_text("Generating script dengan brand guidelines...")
    script = generate_script(client, brand, topik, angle, content_type)
    logger.info(f"Script generated: {len(script)} chars")

    # Step 2: QA Review loop
    qa_status = "APPROVED"
    revision_count = 0

    for attempt in range(1, MAX_QA_RETRIES + 2):  # max retries + initial
        await update.message.reply_text(f"QA Review (attempt {attempt})...")
        qa_result = qa_review_script(client, brand, script)
        logger.info(f"QA attempt {attempt}: {qa_result[:100]}")

        first_line = qa_result.split("\n")[0].strip().upper()

        if "APPROVED" in first_line:
            qa_status = f"APPROVED (attempt {attempt})"
            break
        else:
            # Revision needed
            qa_notes = qa_result  # full QA feedback
            revision_count += 1

            if revision_count > MAX_QA_RETRIES:
                # Max retries reached, use last version
                qa_status = f"APPROVED WITH NOTES (after {revision_count} revisions, max retries reached)"
                await update.message.reply_text(
                    f"QA sudah {revision_count}x revisi, memakai versi terakhir."
                )
                break

            await update.message.reply_text(
                f"QA: Revision needed. Memperbaiki script...\n"
                f"Catatan: {qa_notes[:200]}..."
            )
            script = revise_script(client, brand, script, qa_notes)
            logger.info(f"Script revised: {len(script)} chars")

    return script, qa_status


# ============================================================
# VOICE NOTE → TEXT
# ============================================================
async def voice_to_text(file_url: str) -> str:
    """Download voice note via HTTP, convert OGG→WAV, lalu speech-to-text."""
    import speech_recognition as sr
    from pydub import AudioSegment

    with tempfile.TemporaryDirectory() as tmpdir:
        ogg_path = os.path.join(tmpdir, "voice.ogg")
        wav_path = os.path.join(tmpdir, "voice.wav")

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(file_url)
            resp.raise_for_status()
            with open(ogg_path, "wb") as f:
                f.write(resp.content)

        logger.info(f"Voice downloaded: {os.path.getsize(ogg_path)} bytes")

        audio = AudioSegment.from_ogg(ogg_path)
        audio.export(wav_path, format="wav")
        logger.info(f"Converted to WAV: {os.path.getsize(wav_path)} bytes")

        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)

        try:
            text = recognizer.recognize_google(audio_data, language="id-ID")
        except sr.UnknownValueError:
            try:
                text = recognizer.recognize_google(audio_data, language="en-US")
            except sr.UnknownValueError:
                return None

    return text


# ============================================================
# CONVERSATION HELPERS
# ============================================================
def get_session(context):
    if "session" not in context.user_data:
        reset_session(context)
    return context.user_data["session"]


def reset_session(context):
    context.user_data["session"] = {
        "state": STATE_IDLE,
        "brand": None,
        "topik": None,
        "angle": None,
        "date": None,
        "content_type": None,
    }


def find_missing_fields(session):
    missing = []
    for field in ["brand", "topik", "angle", "date", "content_type"]:
        if not session.get(field):
            missing.append(field)
    return missing


FIELD_QUESTIONS = {
    "brand": "Brand apa yang mau dibuatkan kontennya?\nBrand yang tersedia: {brands}",
    "topik": "Topik kontennya tentang apa?",
    "angle": "Angle/hook-nya mau dari sudut pandang apa?",
    "date": "Tanggal posting kapan? (contoh: Apr 15, May 1)",
    "content_type": "Tipe kontennya apa?\nPilih: Carousel / Reel / Single Post / Story",
}


async def ask_next_missing(update, context, session, brands):
    missing = find_missing_fields(session)
    if not missing:
        return False

    field = missing[0]
    question = FIELD_QUESTIONS[field]

    if field == "brand":
        brand_list = ", ".join(sorted(brands)) if brands else "(belum ada brand)"
        question = question.format(brands=brand_list)
        session["state"] = STATE_WAIT_BRAND
    elif field == "topik":
        session["state"] = STATE_WAIT_TOPIK
    elif field == "angle":
        session["state"] = STATE_WAIT_ANGLE
    elif field == "date":
        session["state"] = STATE_WAIT_DATE
    elif field == "content_type":
        session["state"] = STATE_WAIT_CONTENT_TYPE

    await update.message.reply_text(question)
    return True


async def finalize_and_generate(update, context, session):
    """Semua info lengkap — generate + QA + save."""
    brand = session["brand"]
    topik = session["topik"]
    angle = session["angle"]
    date_str = session["date"]
    content_type = session["content_type"]

    # Cek apakah ada guidelines
    guidelines = get_guidelines_for_brand(brand)
    guidelines_info = ""
    if guidelines:
        guidelines_info = f"\n  Guidelines: {guidelines['tone']} | CTA: {guidelines['cta']}"
    else:
        guidelines_info = "\n  Guidelines: (generic, tidak ada guidelines khusus)"

    await update.message.reply_text(
        f"Semua info lengkap!{guidelines_info}\n\n"
        f"  Brand: {brand}\n"
        f"  Topik: {topik}\n"
        f"  Angle: {angle}\n"
        f"  Tanggal: {date_str}\n"
        f"  Tipe: {content_type}"
    )

    try:
        claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Generate + QA loop
        script, qa_status = await generate_with_qa(
            claude_client, update, brand, topik, angle, content_type
        )

        # Simpan ke Google Sheet
        headers, data_rows, _ = read_sheet_info()
        col_map = get_header_index(headers)
        content_id = get_next_content_id(data_rows, brand)

        append_to_sheet(headers, col_map, brand, content_id, date_str,
                        content_type, topik, angle, script, qa_status)

        # Reply ke Telegram
        header = (
            f"Script berhasil di-generate!\n"
            f"Content ID: {content_id}\n"
            f"QA Status: {qa_status}\n"
            f"Status: Done (tersimpan di Google Sheet)\n\n"
        )

        full_reply = header + script
        if len(full_reply) <= 4096:
            await update.message.reply_text(full_reply)
        else:
            await update.message.reply_text(header + "(Script dikirim di pesan berikut)")
            for i in range(0, len(script), 4096):
                await update.message.reply_text(script[i : i + 4096])

        logger.info(f"Processed {content_id}: {brand} - {topik} | QA: {qa_status}")

    except Exception as e:
        logger.error(f"Error in finalize: {e}", exc_info=True)
        await update.message.reply_text(f"Terjadi error saat generate:\n{str(e)}")

    reset_session(context)


# ============================================================
# TELEGRAM HANDLERS
# ============================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_session(context)

    # Load brand list dari guidelines
    guidelines = load_brand_guidelines()
    brand_list = "\n".join(f"  - {b}" for b in guidelines.keys())

    await update.message.reply_text(
        "Halo! Aku bot Carousel Script Generator.\n\n"
        "Kirim aku pesan dalam format APAPUN, contoh:\n\n"
        "- \"Bikin konten Playpod tentang dating spot yang anti-awkward\"\n"
        "- \"Sabitah, topiknya branding buat pemula, carousel, post 15 April\"\n"
        "- Kirim foto sebagai inspirasi konten\n"
        "- Atau kirim voice note!\n\n"
        f"Brand dengan guidelines:\n{brand_list}\n\n"
        "Fitur:\n"
        "- Auto-detect brand, topik, angle dari pesan bebas\n"
        "- Generate script sesuai brand guidelines\n"
        "- QA review otomatis + auto-revisi\n"
        "- Simpan ke Google Sheet\n\n"
        "Ketik /cancel untuk batalkan proses."
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_session(context)
    await update.message.reply_text("Proses dibatalkan. Kirim pesan baru untuk mulai lagi.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        return
    await process_text(update, context, text)


async def process_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Core logic untuk proses teks."""
    session = get_session(context)
    state = session["state"]

    try:
        if state == STATE_WAIT_BRAND:
            await handle_brand_reply(update, context, session, text)
            return

        if state == STATE_WAIT_CONFIRM_NEW_BRAND:
            await handle_new_brand_confirm(update, context, session, text)
            return

        if state == STATE_WAIT_TOPIK:
            session["topik"] = text
            _, _, brands = read_sheet_info()
            if not await ask_next_missing(update, context, session, brands):
                await finalize_and_generate(update, context, session)
            return

        if state == STATE_WAIT_ANGLE:
            session["angle"] = text
            _, _, brands = read_sheet_info()
            if not await ask_next_missing(update, context, session, brands):
                await finalize_and_generate(update, context, session)
            return

        if state == STATE_WAIT_DATE:
            session["date"] = text
            _, _, brands = read_sheet_info()
            if not await ask_next_missing(update, context, session, brands):
                await finalize_and_generate(update, context, session)
            return

        if state == STATE_WAIT_CONTENT_TYPE:
            ct = match_content_type(text)
            if not ct:
                await update.message.reply_text(
                    f"Tipe \"{text}\" tidak dikenali.\n"
                    f"Pilih: Carousel / Reel / Single Post / Story"
                )
                return
            session["content_type"] = ct
            _, _, brands = read_sheet_info()
            if not await ask_next_missing(update, context, session, brands):
                await finalize_and_generate(update, context, session)
            return

        if state == STATE_WAIT_LINK_BRAND:
            await handle_link_brand_reply(update, context, session, text)
            return

        # ── STATE: IDLE — pesan baru ──
        logger.info(f"[INCOMING] user={update.effective_user.id} text={text!r}")

        # Cek apakah ada link YouTube / Instagram
        links = detect_links(text)
        if links:
            await handle_link_message(update, context, session, links, text)
            return

        await update.message.reply_text("Menganalisis pesan kamu...")

        # Coba parsing via Claude API, fallback ke local parser kalau gagal
        data = None
        try:
            claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            extracted = extract_content_info(claude_client, text)
            logger.info(f"Claude extracted: {extracted}")

            if "UNCLEAR" in extracted and "{" not in extracted:
                logger.info("Claude returned UNCLEAR, using fallback parser")
                data = fallback_parse(text)
            else:
                json_text = re.sub(r"^```json\s*", "", extracted)
                json_text = re.sub(r"\s*```$", "", json_text)
                # Coba cari JSON object di response
                json_match = re.search(r'\{[^{}]*\}', json_text, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(0))
                else:
                    data = json.loads(json_text)
        except Exception as e:
            logger.warning(f"Claude API/parse failed: {e}, using fallback parser")
            data = fallback_parse(text)

        logger.info(f"Parsed data: {data}")

        if data.get("brand"):
            session["brand"] = data["brand"]
        if data.get("topik"):
            session["topik"] = data["topik"]
        if data.get("angle"):
            session["angle"] = data["angle"]
        if data.get("date"):
            session["date"] = data["date"]
        if data.get("content_type"):
            ct = match_content_type(data["content_type"])
            if ct:
                session["content_type"] = ct

        # Kalau belum ada topik sama sekali, pakai seluruh teks sebagai topik
        if not session.get("topik") and not session.get("brand"):
            session["topik"] = text

        filled = []
        for f in ["brand", "topik", "angle", "date", "content_type"]:
            if session.get(f):
                filled.append(f"  {f}: {session[f]}")

        if filled:
            await update.message.reply_text(
                "Oke, aku tangkap:\n" + "\n".join(filled)
            )

        if session.get("brand"):
            _, _, brands = read_sheet_info()
            brand_valid = await validate_brand(
                update, context, session, session["brand"], brands
            )
            if not brand_valid:
                return

        _, _, brands = read_sheet_info()
        if not await ask_next_missing(update, context, session, brands):
            await finalize_and_generate(update, context, session)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await update.message.reply_text(f"Terjadi error:\n{str(e)}")
        reset_session(context)


async def validate_brand(update, context, session, brand_input, brands):
    """Validasi brand terhadap Sheet + guidelines."""
    # Gabungkan brand dari sheet dan guidelines
    guidelines = load_brand_guidelines()
    all_brands = set(brands)
    for g_brand in guidelines.keys():
        all_brands.add(g_brand)

    brands_lower = {b.lower(): b for b in all_brands}
    if brand_input.lower() in brands_lower:
        session["brand"] = brands_lower[brand_input.lower()]
        return True

    brand_list = ", ".join(sorted(all_brands)) if all_brands else "(belum ada brand)"
    session["_pending_brand"] = brand_input
    session["state"] = STATE_WAIT_CONFIRM_NEW_BRAND
    await update.message.reply_text(
        f"Brand \"{brand_input}\" belum ada di tracker.\n\n"
        f"Brand yang tersedia: {brand_list}\n\n"
        f"Mau pakai yang mana, atau ketik \"baru\" untuk buat brand baru?"
    )
    return False


async def handle_brand_reply(update, context, session, text):
    _, _, brands = read_sheet_info()
    guidelines = load_brand_guidelines()
    all_brands = set(brands)
    for g_brand in guidelines.keys():
        all_brands.add(g_brand)

    brands_lower = {b.lower(): b for b in all_brands}
    if text.lower() in brands_lower:
        session["brand"] = brands_lower[text.lower()]
        if not await ask_next_missing(update, context, session, all_brands):
            await finalize_and_generate(update, context, session)
        return

    brand_valid = await validate_brand(update, context, session, text, brands)
    if brand_valid:
        if not await ask_next_missing(update, context, session, all_brands):
            await finalize_and_generate(update, context, session)


async def handle_new_brand_confirm(update, context, session, text):
    _, _, brands = read_sheet_info()
    guidelines = load_brand_guidelines()
    all_brands = set(brands)
    for g_brand in guidelines.keys():
        all_brands.add(g_brand)

    if text.lower() == "baru":
        session["brand"] = session.pop("_pending_brand", text)
        await update.message.reply_text(f"Oke, pakai brand baru: {session['brand']}")
        if not await ask_next_missing(update, context, session, all_brands):
            await finalize_and_generate(update, context, session)
        return

    brands_lower = {b.lower(): b for b in all_brands}
    if text.lower() in brands_lower:
        session["brand"] = brands_lower[text.lower()]
        session.pop("_pending_brand", None)
        if not await ask_next_missing(update, context, session, all_brands):
            await finalize_and_generate(update, context, session)
        return

    brand_list = ", ".join(sorted(all_brands)) if all_brands else "(belum ada brand)"
    await update.message.reply_text(
        f"\"{text}\" tidak dikenali.\n\n"
        f"Brand yang tersedia: {brand_list}\n"
        f"Atau ketik \"baru\" untuk pakai brand baru."
    )


def match_content_type(text):
    text_lower = text.lower().strip()
    mapping = {
        "carousel": "Carousel",
        "reel": "Reel",
        "reels": "Reel",
        "single post": "Single Post",
        "single": "Single Post",
        "post": "Single Post",
        "story": "Story",
        "stories": "Story",
    }
    for key, val in mapping.items():
        if key in text_lower:
            return val
    return None


def fallback_parse(text):
    """Fallback parser: extract brand/topik/angle dari teks tanpa Claude API.
    Lebih baik tebak dari konteks daripada gagal."""
    guidelines = load_brand_guidelines()
    all_brand_names = list(guidelines.keys())
    # Tambahkan brand dari known prefixes
    known_brands = [
        "Playpod", "Sabitah", "County", "Legus", "Defarchy",
        "Happy Baby", "Personal Brand Dimas",
    ]
    for b in known_brands:
        if b not in all_brand_names:
            all_brand_names.append(b)

    text_lower = text.lower()

    # 1) Detect brand — cari nama brand di dalam teks
    brand = None
    for b in all_brand_names:
        if b.lower() in text_lower:
            brand = b
            break

    # 2) Detect content type
    content_type = match_content_type(text)

    # 3) Detect date — pattern sederhana
    date = None
    date_match = re.search(
        r'(\d{1,2}\s+(?:jan|feb|mar|apr|mei|may|jun|jul|aug|agu|sep|okt|oct|nov|des|dec)\w*'
        r'|(?:jan|feb|mar|apr|mei|may|jun|jul|aug|agu|sep|okt|oct|nov|des|dec)\w*\s+\d{1,2})',
        text_lower,
    )
    if date_match:
        date = date_match.group(0).strip()

    # 4) Detect angle — cari setelah kata "angle", "hook", "sudut pandang"
    angle = None
    angle_match = re.search(
        r'(?:angle|hook|sudut pandang)[:\s]+(.+?)(?:,|$|\.|content type|tipe|tanggal|posting)',
        text_lower,
    )
    if angle_match:
        angle = angle_match.group(1).strip().strip('"\'')

    # 5) Sisanya jadi topik — hapus brand, angle, date, content type dari teks
    topik_text = text
    # Hapus brand name
    if brand:
        topik_text = re.sub(re.escape(brand), "", topik_text, flags=re.IGNORECASE).strip()
    # Hapus kata-kata umum di awal
    topik_text = re.sub(
        r'^(?:bikin(?:kan)?|buat(?:kan)?|tolong|mau|coba|generate|konten|content)\s+',
        '', topik_text, flags=re.IGNORECASE,
    ).strip()
    topik_text = re.sub(
        r'^(?:bikin(?:kan)?|buat(?:kan)?|tolong|mau|coba|generate|konten|content)\s+',
        '', topik_text, flags=re.IGNORECASE,
    ).strip()
    # Hapus content type keywords
    for ct_word in ["carousel", "reel", "reels", "single post", "story", "stories"]:
        topik_text = re.sub(r'\b' + ct_word + r'\b', '', topik_text, flags=re.IGNORECASE)
    # Hapus angle part
    if angle_match:
        topik_text = topik_text[:angle_match.start()] + topik_text[angle_match.end():]
    # Hapus date part
    if date_match:
        topik_text = topik_text[:date_match.start()] + topik_text[date_match.end():]
    # Cleanup
    topik_text = re.sub(r'[,\s]+', ' ', topik_text).strip().strip(',-. ')

    topik = topik_text if topik_text else None

    return {
        "brand": brand,
        "topik": topik,
        "angle": angle,
        "date": date,
        "content_type": content_type,
    }


async def handle_link_message(update, context, session, links, full_text):
    """Handle pesan yang mengandung link YouTube/Instagram."""
    link_type, link_url, link_id = links[0]  # proses link pertama

    # Pastikan URL lengkap
    if not link_url.startswith("http"):
        link_url = "https://" + link_url

    source_labels = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok"}
    source_label = source_labels.get(link_type, link_type)
    await update.message.reply_text(
        f"Link {source_label} terdeteksi!\nMengambil konten dari: {link_url}"
    )

    # Extract konten dari link
    content = None
    if link_type == "youtube":
        content = get_youtube_content(link_id)
    elif link_type == "instagram":
        content = await get_instagram_content(link_url)
    elif link_type == "tiktok":
        content = get_tiktok_content(link_url)

    if not content:
        await update.message.reply_text(
            f"Maaf, aku nggak bisa mengambil konten dari link ini.\n"
            f"Coba kirim manual aja topik dan anglenya."
        )
        session["state"] = STATE_IDLE
        return

    await update.message.reply_text("Konten berhasil diambil! Menganalisa...")

    # Analisa konten via Claude
    claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    analysis_raw = analyze_link_content(claude_client, content, source_label, link_url)
    logger.info(f"Link analysis: {analysis_raw}")

    try:
        json_text = re.sub(r"^```json\s*", "", analysis_raw)
        json_text = re.sub(r"\s*```$", "", json_text)
        inspiration = json.loads(json_text)
    except (json.JSONDecodeError, KeyError):
        await update.message.reply_text(
            "Gagal menganalisa konten. Coba kirim manual aja topik dan anglenya."
        )
        session["state"] = STATE_IDLE
        return

    # Simpan inspirasi di session
    session["_inspiration"] = inspiration
    session["_link_url"] = link_url
    session["_link_type"] = source_label

    # Tanya user mau pakai brand apa
    _, _, brands = read_sheet_info()
    guidelines = load_brand_guidelines()
    all_brands = set(brands)
    for g in guidelines.keys():
        all_brands.add(g)
    brand_list = ", ".join(sorted(all_brands)) if all_brands else "(belum ada brand)"

    await update.message.reply_text(
        f"Hasil analisa konten {source_label}:\n\n"
        f"  Topik: {inspiration.get('topik', '-')}\n"
        f"  Angle: {inspiration.get('angle', '-')}\n"
        f"  Hook: {inspiration.get('hook', '-')}\n\n"
        f"Mau saya buatkan script carousel terinspirasi dari ini untuk brand mana?\n\n"
        f"Brand tersedia: {brand_list}"
    )

    session["state"] = STATE_WAIT_LINK_BRAND


async def handle_link_brand_reply(update, context, session, text):
    """Handle jawaban brand setelah analisa link."""
    _, _, brands = read_sheet_info()
    guidelines = load_brand_guidelines()
    all_brands = set(brands)
    for g in guidelines.keys():
        all_brands.add(g)
    brands_lower = {b.lower(): b for b in all_brands}

    # Match brand
    brand = None
    if text.lower() in brands_lower:
        brand = brands_lower[text.lower()]
    else:
        # Coba fuzzy: cek apakah text mengandung nama brand
        for key, val in brands_lower.items():
            if key in text.lower():
                brand = val
                break

    if not brand:
        brand_list = ", ".join(sorted(all_brands))
        await update.message.reply_text(
            f"Brand \"{text}\" tidak dikenali.\n"
            f"Brand tersedia: {brand_list}\n\n"
            f"Ketik nama brand yang mau dipakai:"
        )
        return

    inspiration = session.get("_inspiration", {})
    link_url = session.get("_link_url", "")
    link_type = session.get("_link_type", "")

    await update.message.reply_text(
        f"Oke! Generating script untuk {brand} terinspirasi dari {link_type}..."
    )

    try:
        claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Generate inspired script
        script = generate_inspired_script(claude_client, brand, inspiration)

        # QA review
        await update.message.reply_text("QA Review...")
        qa_result = qa_review_script(claude_client, brand, script)
        first_line = qa_result.split("\n")[0].strip().upper()

        qa_status = "APPROVED (attempt 1)"
        if "APPROVED" not in first_line:
            await update.message.reply_text("QA: Revision needed, memperbaiki...")
            script = revise_script(claude_client, brand, script, qa_result)
            qa_status = "APPROVED (after revision)"

        # Simpan ke Google Sheet
        today = f"{datetime.now().strftime('%b')} {datetime.now().day}"

        headers, data_rows, _ = read_sheet_info()
        col_map = get_header_index(headers)
        content_id = get_next_content_id(data_rows, brand)

        append_to_sheet(
            headers, col_map, brand, content_id, today,
            "Carousel", inspiration.get("topik", ""), inspiration.get("angle", ""),
            script, f"{qa_status} | Inspired by: {link_url}"
        )

        # Reply
        header = (
            f"Script berhasil di-generate!\n"
            f"Content ID: {content_id}\n"
            f"Inspirasi: {link_url}\n"
            f"QA Status: {qa_status}\n"
            f"Status: Done (tersimpan di Google Sheet)\n\n"
        )

        full_reply = header + script
        if len(full_reply) <= 4096:
            await update.message.reply_text(full_reply)
        else:
            await update.message.reply_text(header + "(Script dikirim di pesan berikut)")
            for i in range(0, len(script), 4096):
                await update.message.reply_text(script[i : i + 4096])

        logger.info(f"Processed {content_id}: {brand} inspired by {link_url}")

    except Exception as e:
        logger.error(f"Error in link generation: {e}", exc_info=True)
        await update.message.reply_text(f"Terjadi error:\n{str(e)}")

    # Cleanup session
    session.pop("_inspiration", None)
    session.pop("_link_url", None)
    session.pop("_link_type", None)
    reset_session(context)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle foto — analisis gambar via Claude Vision, lalu proses."""
    caption = update.message.caption or ""
    await update.message.reply_text("Foto diterima, menganalisis gambar...")

    try:
        # Ambil foto resolusi tertinggi (terakhir di list)
        photo = update.message.photo[-1]
        logger.info(f"Photo received: {photo.width}x{photo.height}, {photo.file_size} bytes")

        tg_file = await context.bot.get_file(
            photo.file_id, read_timeout=60, write_timeout=60, connect_timeout=60
        )

        file_url = tg_file.file_path
        if not file_url.startswith("http"):
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_url}"

        # Download gambar
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            resp = await http_client.get(file_url)
            resp.raise_for_status()
            image_bytes = resp.content

        logger.info(f"Photo downloaded: {len(image_bytes)} bytes")

        # Detect media type dari file path
        if file_url.lower().endswith(".png"):
            media_type = "image/png"
        elif file_url.lower().endswith(".webp"):
            media_type = "image/webp"
        else:
            media_type = "image/jpeg"

        # Analisis gambar via Claude Vision
        claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        extracted = analyze_image(claude_client, image_bytes, media_type, caption)
        logger.info(f"Image analysis: {extracted}")

        # Parse JSON
        json_text = re.sub(r"^```json\s*", "", extracted)
        json_text = re.sub(r"\s*```$", "", json_text)
        data = json.loads(json_text)

        # Tampilkan deskripsi gambar
        img_desc = data.get("image_description", "")
        await update.message.reply_text(
            f"Hasil analisis gambar:\n\"{img_desc}\""
        )

        # Isi session dengan data yang di-extract
        session = get_session(context)

        if data.get("brand"):
            session["brand"] = data["brand"]
        if data.get("topik"):
            session["topik"] = data["topik"]
        if data.get("angle"):
            session["angle"] = data["angle"]
        if data.get("content_type"):
            ct = match_content_type(data["content_type"])
            if ct:
                session["content_type"] = ct

        # Tampilkan apa yang sudah ditangkap
        filled = []
        for f in ["brand", "topik", "angle", "date", "content_type"]:
            if session.get(f):
                filled.append(f"  {f}: {session[f]}")

        if filled:
            await update.message.reply_text(
                "Dari gambar, aku tangkap:\n" + "\n".join(filled)
            )

        # Validasi brand & tanya yang kurang
        if session.get("brand"):
            _, _, brands = read_sheet_info()
            brand_valid = await validate_brand(
                update, context, session, session["brand"], brands
            )
            if not brand_valid:
                return

        _, _, brands = read_sheet_info()
        if not await ask_next_missing(update, context, session, brands):
            await finalize_and_generate(update, context, session)

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error parsing image analysis: {e}", exc_info=True)
        await update.message.reply_text(
            "Maaf, aku gagal menganalisis gambar ini.\n"
            "Coba kirim ulang, atau ketik aja pesannya."
        )
    except Exception as e:
        logger.error(f"Error processing photo: {e}", exc_info=True)
        await update.message.reply_text(f"Gagal proses foto:\n{str(e)}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Voice note diterima, converting ke teks...")

    try:
        voice = update.message.voice
        logger.info(f"Voice note received: {voice.duration}s, {voice.file_size} bytes")

        tg_file = await context.bot.get_file(
            voice.file_id, read_timeout=60, write_timeout=60, connect_timeout=60
        )

        file_url = tg_file.file_path
        if not file_url.startswith("http"):
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_url}"

        logger.info(f"Downloading from: {file_url}")
        text = await voice_to_text(file_url)

        if not text:
            await update.message.reply_text(
                "Maaf, aku nggak bisa mengenali suaranya.\n"
                "Coba kirim ulang dengan suara lebih jelas, atau ketik aja pesannya."
            )
            return

        await update.message.reply_text(f"Hasil transkripsi:\n\"{text}\"")
        await process_text(update, context, text)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error processing voice: {e}", exc_info=True)
        if "ffprobe" in error_msg or "ffmpeg" in error_msg:
            await update.message.reply_text(
                "Voice note gagal diproses (ffmpeg error).\n"
                "Untuk sementara, tolong ketik aja pesannya ya!"
            )
        else:
            await update.message.reply_text(f"Gagal proses voice note:\n{error_msg}")


# ============================================================
# MAIN
# ============================================================
def main():
    if not TELEGRAM_BOT_TOKEN:
        print("[WARNING] TELEGRAM_BOT_TOKEN tidak ditemukan! Set environment variable TELEGRAM_BOT_TOKEN.")
    if not ANTHROPIC_API_KEY:
        print("[WARNING] ANTHROPIC_API_KEY tidak ditemukan! Set environment variable ANTHROPIC_API_KEY.")

    guidelines = load_brand_guidelines()

    print("=" * 60)
    print("  TELEGRAM CAROUSEL BOT (Brand Guidelines + QA)")
    print(f"  Bot Token: ...{TELEGRAM_BOT_TOKEN[-8:]}")
    print(f"  API Key  : ...{ANTHROPIC_API_KEY[-8:]}")
    print(f"  Sheet    : {SPREADSHEET_ID}")
    print(f"  Brands   : {', '.join(guidelines.keys())}")
    print("=" * 60)
    print("  Fitur:")
    print("    - Terima pesan format apapun + voice note + foto")
    print("    - Brand guidelines per brand")
    print("    - QA Agent: auto-review + auto-revisi")
    print("    - Multi-step conversation flow")
    print("    - Auto-save ke Google Sheet")
    print("=" * 60)
    print("\n  Bot sedang berjalan... (Ctrl+C untuk stop)\n")

    request = HTTPXRequest(read_timeout=60, write_timeout=60, connect_timeout=60)
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
