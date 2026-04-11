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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
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
REPORT_CHAT_ID = os.environ.get("REPORT_CHAT_ID", "")  # Telegram chat ID untuk daily report
TEAM_GROUP_ID = os.environ.get("TEAM_GROUP_ID", "")  # Telegram group ID untuk notifikasi tim

# Tim Sabitah
TEAM_MEMBERS = {
    "Dimas": "Owner",
    "Firman": "Content Creator",
    "Asdi": "Social Media Specialist",
    "Dedi": "Main Editor",
}
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
STATE_WAIT_DOC_BRAND = "wait_doc_brand"
STATE_WAIT_DOC_CONTENT_TYPE = "wait_doc_content_type"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _extract_first_json_object(text):
    """Extract JSON object pertama dari string pakai brace counting.
    Support nested braces dan string values yang mengandung braces."""
    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == '\\' and in_string:
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def safe_json_loads(text, fallback=None):
    """Parse JSON object pertama dari string. Abaikan teks sebelum/sesudah.
    Return fallback (default: dict kosong) kalau gagal."""
    if fallback is None:
        fallback = {}
    if not text or not text.strip():
        return fallback

    # Step 1: Extract JSON object pertama dari teks
    json_str = _extract_first_json_object(text)
    if not json_str:
        logger.warning(f"safe_json_loads: no JSON object found in: {text[:200]!r}")
        return fallback

    logger.info(f"safe_json_loads: extracted {len(json_str)} chars JSON")

    # Step 2: Coba parse langsung
    try:
        return json.loads(json_str, strict=False)
    except json.JSONDecodeError as e:
        logger.warning(f"safe_json_loads: direct parse failed: {e}")

    # Step 3: Sanitasi control chars lalu coba lagi
    try:
        sanitized = json_str.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
        return json.loads(sanitized, strict=False)
    except json.JSONDecodeError as e:
        logger.warning(f"safe_json_loads: sanitized parse failed: {e}")

    logger.warning(f"safe_json_loads gagal parse: {json_str[:300]!r}")
    return fallback


# ============================================================
# BRAND GUIDELINES
# ============================================================
def load_brand_guidelines():
    """Load brand guidelines dari env var atau JSON file."""
    # Prioritas 1: Env var (Railway)
    guidelines_json = os.environ.get("BRAND_GUIDELINES_JSON", "")
    if guidelines_json:
        logger.info(f"[BRAND] Loading guidelines dari env var BRAND_GUIDELINES_JSON ({len(guidelines_json)} chars)")
        data = safe_json_loads(guidelines_json)
        if data:
            logger.info(f"[BRAND] Brands dari env: {list(data.keys())}")
            return data
        else:
            logger.error(f"[BRAND] Gagal parse BRAND_GUIDELINES_JSON")
            logger.error(f"[BRAND] JSON preview: {guidelines_json[:200]!r}")
            return {}

    # Prioritas 2: File lokal
    if os.path.exists(BRAND_GUIDELINES_FILE):
        with open(BRAND_GUIDELINES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"[BRAND] Brands dari file: {list(data.keys())}")
            return data

    logger.warning("[BRAND] Tidak ada brand guidelines (env var maupun file)")
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
    # Prioritas 1: Service Account (Railway — recommended)
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if sa_json:
        from google.oauth2 import service_account
        info = json.loads(sa_json, strict=False)
        logger.info(f"[GOOGLE] Pakai Service Account: {info.get('client_email', '?')}")
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

    # Prioritas 2: OAuth token env var (fallback — cek apakah service account atau OAuth)
    google_token_json = os.environ.get("GOOGLE_TOKEN_JSON", "")
    if google_token_json:
        info = json.loads(google_token_json, strict=False)
        # Cek apakah ini service account
        if info.get("type") == "service_account":
            from google.oauth2 import service_account
            logger.info(f"[GOOGLE] GOOGLE_TOKEN_JSON berisi Service Account: {info.get('client_email', '?')}")
            return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        # OAuth token biasa
        logger.info("[GOOGLE] Pakai OAuth token dari GOOGLE_TOKEN_JSON")
        creds = Credentials.from_authorized_user_info(info, SCOPES)
        if not creds.valid and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            os.environ["GOOGLE_TOKEN_JSON"] = creds.to_json()
        return creds

    # Prioritas 3: File lokal (development)
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


REQUIRED_HEADERS = ["Canva Link", "Production Status", "Visual Status"]


def col_to_letter(col_index):
    """Convert 0-based column index to sheet letter (0=A, 25=Z, 26=AA)."""
    result = ""
    while True:
        result = chr(65 + col_index % 26) + result
        col_index = col_index // 26 - 1
        if col_index < 0:
            break
    return result


def ensure_sheet_headers(headers):
    """Pastikan kolom wajib ada di Sheet. Tambahkan kalau belum ada.
    Expand grid kalau perlu."""
    headers_lower = [h.strip().lower() for h in headers]
    missing = [h for h in REQUIRED_HEADERS if h.strip().lower() not in headers_lower]
    if not missing:
        return headers

    try:
        service = get_sheets_service()
        start_col = len(headers)
        needed_cols = start_col + len(missing)

        # Get current grid size and expand if needed
        sheet_meta = service.spreadsheets().get(
            spreadsheetId=SPREADSHEET_ID,
            fields="sheets.properties",
        ).execute()
        for s in sheet_meta.get("sheets", []):
            if s["properties"]["title"] == SHEET_NAME:
                current_cols = s["properties"]["gridProperties"]["columnCount"]
                if needed_cols > current_cols:
                    sheet_id = s["properties"]["sheetId"]
                    service.spreadsheets().batchUpdate(
                        spreadsheetId=SPREADSHEET_ID,
                        body={"requests": [{
                            "appendDimension": {
                                "sheetId": sheet_id,
                                "dimension": "COLUMNS",
                                "length": needed_cols - current_cols,
                            }
                        }]},
                    ).execute()
                    logger.info(f"[SHEET] Expanded grid to {needed_cols} columns")
                break

        for i, new_header in enumerate(missing):
            col_letter = col_to_letter(start_col + i)
            cell = f"'{SHEET_NAME}'!{col_letter}2"
            service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=cell,
                valueInputOption="RAW",
                body={"values": [[new_header]]},
            ).execute()
            headers.append(new_header)
            logger.info(f"[SHEET] Added header '{new_header}' at column {col_letter}")
    except Exception as e:
        logger.error(f"[SHEET] Failed to add headers: {e}")

    return headers


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
        "canva link": "canva_link",
        "design link": "canva_link",
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
        "visual status": "visual_status",
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
        "SABITAH": "SB", "COUNTY": "CT",
        "LEGUS": "LG", "DEFARCHY": "DF", "HAPPY BABY": "HB",
        "PERSONAL BRAND DIMAS": "DM",
        "OMA HERA": "OH", "CI ANGEL": "CA",
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
    text = full_output.strip()

    # Coba berbagai separator yang mungkin dipakai Claude
    brief_markers = ["=== CONTENT BRIEF ===", "## CONTENT BRIEF", "**CONTENT BRIEF**",
                     "CONTENT BRIEF:", "CONTENT BRIEF"]
    script_markers = ["=== SCRIPT ===", "## SCRIPT", "**SCRIPT**",
                      "SCRIPT:", "SLIDE 1"]

    brief = ""
    script = text

    # Cari posisi brief dan script markers
    brief_pos = -1
    brief_marker_len = 0
    for marker in brief_markers:
        pos = text.upper().find(marker.upper())
        if pos != -1:
            brief_pos = pos
            brief_marker_len = len(marker)
            break

    script_pos = -1
    for marker in script_markers:
        pos = text.upper().find(marker.upper())
        if pos != -1 and (brief_pos == -1 or pos > brief_pos):
            script_pos = pos
            break

    if brief_pos != -1 and script_pos != -1:
        brief = text[brief_pos + brief_marker_len:script_pos].strip().strip("=-#* ")
        script = text[script_pos:].strip()
    elif script_pos != -1:
        # Tidak ada brief section, tapi ada script
        brief = ""
        script = text[script_pos:].strip()

    # Kalau brief masih kosong, buat ringkasan dari slide pertama
    if not brief and script:
        lines = [l.strip() for l in script.split('\n') if l.strip() and not l.strip().startswith('SLIDE') and not l.strip().startswith('===')]
        # Ambil beberapa baris pertama sebagai brief
        brief_lines = lines[:3]
        if brief_lines:
            brief = " ".join(brief_lines)
            if len(brief) > 300:
                brief = brief[:297] + "..."

    return brief, script


def append_to_sheet(headers, col_map, brand, content_id, date_str,
                    content_type, topik, angle, full_output, qa_status):
    """Tambah baris baru sesuai kolom header yang ada."""
    headers = ensure_sheet_headers(headers)
    col_map = get_header_index(headers)
    brief, script = extract_brief_and_script(full_output)
    logger.info(f"[SHEET] Brief length: {len(brief)}, Script length: {len(script)}")
    logger.info(f"[SHEET] Brief preview: {brief[:150]!r}")
    logger.info(f"[SHEET] Col map: {col_map}")
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
        "script_owner": "Dimas",
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
        "canva_link": "",
        "visual_status": (
            "Ready for Visual" if content_type and content_type.lower() == "carousel"
            else "Skip - Video Manual" if content_type and content_type.lower() in ("reel", "reels")
            else "Not Started"
        ),
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
            data = json.loads(r.stdout, strict=False)
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
# SHEET HELPERS (Visual Status)
# ============================================================


def update_sheet_visual_status(content_id, status):
    """Update kolom Visual Status di Google Sheet untuk content_id tertentu."""
    try:
        headers, data_rows, _ = read_sheet_info()
        col_map = get_header_index(headers)
        vs_col = col_map.get("visual_status")
        if vs_col is None:
            logger.warning("[SHEET] No visual_status column found")
            return

        cid_col = col_map.get("content_id", 1)
        for row_idx, row in enumerate(data_rows):
            if len(row) > cid_col and row[cid_col].strip() == content_id:
                cell = f"'{SHEET_NAME}'!{col_to_letter(vs_col)}{row_idx + 3}"
                service = get_sheets_service()
                service.spreadsheets().values().update(
                    spreadsheetId=SPREADSHEET_ID,
                    range=cell,
                    valueInputOption="RAW",
                    body={"values": [[status]]},
                ).execute()
                logger.info(f"[SHEET] Visual Status updated: {cell} = {status}")
                return
    except Exception as e:
        logger.error(f"[SHEET] Failed to update visual status: {e}")


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

        # Notify team
        await notify_new_content(context, content_id, brand, topik, content_type)

        # Update Visual Status & notify for Carousel
        if content_type == "Carousel":
            if content_id:
                update_sheet_visual_status(content_id, "Ready for Visual")
            await update.message.reply_text(
                f"✅ Script carousel {brand} sudah jadi dan tersimpan di tracker.\n\n"
                f"Untuk generate visual, buka Claude.ai Project "
                f"'Brand Visual Generator' dan ketik:\n"
                f"*generate carousel dari tracker*",
                parse_mode="Markdown",
            )

    except Exception as e:
        logger.error(f"Error in finalize: {e}", exc_info=True)
        await update.message.reply_text(f"Terjadi error saat generate:\n{str(e)}")

    reset_session(context)


# ============================================================
# TELEGRAM HANDLERS
# ============================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_session(context)

    # Auto-save chat ID untuk daily report
    chat_id = str(update.effective_chat.id)
    context.bot_data["report_chat_id"] = chat_id
    logger.info(f"[REPORT] Chat ID saved: {chat_id}")

    # Load brand list dari guidelines
    guidelines = load_brand_guidelines()
    brand_list = "\n".join(f"  - {b}" for b in guidelines.keys())

    await update.message.reply_text(
        "Halo! Aku bot Carousel Script Generator.\n\n"
        "Kirim aku pesan dalam format APAPUN, contoh:\n\n"
        "- \"Bikin konten Sabitah tentang dating spot yang anti-awkward\"\n"
        "- \"Sabitah, topiknya branding buat pemula, carousel, post 15 April\"\n"
        "- Kirim foto sebagai inspirasi konten\n"
        "- Atau kirim voice note!\n\n"
        f"Brand dengan guidelines:\n{brand_list}\n\n"
        "Fitur:\n"
        "- Auto-detect brand, topik, angle dari pesan bebas\n"
        "- Generate script sesuai brand guidelines\n"
        "- QA review otomatis + auto-revisi\n"
        "- Simpan ke Google Sheet\n"
        "- /report — lihat daily report sekarang\n\n"
        "Ketik /cancel untuk batalkan proses."
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_session(context)
    await update.message.reply_text("Proses dibatalkan. Kirim pesan baru untuk mulai lagi.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        return

    # In groups, only respond if bot is mentioned or user has active session
    chat_type = update.effective_chat.type
    if chat_type in ("group", "supergroup"):
        session = get_session(context)
        bot_username = (await context.bot.get_me()).username or ""
        is_mentioned = f"@{bot_username}" in text
        has_active_session = session.get("state", STATE_IDLE) != STATE_IDLE

        if not is_mentioned and not has_active_session:
            return  # Ignore random group messages

        # Remove bot mention from text
        if is_mentioned:
            text = text.replace(f"@{bot_username}", "").strip()

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

        if state == STATE_WAIT_DOC_BRAND:
            # Fallback kalau user ketik manual instead of button
            known = get_all_known_brands()
            known_lower = {b.lower(): b for b in known}
            brand_match = known_lower.get(text.lower())
            if not brand_match:
                guidelines = load_brand_guidelines()
                keyboard = []
                row = []
                for i, brand_name in enumerate(guidelines.keys()):
                    row.append(InlineKeyboardButton(brand_name, callback_data=f"docbrand:{brand_name}"))
                    if len(row) == 2:
                        keyboard.append(row)
                        row = []
                if row:
                    keyboard.append(row)
                await update.message.reply_text(
                    f"Brand \"{text}\" tidak dikenali. Pilih salah satu:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return
            session["brand"] = brand_match
            session["state"] = STATE_WAIT_DOC_CONTENT_TYPE
            keyboard = [
                [InlineKeyboardButton("Carousel (7 slide)", callback_data="doctype:Carousel")],
                [InlineKeyboardButton("Reels (30-60 detik)", callback_data="doctype:Reel")],
                [InlineKeyboardButton("Single Post", callback_data="doctype:Single Post")],
            ]
            await update.message.reply_text(
                f"Brand: *{brand_match}*\n\nMau dijadikan konten tipe apa?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return

        if state == STATE_WAIT_DOC_CONTENT_TYPE:
            # Fallback kalau user ketik manual
            ct = match_content_type(text)
            if not ct:
                keyboard = [
                    [InlineKeyboardButton("Carousel (7 slide)", callback_data="doctype:Carousel")],
                    [InlineKeyboardButton("Reels (30-60 detik)", callback_data="doctype:Reel")],
                    [InlineKeyboardButton("Single Post", callback_data="doctype:Single Post")],
                ]
                await update.message.reply_text(
                    f"Tipe \"{text}\" tidak dikenali. Pilih salah satu:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return
            session["_doc_content_type"] = ct
            await _process_doc_with_brand(update, context, session)
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
                data = safe_json_loads(json_text)
                if not data:
                    logger.info("safe_json_loads returned empty, using fallback parser")
                    data = fallback_parse(text)
        except Exception as e:
            logger.warning(f"Claude API/parse failed: {e}, using fallback parser")
            data = fallback_parse(text)

        logger.info(f"Parsed data: {data}")

        # Validasi brand SEBELUM set di session
        if data.get("brand"):
            known = get_all_known_brands()
            known_lower = {b.lower(): b for b in known}
            parsed_brand = data["brand"].strip()
            if parsed_brand.lower() in known_lower:
                session["brand"] = known_lower[parsed_brand.lower()]
            else:
                logger.info(f"Brand '{parsed_brand}' tidak ada di daftar, diabaikan")
                data["brand"] = None  # jangan set di session

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

        # Kalau brand dari parsing tidak valid, langsung tanya user
        if data.get("brand") is None and not session.get("brand"):
            all_brands = get_all_known_brands()
            brand_list = ", ".join(sorted(all_brands))
            session["state"] = STATE_WAIT_BRAND
            await update.message.reply_text(
                f"Brand tidak ditemukan dari pesanmu.\n\n"
                f"Brand yang tersedia: {brand_list}\n\n"
                f"Mau pakai yang mana?"
            )
            return

        if session.get("brand"):
            all_brands = get_all_known_brands()
            known_lower = {b.lower(): b for b in all_brands}
            if session["brand"].lower() not in known_lower:
                brand_list = ", ".join(sorted(all_brands))
                session["brand"] = None
                session["state"] = STATE_WAIT_BRAND
                await update.message.reply_text(
                    f"Brand tidak ditemukan.\n\n"
                    f"Brand yang tersedia: {brand_list}\n\n"
                    f"Mau pakai yang mana?"
                )
                return

        _, _, brands = read_sheet_info()
        if not await ask_next_missing(update, context, session, brands):
            await finalize_and_generate(update, context, session)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await update.message.reply_text(f"Terjadi error:\n{str(e)}")
        reset_session(context)


def get_all_known_brands():
    """Return set semua brand yang valid (dari guidelines + sheet)."""
    guidelines = load_brand_guidelines()
    all_brands = set(guidelines.keys())
    # Tambahkan known brands yang mungkin belum ada di guidelines
    for b in ["Sabitah", "County", "LEGUS", "Defarchy",
              "Happy Baby", "Personal Brand Dimas", "Oma Hera", "Ci Angel"]:
        all_brands.add(b)
    try:
        _, _, sheet_brands = read_sheet_info()
        all_brands.update(sheet_brands)
    except Exception:
        pass
    return all_brands


async def validate_brand(update, context, session, brand_input, brands):
    """Validasi brand — harus ada di daftar, tidak boleh tebak."""
    all_brands = get_all_known_brands()

    brands_lower = {b.lower(): b for b in all_brands}
    if brand_input.lower() in brands_lower:
        session["brand"] = brands_lower[brand_input.lower()]
        return True

    brand_list = ", ".join(sorted(all_brands)) if all_brands else "(belum ada brand)"
    session["brand"] = None  # reset brand yang salah
    session["state"] = STATE_WAIT_BRAND
    await update.message.reply_text(
        f"Brand \"{brand_input}\" tidak ditemukan.\n\n"
        f"Brand yang tersedia: {brand_list}\n\n"
        f"Mau pakai yang mana?"
    )
    return False


async def handle_brand_reply(update, context, session, text):
    all_brands = get_all_known_brands()

    brands_lower = {b.lower(): b for b in all_brands}
    if text.lower() in brands_lower:
        session["brand"] = brands_lower[text.lower()]
        if not await ask_next_missing(update, context, session, all_brands):
            await finalize_and_generate(update, context, session)
        return

    # Brand tidak dikenali — tanya ulang
    brand_list = ", ".join(sorted(all_brands))
    await update.message.reply_text(
        f"Brand \"{text}\" tidak ditemukan.\n\n"
        f"Brand yang tersedia: {brand_list}\n\n"
        f"Mau pakai yang mana?"
    )


async def handle_new_brand_confirm(update, context, session, text):
    """Redirect ke handle_brand_reply — tidak ada opsi 'baru' lagi."""
    session["state"] = STATE_WAIT_BRAND
    await handle_brand_reply(update, context, session, text)


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
    all_brand_names = list(get_all_known_brands())

    text_lower = text.lower()

    # 1) Detect brand — cari nama brand EXACT (word boundary) di dalam teks
    brand = None
    for b in sorted(all_brand_names, key=len, reverse=True):  # match terpanjang dulu
        if re.search(r'\b' + re.escape(b.lower()) + r'\b', text_lower):
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

    json_text = re.sub(r"^```json\s*", "", analysis_raw)
    json_text = re.sub(r"\s*```$", "", json_text)
    inspiration = safe_json_loads(json_text)
    if not inspiration:
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
    all_brands = get_all_known_brands()
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
    all_brands = get_all_known_brands()
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

        # Parse JSON — safe_json_loads handles semua edge cases
        logger.info(f"Raw Claude image response: {extracted[:500]!r}")
        data = safe_json_loads(extracted)

        if not data:
            logger.warning("Image analysis returned empty data")
            await update.message.reply_text(
                "Aku terima gambarnya, tapi gagal extract info.\n"
                "Coba ketik aja pesannya, misal: \"Bikin konten Sabitah tentang ...\""
            )
            return

        # Tampilkan deskripsi gambar
        img_desc = data.get("image_description", "")
        if img_desc:
            await update.message.reply_text(
                f"Hasil analisis gambar:\n\"{img_desc}\""
            )

        # Isi session dengan data yang di-extract
        session = get_session(context)

        # Validasi brand sebelum set di session
        if data.get("brand"):
            known = get_all_known_brands()
            known_lower = {b.lower(): b for b in known}
            if data["brand"].lower() in known_lower:
                session["brand"] = known_lower[data["brand"].lower()]
            else:
                logger.info(f"Image brand '{data['brand']}' tidak valid, diabaikan")

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

        _, _, brands = read_sheet_info()
        if not await ask_next_missing(update, context, session, brands):
            await finalize_and_generate(update, context, session)

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
# CALLBACK QUERY HANDLER (Inline Buttons)
# ============================================================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()
    data = query.data
    session = get_session(context)

    if data.startswith("docbrand:"):
        brand_name = data.split(":", 1)[1]
        session["brand"] = brand_name
        session["state"] = STATE_WAIT_DOC_CONTENT_TYPE

        keyboard = [
            [InlineKeyboardButton("Carousel (7 slide)", callback_data="doctype:Carousel")],
            [InlineKeyboardButton("Reels (30-60 detik)", callback_data="doctype:Reel")],
            [InlineKeyboardButton("Single Post", callback_data="doctype:Single Post")],
        ]
        await query.edit_message_text(
            f"Brand: *{brand_name}*\n\nMau dijadikan konten tipe apa?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data.startswith("doctype:"):
        content_type = data.split(":", 1)[1]
        session["_doc_content_type"] = content_type
        await query.edit_message_text(
            f"Tipe konten: *{content_type}*\nMemproses...",
            parse_mode="Markdown",
        )
        # Create a fake Update with message for _process_doc_with_brand
        await _process_doc_with_brand(query, context, session)

    else:
        logger.warning(f"Unknown callback data: {data}")


# ============================================================
# DOCUMENT UPLOAD → AUTO SCRIPT
# ============================================================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document upload — extract text, ask brand, then generate script."""
    # Skip if message is from a group and not a direct reply to bot or private chat
    chat_type = update.effective_chat.type
    if chat_type in ("group", "supergroup"):
        # In groups, only process documents that are explicitly sent to bot
        # (via reply or caption mentioning bot)
        caption = update.message.caption or ""
        bot_username = (await context.bot.get_me()).username or ""
        if f"@{bot_username}" not in caption:
            return  # Ignore documents in group unless bot is mentioned

    doc = update.message.document
    if not doc:
        return

    # Skip GIFs, stickers, animations
    mime = doc.mime_type or ""
    if any(t in mime for t in ("gif", "video", "image", "sticker", "webp", "mp4")):
        return

    file_name = doc.file_name or "unknown"
    caption = update.message.caption or ""

    # Filter: only accept text-based docs
    allowed_ext = (".txt", ".doc", ".docx", ".pdf", ".md", ".rtf", ".csv")
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in allowed_ext:
        # Only reply in private chat, not in groups (avoid spam)
        if chat_type == "private":
            await update.message.reply_text(
                f"Format file '{ext}' belum didukung.\n"
                f"Kirim file berupa: {', '.join(allowed_ext)}"
            )
        return

    await update.message.reply_text(f"📄 Dokumen diterima: {file_name}\nMenganalisis isi dokumen...")

    try:
        tg_file = await context.bot.get_file(
            doc.file_id, read_timeout=60, write_timeout=60, connect_timeout=60
        )
        file_url = tg_file.file_path
        if not file_url.startswith("http"):
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_url}"

        # Download file
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            resp = await http_client.get(file_url)
            resp.raise_for_status()
            file_bytes = resp.content

        # Extract text based on file type
        doc_text = ""
        if ext == ".pdf":
            try:
                import fitz  # PyMuPDF
                pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
                for page in pdf_doc:
                    doc_text += page.get_text()
                pdf_doc.close()
            except ImportError:
                logger.error("[DOC] PyMuPDF not installed, cannot read PDF")
                await update.message.reply_text(
                    "Library PDF belum terinstall di server.\n"
                    "Coba kirim dalam format .txt atau .docx, atau copy-paste isinya langsung."
                )
                return
            except Exception as e:
                logger.error(f"[DOC] PDF read error: {e}")
                await update.message.reply_text(f"Gagal membaca PDF: {e}")
                return
        elif ext in (".doc", ".docx"):
            try:
                import docx as python_docx
                doc_file = python_docx.Document(io.BytesIO(file_bytes))
                doc_text = "\n".join(p.text for p in doc_file.paragraphs)
            except ImportError:
                logger.error("[DOC] python-docx not installed")
                await update.message.reply_text(
                    "Library DOCX belum terinstall di server.\n"
                    "Coba kirim dalam format .txt atau .pdf."
                )
                return
        else:
            doc_text = file_bytes.decode("utf-8", errors="replace")

        doc_text = doc_text.strip()
        if not doc_text:
            await update.message.reply_text("Dokumen kosong atau tidak bisa dibaca.")
            return

        logger.info(f"[DOC] Extracted {len(doc_text)} chars from {file_name}")

        # Use Claude to analyze — detect chapters and summarize
        claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Send full doc (up to 50k chars for Claude context)
        analysis_text_input = doc_text[:50000]

        analysis = claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": f"""Analisis dokumen berikut secara menyeluruh.

DOKUMEN:
\"\"\"{analysis_text_input}\"\"\"

TUGAS:
1. Identifikasi topik utama dokumen
2. Ringkasan singkat (2-3 kalimat)
3. Deteksi SEMUA bab/chapter/section dalam dokumen. Untuk setiap bab, berikan judul dan ringkasan singkat isi bab tersebut.

Respond dalam JSON (tanpa markdown code block):
{{
  "topik": "topik utama",
  "ringkasan": "ringkasan 2-3 kalimat",
  "chapters": [
    {{"chapter_num": 1, "title": "judul bab", "summary": "ringkasan isi bab 1-2 kalimat"}},
    {{"chapter_num": 2, "title": "judul bab", "summary": "ringkasan isi bab"}},
    ...
  ]
}}"""}],
        )
        analysis_text = analysis.content[0].text.strip()
        analysis_data = safe_json_loads(analysis_text)

        if not analysis_data:
            analysis_data = {"topik": "Dokumen yang diupload", "ringkasan": doc_text[:200], "chapters": []}

        topik = analysis_data.get("topik", "")
        ringkasan = analysis_data.get("ringkasan", "")
        chapters = analysis_data.get("chapters", [])

        # Show analysis with chapters
        preview = f"📋 *Hasil Analisis Dokumen:*\n\n"
        preview += f"*Topik:* {topik}\n"
        if ringkasan:
            preview += f"*Ringkasan:* {ringkasan}\n"
        if chapters:
            preview += f"\n*Ditemukan {len(chapters)} bab:*\n"
            for ch in chapters:
                preview += f"  {ch.get('chapter_num', '?')}. {ch.get('title', '?')}\n"
        preview += f"\n_Total: {len(doc_text)} karakter dibaca_\n"

        # Truncate preview if too long for Telegram
        if len(preview) > 4000:
            preview = preview[:3990] + "..."

        await update.message.reply_text(preview, parse_mode="Markdown")

        # Save doc data to session, ask for brand
        session = get_session(context)
        session["_doc_text"] = doc_text
        session["_doc_topik"] = topik
        session["_doc_chapters"] = chapters
        session["_doc_analysis"] = analysis_data
        session["state"] = STATE_WAIT_DOC_BRAND

        # If caption contains brand name, auto-detect
        if caption:
            known = get_all_known_brands()
            known_lower = {b.lower(): b for b in known}
            for word in caption.split():
                if word.lower() in known_lower:
                    session["brand"] = known_lower[word.lower()]
                    break

        if session.get("brand"):
            # Brand sudah diketahui, langsung tanya content type via buttons
            session["state"] = STATE_WAIT_DOC_CONTENT_TYPE
            keyboard = [
                [InlineKeyboardButton("Carousel (7 slide)", callback_data="doctype:Carousel")],
                [InlineKeyboardButton("Reels (30-60 detik)", callback_data="doctype:Reel")],
                [InlineKeyboardButton("Single Post", callback_data="doctype:Single Post")],
            ]
            await update.message.reply_text(
                f"Brand: *{session['brand']}*\n\nMau dijadikan konten tipe apa?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            # Tampilkan brand sebagai buttons
            guidelines = load_brand_guidelines()
            keyboard = []
            row = []
            for i, brand_name in enumerate(guidelines.keys()):
                row.append(InlineKeyboardButton(brand_name, callback_data=f"docbrand:{brand_name}"))
                if len(row) == 2:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
            await update.message.reply_text(
                "Mau dijadikan konten untuk brand mana?",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    except Exception as e:
        logger.error(f"Error processing document: {e}", exc_info=True)
        await update.message.reply_text(f"Gagal proses dokumen:\n{str(e)}")


async def _process_doc_with_brand(source, context, session):
    """Process uploaded doc into branded script(s).
    If chapters detected, generates 1 content per chapter."""
    # Get reply function regardless of source type
    if hasattr(source, 'message') and source.message:
        reply = source.message.reply_text
    elif hasattr(source, 'get_bot'):
        reply = source.message.reply_text
    else:
        reply = source.reply_text

    brand = session["brand"]
    doc_text = session.get("_doc_text", "")
    doc_topik = session.get("_doc_topik", "Konten dari dokumen")
    chapters = session.get("_doc_chapters", [])
    content_type = session.get("_doc_content_type", "Carousel")

    guidelines = get_guidelines_for_brand(brand)
    guidelines_text = format_guidelines_text(brand, guidelines) if guidelines else ""

    # Build format instruction
    if content_type in ("Reel", "Reels"):
        format_instruction = """Format output sebagai SCRIPT REELS (30-60 detik):
OPENING (0-5 detik):
Shot: [deskripsi visual]
Narasi: [teks yang diucapkan]

POINT 1 (5-15 detik):
Shot: [deskripsi visual]
Narasi: [teks]

POINT 2 (15-30 detik):
Shot: [deskripsi visual]
Narasi: [teks]

POINT 3 (30-45 detik):
Shot: [deskripsi visual]
Narasi: [teks]

CTA (45-60 detik):
Shot: [deskripsi visual]
Narasi: [CTA sesuai brand]"""
    else:
        format_instruction = """Format output sebagai SCRIPT CAROUSEL 7 slide:
SLIDE 1 (COVER):
Judul: [hook menarik]
Teks: [teks pendek]
Visual: [arahan visual]

SLIDE 2-6:
Judul: [subjudul]
Teks: [konten edukatif/insight]
Visual: [arahan visual]

SLIDE 7 (CTA):
Judul: [ajakan]
Teks: [CTA sesuai brand guidelines]
Visual: [arahan visual]

Maks 50 kata per slide."""

    try:
        claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # If chapters detected, generate 1 content per chapter
        if chapters and len(chapters) > 1:
            total = len(chapters)
            await reply(
                f"📚 Ditemukan *{total} bab* dalam dokumen.\n"
                f"Memproses 1 konten {content_type} per bab untuk *{brand}*...\n"
                f"Ini akan memakan waktu beberapa menit.",
                parse_mode="Markdown",
            )

            generated = []
            for idx, chapter in enumerate(chapters):
                ch_num = chapter.get("chapter_num", idx + 1)
                ch_title = chapter.get("title", f"Bab {ch_num}")
                ch_summary = chapter.get("summary", "")

                await reply(f"🔄 [{idx+1}/{total}] Generating: {ch_title}...")

                # Find chapter content in doc_text
                # Use Claude to extract + generate in one call
                prompt = f"""Kamu adalah content strategist untuk brand "{brand}".

BRAND GUIDELINES:
{guidelines_text}

DOKUMEN LENGKAP:
\"\"\"{doc_text[:50000]}\"\"\"

TUGAS:
Dari dokumen di atas, fokus pada BAB {ch_num}: "{ch_title}".
Ringkasan bab: {ch_summary}

Buatkan script konten Instagram berdasarkan ISI BAB INI SAJA.
- Ambil pesan utama, insight, dan wisdom dari bab ini
- Sesuaikan tone dan bahasa dengan brand guidelines
- Buat hook yang menarik dan relevan dengan isi bab
- CTA di akhir HARUS sesuai brand guidelines

{format_instruction}

PENTING:
- Bahasa: {guidelines.get('bahasa', 'Indonesia') if guidelines else 'Indonesia'}
- Tone: {guidelines.get('tone', 'profesional') if guidelines else 'profesional'}
- CTA: {guidelines.get('cta', 'follow') if guidelines else 'follow'}
- Tulis script LENGKAP berdasarkan isi bab, bukan placeholder
- Jangan ulang isi bab secara verbatim, tapi adaptasi jadi konten yang engaging"""

                try:
                    msg = claude_client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=2000,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    script = msg.content[0].text.strip()

                    # Save to Sheet
                    headers, data_rows, _ = read_sheet_info()
                    col_map = get_header_index(headers)
                    content_id = get_next_content_id(data_rows, brand)

                    append_to_sheet(
                        headers, col_map, brand, content_id, "",
                        content_type, ch_title, "", script, "doc-upload",
                    )

                    if content_type == "Carousel":
                        update_sheet_visual_status(content_id, "Ready for Visual")

                    generated.append({"id": content_id, "title": ch_title})
                    logger.info(f"[DOC] Generated {content_id}: {brand} - {ch_title}")

                    import asyncio
                    await asyncio.sleep(1)  # Rate limit

                except Exception as e:
                    logger.error(f"[DOC] Error on chapter {ch_num}: {e}")
                    await reply(f"⚠️ Gagal generate bab {ch_num}: {str(e)[:100]}")

            # Summary
            if generated:
                summary = f"✅ *Selesai! {len(generated)} konten berhasil di-generate:*\n\n"
                for item in generated:
                    summary += f"  • {item['id']} — {item['title']}\n"
                summary += f"\nBrand: {brand} | Tipe: {content_type}\n"
                summary += "Semua tersimpan di Google Sheet tracker."
                if len(summary) > 4096:
                    summary = summary[:4090] + "..."
                await reply(summary, parse_mode="Markdown")

                # Notify team about batch
                await notify_batch_complete(context, brand, len(generated), content_type)
            else:
                await reply("❌ Tidak ada konten yang berhasil di-generate.")

        else:
            # Single content (no chapters or 1 chapter)
            await reply(
                f"🔄 Mengadaptasi dokumen menjadi script {content_type} untuk *{brand}*...",
                parse_mode="Markdown",
            )

            prompt = f"""Kamu adalah content strategist untuk brand "{brand}".

BRAND GUIDELINES:
{guidelines_text}

DOKUMEN SUMBER:
\"\"\"{doc_text[:50000]}\"\"\"

TUGAS:
Adaptasi dokumen di atas menjadi script konten Instagram yang siap pakai.
- Ambil insight dan poin kunci dari dokumen
- Sesuaikan tone, bahasa, dan CTA dengan brand guidelines
- Buat hook yang menarik di awal
- CTA di akhir HARUS sesuai brand guidelines

{format_instruction}

PENTING:
- Bahasa: {guidelines.get('bahasa', 'Indonesia') if guidelines else 'Indonesia'}
- Tone: {guidelines.get('tone', 'profesional') if guidelines else 'profesional'}
- CTA: {guidelines.get('cta', 'follow') if guidelines else 'follow'}
- Tulis script LENGKAP, bukan placeholder"""

            msg = claude_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            script = msg.content[0].text.strip()

            headers, data_rows, _ = read_sheet_info()
            col_map = get_header_index(headers)
            content_id = get_next_content_id(data_rows, brand)

            append_to_sheet(
                headers, col_map, brand, content_id, "",
                content_type, doc_topik, "", script, "doc-upload",
            )

            if content_type == "Carousel":
                update_sheet_visual_status(content_id, "Ready for Visual")

            header = (
                f"✅ Script berhasil di-generate!\n"
                f"Content ID: {content_id}\n"
                f"Brand: {brand} | Tipe: {content_type}\n"
                f"Topik: {doc_topik}\n\n"
            )

            full_reply_text = header + script
            if len(full_reply_text) <= 4096:
                await reply(full_reply_text)
            else:
                await reply(header + "(Script dikirim di pesan berikut)")
                for i in range(0, len(script), 4096):
                    await reply(script[i : i + 4096])

            logger.info(f"[DOC] Generated {content_id}: {brand} - {doc_topik}")
            await notify_new_content(context, content_id, brand, doc_topik, content_type)

    except Exception as e:
        logger.error(f"[DOC] Error generating script: {e}", exc_info=True)
        await reply(f"❌ Gagal generate script dari dokumen:\n{str(e)}")

    # Cleanup session
    for key in list(session.keys()):
        if key.startswith("_doc_"):
            session.pop(key, None)
    reset_session(context)


# ============================================================
# DAILY REPORT
# ============================================================
async def notify_team(context_or_bot, message):
    """Kirim notifikasi ke Telegram Group tim Sabitah."""
    group_id = TEAM_GROUP_ID
    if not group_id:
        logger.warning("[NOTIFY] TEAM_GROUP_ID belum di-set, skip notif")
        return

    try:
        bot = context_or_bot.bot if hasattr(context_or_bot, 'bot') else context_or_bot
        await bot.send_message(
            chat_id=int(group_id),
            text=message,
            parse_mode="Markdown",
        )
        logger.info("[NOTIFY] Team notification sent")
    except Exception as e:
        logger.error(f"[NOTIFY] Gagal kirim notif: {e}")
        try:
            bot = context_or_bot.bot if hasattr(context_or_bot, 'bot') else context_or_bot
            await bot.send_message(chat_id=int(group_id), text=message)
        except Exception:
            pass


async def notify_new_content(context_or_bot, content_id, brand, topik, content_type, owner="Dimas"):
    """Notifikasi tim saat konten baru di-generate."""
    # Assign PIC berdasarkan content type
    if content_type in ("Carousel", "Single Post"):
        next_pic = "Dedi (Editor)"
        next_action = "Review & buat visual design"
    elif content_type in ("Reel", "Reels"):
        next_pic = "Firman (Content Creator)"
        next_action = "Shooting & editing video"
    else:
        next_pic = "Tim"
        next_action = "Review konten"

    msg = (
        f"🆕 *Konten Baru Masuk!*\n\n"
        f"📌 *{content_id}* — {brand}\n"
        f"📝 {topik}\n"
        f"🎬 Tipe: {content_type}\n"
        f"👤 Dibuat: {owner}\n\n"
        f"➡️ *Next:* {next_pic}\n"
        f"📋 Action: {next_action}\n\n"
        f"_Cek tracker untuk detail script._"
    )
    await notify_team(context_or_bot, msg)


async def notify_batch_complete(context_or_bot, brand, count, content_type):
    """Notifikasi tim saat batch konten selesai (misal dari upload dokumen)."""
    msg = (
        f"📚 *Batch Konten Selesai!*\n\n"
        f"Brand: *{brand}*\n"
        f"Jumlah: *{count} konten* ({content_type})\n"
        f"Status: Script Done\n\n"
        f"👤 *Dedi* — review & assign visual\n"
        f"👤 *Asdi* — siapkan jadwal posting\n\n"
        f"_Cek tracker untuk detail._"
    )
    await notify_team(context_or_bot, msg)


async def notify_deadline_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Job harian: kirim reminder deadline ke group tim."""
    group_id = TEAM_GROUP_ID
    if not group_id:
        return

    try:
        headers, data_rows, _ = read_sheet_info()
        col_map = get_header_index(headers)
    except Exception:
        return

    today = datetime.now()
    urgent = []
    upcoming = []

    for row in data_rows:
        def col(field):
            idx = col_map.get(field)
            if idx is not None and idx < len(row):
                return row[idx].strip()
            return ""

        script_status = col("script_status").lower()
        visual_status = col("visual_status").lower()
        posting_status = col("posting_status").lower()
        date_str = col("date")
        brand = col("brand")
        topik = col("topik")[:40]
        cid = col("content_id")

        if posting_status in ("done", "posted"):
            continue

        if not date_str:
            continue

        parsed_date = None
        for fmt in ["%b %d", "%d %b", "%Y-%m-%d", "%d/%m/%Y", "%B %d"]:
            try:
                parsed_date = datetime.strptime(date_str, fmt).replace(year=today.year)
                break
            except ValueError:
                continue

        if not parsed_date:
            continue

        delta = (parsed_date.date() - today.date()).days

        if delta < 0:
            urgent.append(f"  🔴 *OVERDUE* [{cid}] {brand} — {topik}")
        elif delta == 0:
            urgent.append(f"  🟠 *HARI INI* [{cid}] {brand} — {topik}")
        elif delta == 1:
            upcoming.append(f"  🟡 *BESOK* [{cid}] {brand} — {topik}")
        elif delta <= 3:
            upcoming.append(f"  ⚪ *{delta} hari* [{cid}] {brand} — {topik}")

    if not urgent and not upcoming:
        return  # Tidak ada yang mendesak

    lines = [f"⏰ *Deadline Reminder — {today.strftime('%d %B %Y')}*\n"]

    if urgent:
        lines.append("🔥 *Mendesak:*")
        lines.extend(urgent[:15])
        lines.append("")

    if upcoming:
        lines.append("📅 *Segera:*")
        lines.extend(upcoming[:10])
        lines.append("")

    lines.append("_Cek tracker & update status ya tim!_")

    msg = "\n".join(lines)
    try:
        await context.bot.send_message(
            chat_id=int(group_id), text=msg, parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"[NOTIFY] Deadline reminder failed: {e}")


def build_daily_report():
    """Baca Google Sheet dan buat summary report."""
    try:
        headers, data_rows, brands_in_sheet = read_sheet_info()
        col_map = get_header_index(headers)
    except Exception as e:
        logger.error(f"[REPORT] Gagal baca sheet: {e}")
        return f"❌ Gagal baca Google Sheet:\n{e}"

    if not headers:
        return "📊 Sheet kosong, belum ada data."

    today = datetime.now()
    # Hitung per brand
    brand_stats = {}  # brand -> {done, in_progress, not_started}
    urgent = []       # deadline hari ini/besok tapi belum done
    week_generated = 0  # script generated minggu ini

    for row in data_rows:
        # Ambil values dengan safe indexing
        def col(field):
            idx = col_map.get(field)
            if idx is not None and idx < len(row):
                return row[idx].strip()
            return ""

        brand = col("brand") or "(No Brand)"
        script_status = col("script_status").lower()
        date_str = col("date")
        script_owner = col("script_owner").lower()

        # Stats per brand
        if brand not in brand_stats:
            brand_stats[brand] = {"done": 0, "in_progress": 0, "not_started": 0, "total": 0}
        brand_stats[brand]["total"] += 1

        if "done" in script_status:
            brand_stats[brand]["done"] += 1
        elif script_status in ("", "not started"):
            brand_stats[brand]["not_started"] += 1
        else:
            brand_stats[brand]["in_progress"] += 1

        # Cek deadline urgent (hari ini / besok)
        if date_str and "done" not in script_status:
            try:
                # Parse berbagai format tanggal
                parsed_date = None
                for fmt in ["%b %d", "%d %b", "%Y-%m-%d", "%d/%m/%Y", "%B %d"]:
                    try:
                        parsed_date = datetime.strptime(date_str, fmt)
                        # Tahun default = tahun ini
                        parsed_date = parsed_date.replace(year=today.year)
                        break
                    except ValueError:
                        continue
                if parsed_date:
                    delta = (parsed_date.date() - today.date()).days
                    if 0 <= delta <= 1:
                        topik = col("topik") or "(no topic)"
                        day_label = "HARI INI" if delta == 0 else "BESOK"
                        urgent.append(f"  ⚠️ [{day_label}] {brand} — {topik}")
            except Exception:
                pass

        # Script generated minggu ini (by Claude AI)
        if "done" in script_status and "claude" in script_owner:
            # Cek apakah date masih minggu ini
            try:
                parsed_date = None
                for fmt in ["%b %d", "%d %b", "%Y-%m-%d", "%d/%m/%Y", "%B %d"]:
                    try:
                        parsed_date = datetime.strptime(date_str, fmt).replace(year=today.year)
                        break
                    except ValueError:
                        continue
                if parsed_date:
                    days_ago = (today.date() - parsed_date.date()).days
                    if 0 <= days_ago <= 7:
                        week_generated += 1
            except Exception:
                pass

    # Format report
    lines = []
    lines.append("📊 *DAILY REPORT — Content Tracker*")
    lines.append(f"📅 {today.strftime('%A, %d %B %Y')}")
    lines.append("")

    # Per brand stats
    lines.append("📋 *Status per Brand:*")
    for brand in sorted(brand_stats.keys()):
        s = brand_stats[brand]
        lines.append(
            f"  *{brand}*: ✅ {s['done']} done · 🔄 {s['in_progress']} progress · "
            f"⬜ {s['not_started']} pending  ({s['total']} total)"
        )
    lines.append("")

    # Urgent deadlines
    if urgent:
        lines.append("🔥 *Deadline Mendesak:*")
        lines.extend(urgent)
    else:
        lines.append("✅ *Tidak ada deadline mendesak hari ini/besok*")
    lines.append("")

    # Weekly stats
    lines.append(f"🤖 *Script generated minggu ini:* {week_generated}")
    lines.append("")
    lines.append("—")
    lines.append("_Auto-generated by Sabitah Bot_")

    return "\n".join(lines)


async def send_daily_report(context: ContextTypes.DEFAULT_TYPE):
    """Kirim daily report ke chat ID dan team group."""
    report = build_daily_report()

    # Kirim ke REPORT_CHAT_ID (owner)
    chat_id = REPORT_CHAT_ID or context.bot_data.get("report_chat_id", "")
    if chat_id:
        try:
            await context.bot.send_message(
                chat_id=int(chat_id), text=report, parse_mode="Markdown",
            )
            logger.info("[REPORT] Daily report sent to owner")
        except Exception as e:
            logger.error(f"[REPORT] Gagal kirim report ke owner: {e}")
            try:
                await context.bot.send_message(chat_id=int(chat_id), text=report)
            except Exception:
                pass

    # Kirim juga ke team group
    group_id = TEAM_GROUP_ID or context.bot_data.get("team_group_id", "")
    if group_id and group_id != chat_id:
        try:
            await context.bot.send_message(
                chat_id=int(group_id), text=report, parse_mode="Markdown",
            )
            logger.info("[REPORT] Daily report sent to team group")
        except Exception as e:
            logger.error(f"[REPORT] Gagal kirim report ke group: {e}")
            try:
                await context.bot.send_message(chat_id=int(group_id), text=report)
            except Exception:
                pass


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual trigger: /report — kirim daily report sekarang."""
    chat_id = str(update.effective_chat.id)
    context.bot_data["report_chat_id"] = chat_id
    logger.info(f"[REPORT] Manual report requested by chat_id={chat_id}")

    report = build_daily_report()
    try:
        await update.message.reply_text(report, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(report)


async def team_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/team — register group ini sebagai team notification channel."""
    logger.info(f"[TEAM] /team command received from chat_id={update.effective_chat.id} type={update.effective_chat.type}")
    chat_id = str(update.effective_chat.id)
    chat_type = update.effective_chat.type

    if chat_type in ("group", "supergroup"):
        context.bot_data["team_group_id"] = chat_id
        global TEAM_GROUP_ID
        TEAM_GROUP_ID = chat_id

        team_list = "\n".join(f"  • {name} — {role}" for name, role in TEAM_MEMBERS.items())
        await update.message.reply_text(
            f"✅ Group ini terdaftar sebagai *Sabitah Team Channel*\n"
            f"Chat ID: `{chat_id}`\n\n"
            f"*Tim Sabitah:*\n{team_list}\n\n"
            f"Notifikasi yang akan dikirim ke sini:\n"
            f"  • Konten baru di-generate\n"
            f"  • Batch konten selesai\n"
            f"  • Deadline reminder (08:30 WIB)\n"
            f"  • Daily report (08:00 WIB)\n\n"
            f"_Set TEAM\\_GROUP\\_ID={chat_id} di Railway env untuk permanent._",
            parse_mode="Markdown",
        )
        logger.info(f"[TEAM] Group registered: {chat_id}")
    else:
        # Di private chat — cek apakah ada group ID di argument
        args = context.args
        if args and args[0].lstrip("-").isdigit():
            group_id = args[0]
            context.bot_data["team_group_id"] = group_id
            TEAM_GROUP_ID = group_id

            team_list = "\n".join(f"  • {name} — {role}" for name, role in TEAM_MEMBERS.items())

            # Test kirim pesan ke group
            try:
                await context.bot.send_message(
                    chat_id=int(group_id),
                    text=(
                        f"✅ *Sabitah Team Channel Terdaftar!*\n\n"
                        f"*Tim Sabitah:*\n{team_list}\n\n"
                        f"Notifikasi aktif:\n"
                        f"  • Konten baru di-generate\n"
                        f"  • Batch konten selesai\n"
                        f"  • Deadline reminder (08:30 WIB)\n"
                        f"  • Daily report (08:00 WIB)"
                    ),
                    parse_mode="Markdown",
                )
                await update.message.reply_text(
                    f"✅ Group `{group_id}` berhasil didaftarkan!\n"
                    f"Pesan test sudah dikirim ke group.\n\n"
                    f"_Set TEAM\\_GROUP\\_ID={group_id} di Railway env._",
                    parse_mode="Markdown",
                )
                logger.info(f"[TEAM] Group registered via private: {group_id}")
            except Exception as e:
                await update.message.reply_text(f"❌ Gagal kirim ke group {group_id}:\n{e}")
        else:
            # Instruksi cara dapat group ID
            await update.message.reply_text(
                "📋 *Cara Setup Team Notification:*\n\n"
                "*Cara 1 — Dari Group:*\n"
                "Ketik /team di Telegram Group\n\n"
                "*Cara 2 — Dari Sini:*\n"
                "1. Add bot @RawDataBot ke group kamu\n"
                "2. Lihat pesan dari RawDataBot — cari `chat id`\n"
                "3. Copy angka chat id (biasanya minus, misal -1001234567890)\n"
                "4. Ketik di sini: `/team -1001234567890`\n"
                "5. Remove @RawDataBot dari group\n\n"
                "Atau set langsung di Railway:\n"
                "  `TEAM_GROUP_ID = -1001234567890`",
                parse_mode="Markdown",
            )


async def chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/chatid — tampilkan chat ID untuk setup."""
    chat = update.effective_chat
    await update.message.reply_text(
        f"Chat ID: `{chat.id}`\n"
        f"Type: {chat.type}\n"
        f"Title: {chat.title or 'Private'}",
        parse_mode="Markdown",
    )


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
    print(f"  Report to: {REPORT_CHAT_ID or '(auto from /report)'}")
    print(f"  Team grp : {TEAM_GROUP_ID or '(set via /team in group)'}")
    print(f"  Brands   : {', '.join(guidelines.keys())}")
    print("=" * 60)
    print("  Fitur:")
    print("    - Terima pesan + voice + foto + dokumen (PDF/DOCX)")
    print("    - Brand guidelines per brand")
    print("    - QA Agent: auto-review + auto-revisi")
    print("    - Document: auto-detect chapters, 1 bab = 1 konten")
    print("    - Auto-save ke Google Sheet")
    print("    - Team notifications ke Telegram Group")
    print("    - Daily report jam 08:00 WIB")
    print("    - Deadline reminder jam 08:30 WIB")
    print("=" * 60)
    print("\n  Bot sedang berjalan... (Ctrl+C untuk stop)\n")

    request = HTTPXRequest(read_timeout=60, write_timeout=60, connect_timeout=60)
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).request(request).build()

    # Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("team", team_command))
    app.add_handler(CommandHandler("chatid", chatid_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Schedule daily report jam 08:00 WIB (01:00 UTC)
    from datetime import time as dt_time, timezone, timedelta
    wib = timezone(timedelta(hours=7))
    report_time = dt_time(hour=8, minute=0, second=0, tzinfo=wib)

    if app.job_queue:
        app.job_queue.run_daily(send_daily_report, time=report_time, name="daily_report")
        logger.info(f"[REPORT] Daily report scheduled at {report_time} WIB")

        # Deadline reminder jam 08:30 WIB
        reminder_time = dt_time(hour=8, minute=30, second=0, tzinfo=wib)
        app.job_queue.run_daily(notify_deadline_reminder, time=reminder_time, name="deadline_reminder")
        logger.info(f"[REPORT] Deadline reminder scheduled at {reminder_time} WIB")
    else:
        logger.warning("[REPORT] JobQueue not available, daily report disabled")

    app.run_polling(
        allowed_updates=["message", "callback_query", "my_chat_member", "chat_member"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
