"""
Generate scripts for tasks where the linked Google Doc is empty/404 or missing.

For each missing script:
1. Generate script content via Claude API based on brand guidelines + topic + hook
2. Create new Google Doc with formatted content
3. Update Master Tracker script_link column

Format adapts to content type:
- Carousel/Carousel (5/6/7 slides) → SLIDE 1 (COVER), SLIDE 2..., SLIDE N (CTA)
- Reel/Reels → HOOK + monolog/dialog
- Feed/Single Post → 1 caption + visual brief
- Stories → short copy
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from googleapiclient.discovery import build
import anthropic

from telegram_bot import (
    read_sheet_info, get_header_index, fetch_doc_text,
    get_google_credentials, load_brand_guidelines,
    get_sheets_service, col_to_letter,
    SPREADSHEET_ID, SHEET_NAME, ANTHROPIC_API_KEY,
)


def generate_script(claude_client, brand_info, brand_name, content_id, topic, hook, content_type):
    """Generate a script via Claude based on brand guidelines."""

    visual = brand_info.get("visual", {})
    fmt_section = brand_info.get("script_format", {})
    religious = brand_info.get("religious_context", "")

    # Determine format instructions based on content type
    ct_lower = content_type.lower()
    if "carousel" in ct_lower:
        slide_count = 7
        if "5" in ct_lower:
            slide_count = 5
        elif "6" in ct_lower:
            slide_count = 6
        format_instructions = f"""Format CAROUSEL Instagram - {slide_count} slide:

SLIDE 1 (COVER):
Judul: [headline yang catchy & hook-driven]
Teks: [supporting copy 1-2 kalimat]
Visual: [arahan visual]

SLIDE 2-{slide_count-1}:
Judul: [point per slide]
Teks: [penjelasan]
Visual: [arahan visual]

SLIDE {slide_count} (CTA):
Judul: [closing hook]
Teks: [CTA jelas sesuai brand]
Visual: [arahan visual]"""
    elif "reel" in ct_lower or "story" in ct_lower:
        format_instructions = """Format REEL Instagram - spoken word / dialog:

HOOK (visual + suasana): [arahan visual + tone audio]

[Speaker]: "[opening line yang nampar di 3 detik pertama]"
"[lanjutan...]"
"[story/teaching/insight]"
"[CTA reflektif/action]"

Total durasi sekitar 30-60 detik (sekitar 100-150 kata spoken)."""
    elif "feed" in ct_lower or "single" in ct_lower or "post" in ct_lower:
        format_instructions = """Format SINGLE POST / FEED Instagram:

VISUAL BRIEF:
[Deskripsi visual: layout, warna, elemen, mood]

HEADLINE:
[Headline besar di image]

CAPTION:
[Caption lengkap untuk Instagram, max 3 paragraf]

CTA:
[Action yang dimau dari audience]"""
    else:
        format_instructions = "Format bebas sesuai content type"

    # Build prompt
    prompt = f"""Tulis script konten Instagram untuk brand "{brand_name}".

CONTENT INFO:
- Content ID: {content_id}
- Topic: {topic}
- Hook: {hook}
- Type: {content_type}

BRAND GUIDELINES:
- Tone: {brand_info.get('tone', '')}
- Target audience: {brand_info.get('target', '')}
- CTA style: {brand_info.get('cta', '')}
- Bahasa: {brand_info.get('bahasa', '')}
"""

    if religious:
        prompt += f"- Religious context: {religious}\n"

    if brand_info.get('background'):
        prompt += f"- Background: {brand_info.get('background')}\n"

    prompt += f"""
RULES PENTING:
{chr(10).join('- ' + r for r in brand_info.get('rules', []))}
"""

    # If brand has script_format (e.g., Oma Hera), use it
    if fmt_section:
        prompt += f"""
SCRIPT FORMAT WAJIB (override default format):
{chr(10).join(s for s in fmt_section.get('structure', []))}

FORMAT RULES (yang DILARANG):
{chr(10).join('- ' + r for r in fmt_section.get('format_rules', []))}

Contoh pembuka: {fmt_section.get('example_opening', '')}
Contoh penutup: {fmt_section.get('example_closing', '')}
"""
    else:
        prompt += f"\nFORMAT OUTPUT:\n{format_instructions}\n"

    prompt += """
INSTRUKSI:
1. Tulis script yang ENGAGING, ON-BRAND, dan sesuai tone brand
2. Ikuti hook yang sudah disediakan (kalau ada) dan kembangkan
3. Pastikan CTA sesuai brand (soft sell / reflective / hard sell sesuai guidelines)
4. Output HANYA isi script-nya, tanpa metadata header (tidak perlu Content ID/Brand/Tipe di awal)
5. Gunakan bahasa yang sesuai brand guidelines
"""

    msg = claude_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def create_doc_with_script(docs_service, drive_service, brand, content_id, topic, content_type, hook, script_content):
    """Create new Google Doc with script. Returns doc URL."""
    title = hook[:80] if hook else topic[:80]
    doc_title = f"[{content_id}] {brand} - {title}"

    # Create doc
    doc = docs_service.documents().create(body={"title": doc_title}).execute()
    doc_id = doc["documentId"]

    # Build full content
    sep = "=" * 40
    full_text = (
        f"Content ID: {content_id}\n"
        f"Brand: {brand}\n"
        f"Tipe: {content_type}\n"
        f"Topik: {topic}\n"
        f"Hook: {hook}\n"
        f"{sep}\n\n"
        f"{script_content}\n"
    )

    # Insert text
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{
            "insertText": {"location": {"index": 1}, "text": full_text}
        }]},
    ).execute()

    # Make shareable (anyone with link can edit)
    try:
        drive_service.permissions().create(
            fileId=doc_id,
            body={"type": "anyone", "role": "writer"},
        ).execute()
    except Exception as e:
        print(f"    Permission warning: {e}")

    return f"https://docs.google.com/document/d/{doc_id}/edit"


def update_sheet_script_link(service, content_id, new_link):
    """Update script_link column in Master Tracker."""
    headers, data, _ = read_sheet_info()
    col_map = get_header_index(headers)
    link_col = col_map.get("script_link")
    cid_col = col_map.get("content_id", 1)

    if link_col is None:
        return False

    for row_idx, row in enumerate(data):
        if cid_col >= len(row):
            continue
        if row[cid_col].strip() == content_id:
            actual_row = row_idx + 3
            cell = f"'{SHEET_NAME}'!{col_to_letter(link_col)}{actual_row}"
            service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=cell,
                valueInputOption="RAW",
                body={"values": [[new_link]]},
            ).execute()
            return True
    return False


def main():
    print("=" * 60)
    print("GENERATE MISSING SCRIPTS")
    print("=" * 60)

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    guidelines = load_brand_guidelines()
    creds = get_google_credentials()
    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)
    sheets_service = get_sheets_service()
    claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Read sheet
    headers, data, _ = read_sheet_info()
    col_map = get_header_index(headers)

    def col(row, name):
        idx = col_map.get(name)
        if idx is not None and idx < len(row):
            return row[idx].strip()
        return ""

    # Find all Done scripts that are empty/missing
    print("Scanning sheet for missing scripts...")
    missing = []
    for row in data:
        if col(row, "script_status").lower() != "done":
            continue
        cid = col(row, "content_id")
        link = col(row, "script_link")

        if not link:
            missing.append({
                "cid": cid, "brand": col(row, "brand"), "topic": col(row, "topik"),
                "type": col(row, "content_type"), "hook": col(row, "hook"),
                "reason": "no_link",
            })
            continue

        # Check if doc has content
        text = fetch_doc_text(docs_service, link)
        if not text or len(text.strip()) < 100:
            missing.append({
                "cid": cid, "brand": col(row, "brand"), "topic": col(row, "topik"),
                "type": col(row, "content_type"), "hook": col(row, "hook"),
                "reason": "empty_or_404",
            })

    print(f"Found {len(missing)} missing scripts")
    print()

    if not missing:
        print("Nothing to do!")
        return

    # Generate each
    success = 0
    failed = 0
    errors = []

    for i, m in enumerate(missing, 1):
        print(f"[{i}/{len(missing)}] {m['cid']} | {m['brand']} | {m['type']}")
        print(f"  Topic: {m['topic'][:60]}")
        print(f"  Reason: {m['reason']}")

        try:
            brand_info = guidelines.get(m["brand"])
            if not brand_info:
                print(f"  SKIP: brand '{m['brand']}' not in guidelines")
                failed += 1
                errors.append(f"{m['cid']}: brand not in guidelines")
                continue

            # Generate
            print("  Generating script via Claude...")
            script = generate_script(
                claude_client, brand_info, m["brand"],
                m["cid"], m["topic"], m["hook"], m["type"]
            )

            # Create doc
            print("  Creating new Google Doc...")
            doc_url = create_doc_with_script(
                docs_service, drive_service,
                m["brand"], m["cid"], m["topic"], m["type"], m["hook"], script
            )

            # Update sheet
            print("  Updating Master Tracker script_link...")
            ok = update_sheet_script_link(sheets_service, m["cid"], doc_url)

            if ok:
                success += 1
                print(f"  OK ({len(script)} chars) -> {doc_url[:60]}...")
            else:
                failed += 1
                errors.append(f"{m['cid']}: failed to update sheet")
                print(f"  FAILED to update sheet")

            # Rate limit
            time.sleep(2)

        except Exception as e:
            failed += 1
            errors.append(f"{m['cid']}: {e}")
            print(f"  ERROR: {e}")

    print()
    print("=" * 60)
    print(f"COMPLETE")
    print("=" * 60)
    print(f"Success: {success}/{len(missing)}")
    print(f"Failed:  {failed}/{len(missing)}")
    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
