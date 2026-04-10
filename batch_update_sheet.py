"""Batch update Google Sheet: fix hooks, generate scripts, update statuses."""
import sys
import os
import re
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import anthropic
from telegram_bot import (
    read_sheet_info, get_header_index, ensure_sheet_headers,
    get_sheets_service, col_to_letter, get_guidelines_for_brand,
    format_guidelines_text, SPREADSHEET_ID, SHEET_NAME,
    ANTHROPIC_API_KEY,
)

CUTOFF_DATE = datetime(2026, 4, 10)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def update_cell(service, col_idx, row_idx, value):
    """Update single cell. row_idx is 0-based data row index (sheet row = row_idx + 3)."""
    cell = f"'{SHEET_NAME}'!{col_to_letter(col_idx)}{row_idx + 3}"
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=cell,
        valueInputOption="RAW",
        body={"values": [[value]]},
    ).execute()
    return cell


def parse_date(date_str):
    """Parse various date formats from sheet."""
    if not date_str:
        return None
    for fmt in ["%b %d", "%d %b", "%Y-%m-%d", "%d/%m/%Y", "%B %d", "%b %d, %Y", "%B %d, %Y"]:
        try:
            d = datetime.strptime(date_str.strip(), fmt)
            if d.year == 1900:
                d = d.replace(year=2026)
            return d
        except ValueError:
            continue
    return None


def get_col(row, col_map, field):
    idx = col_map.get(field)
    if idx is not None and idx < len(row):
        return row[idx].strip()
    return ""


def generate_hook(brand, topik):
    """Generate catchy hook using Claude API."""
    guidelines = get_guidelines_for_brand(brand)
    guidelines_text = format_guidelines_text(brand, guidelines) if guidelines else ""

    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=100,
        messages=[{"role": "user", "content": f"""Buatkan 1 hook/angle yang catchy untuk konten Instagram.

Brand: {brand}
Topik: {topik}
{guidelines_text}

Respond HANYA dengan hook-nya saja, 1 kalimat singkat (maks 15 kata), tanpa penjelasan tambahan."""}],
    )
    return msg.content[0].text.strip().strip('"')


def generate_carousel_script(brand, topik, hook):
    """Generate full 7-slide carousel script."""
    guidelines = get_guidelines_for_brand(brand)
    guidelines_text = format_guidelines_text(brand, guidelines) if guidelines else ""

    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": f"""Kamu adalah content strategist untuk brand "{brand}" di Indonesia.

BRAND GUIDELINES:
{guidelines_text}

Buatkan SCRIPT CAROUSEL Instagram 7 slide LENGKAP:

- Brand: {brand}
- Topik: {topik}
- Hook/Angle: {hook}

FORMAT:
SLIDE 1 (COVER):
Judul: [hook yang menarik]
Teks: [teks pendek untuk cover]
Visual: [arahan visual singkat]

SLIDE 2:
Judul: [subjudul]
Teks: [konten edukatif/insight]
Visual: [arahan visual]

... (sampai SLIDE 6)

SLIDE 7 (CTA):
Judul: [ajakan]
Teks: [CTA sesuai brand guidelines]
Visual: [arahan visual]

RULES:
- Bahasa HARUS sesuai guidelines: {guidelines.get('bahasa', 'Indonesia') if guidelines else 'Indonesia'}
- Tone HARUS sesuai guidelines: {guidelines.get('tone', 'professional') if guidelines else 'professional'}
- CTA di slide 7 HARUS: {guidelines.get('cta', 'follow untuk info lainnya') if guidelines else 'follow untuk info lainnya'}
- Maks 50 kata per slide
- Maks 1-2 emoji per slide
- Tulis script lengkap, BUKAN placeholder"""}],
    )
    return msg.content[0].text.strip()


def generate_reels_script(brand, topik, hook):
    """Generate reels script (talking points, shot-by-shot, 30-60 sec)."""
    guidelines = get_guidelines_for_brand(brand)
    guidelines_text = format_guidelines_text(brand, guidelines) if guidelines else ""

    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": f"""Kamu adalah content strategist untuk brand "{brand}" di Indonesia.

BRAND GUIDELINES:
{guidelines_text}

Buatkan SCRIPT REELS Instagram (durasi 30-60 detik):

- Brand: {brand}
- Topik: {topik}
- Hook/Angle: {hook}

FORMAT:
OPENING (0-5 detik):
Shot: [deskripsi visual]
Narasi: [teks yang diucapkan/ditampilkan]

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
Narasi: [CTA sesuai brand]

RULES:
- Bahasa: {guidelines.get('bahasa', 'Indonesia') if guidelines else 'Indonesia'}
- Tone: {guidelines.get('tone', 'professional') if guidelines else 'professional'}
- CTA: {guidelines.get('cta', 'follow') if guidelines else 'follow'}
- Tulis script lengkap, bukan placeholder
- Harus engaging dari detik pertama"""}],
    )
    return msg.content[0].text.strip()


def main():
    print("=" * 60)
    print("  BATCH UPDATE GOOGLE SHEET")
    print("=" * 60)

    service = get_sheets_service()

    # Step 1: Ensure headers
    print("\n[1] Ensuring headers...")
    headers, data_rows, brands = read_sheet_info()
    headers = ensure_sheet_headers(headers)
    col_map = get_header_index(headers)
    print(f"    Columns: {len(headers)}, Rows: {len(data_rows)}")
    print(f"    canva_link={col_map.get('canva_link')}, visual_status={col_map.get('visual_status')}")

    # Step 2: Fix empty hooks
    print("\n[2] Fixing empty hooks...")
    hook_count = 0
    for row_idx, row in enumerate(data_rows):
        hook_val = get_col(row, col_map, "hook")
        topik = get_col(row, col_map, "topik")
        brand = get_col(row, col_map, "brand")

        if not hook_val and topik and brand:
            print(f"    Generating hook: {brand} — {topik[:40]}...")
            try:
                hook = generate_hook(brand, topik)
                update_cell(service, col_map["hook"], row_idx, hook)
                print(f"    -> {hook}")
                hook_count += 1
                time.sleep(0.5)
            except Exception as e:
                print(f"    ERROR: {e}")
    print(f"    Fixed {hook_count} hooks.")

    # Step 3: Fix Script Owner
    print("\n[3] Fixing Script Owner...")
    owner_count = 0
    # Re-read to get fresh data
    headers, data_rows, brands = read_sheet_info()
    col_map = get_header_index(headers)

    owner_col = col_map.get("script_owner")
    if owner_col is not None:
        for row_idx, row in enumerate(data_rows):
            owner = get_col(row, col_map, "script_owner").lower()
            if owner in ("claude ai", "claude", "bot", "ai", ""):
                script_status = get_col(row, col_map, "script_status").lower()
                # Only update if script was done (generated by bot)
                if script_status == "done":
                    update_cell(service, owner_col, row_idx, "Dimas")
                    owner_count += 1
        print(f"    Updated {owner_count} rows to Script Owner = 'Dimas'.")
    else:
        print("    No script_owner column found.")

    # Step 4: Auto-generate Carousel scripts
    print("\n[4] Generating Carousel scripts...")
    # Re-read fresh data
    headers, data_rows, brands = read_sheet_info()
    col_map = get_header_index(headers)
    carousel_count = 0

    for row_idx, row in enumerate(data_rows):
        content_type = get_col(row, col_map, "content_type").lower()
        script_status = get_col(row, col_map, "script_status").lower()
        date_str = get_col(row, col_map, "date")
        brand = get_col(row, col_map, "brand")
        topik = get_col(row, col_map, "topik")
        hook_val = get_col(row, col_map, "hook")

        if content_type != "carousel":
            continue
        if script_status not in ("not started", ""):
            continue

        row_date = parse_date(date_str)
        if row_date and row_date > CUTOFF_DATE:
            continue

        if not brand or not topik:
            continue

        cid = get_col(row, col_map, "content_id")
        print(f"    [{cid}] {brand} — {topik[:40]}...")

        # Generate hook if empty
        if not hook_val:
            hook_val = generate_hook(brand, topik)
            update_cell(service, col_map["hook"], row_idx, hook_val)
            print(f"      Hook: {hook_val}")
            time.sleep(0.3)

        # Generate script
        try:
            script = generate_carousel_script(brand, topik, hook_val)
            print(f"      Script: {len(script)} chars")

            # Update cells
            if "script_notes" in col_map:
                update_cell(service, col_map["script_notes"], row_idx, script)
            if "script_status" in col_map:
                update_cell(service, col_map["script_status"], row_idx, "Done")
            if "script_owner" in col_map:
                update_cell(service, col_map["script_owner"], row_idx, "Dimas")
            if "visual_status" in col_map:
                update_cell(service, col_map["visual_status"], row_idx, "Ready for Visual")
            if "canva_link" in col_map:
                # Only set empty if currently empty
                current_link = get_col(row, col_map, "canva_link")
                if not current_link:
                    update_cell(service, col_map["canva_link"], row_idx, "")

            carousel_count += 1
            time.sleep(1)
        except Exception as e:
            print(f"      ERROR: {e}")

    print(f"    Generated {carousel_count} carousel scripts.")

    # Step 5: Auto-generate Reels scripts
    print("\n[5] Generating Reels scripts...")
    # Re-read fresh data
    headers, data_rows, brands = read_sheet_info()
    col_map = get_header_index(headers)
    reels_count = 0

    for row_idx, row in enumerate(data_rows):
        content_type = get_col(row, col_map, "content_type").lower()
        script_status = get_col(row, col_map, "script_status").lower()
        date_str = get_col(row, col_map, "date")
        brand = get_col(row, col_map, "brand")
        topik = get_col(row, col_map, "topik")
        hook_val = get_col(row, col_map, "hook")

        if content_type not in ("reel", "reels"):
            continue
        if script_status not in ("not started", ""):
            continue

        row_date = parse_date(date_str)
        if row_date and row_date > CUTOFF_DATE:
            continue

        if not brand or not topik:
            continue

        cid = get_col(row, col_map, "content_id")
        print(f"    [{cid}] {brand} — {topik[:40]}...")

        # Generate hook if empty
        if not hook_val:
            hook_val = generate_hook(brand, topik)
            update_cell(service, col_map["hook"], row_idx, hook_val)
            print(f"      Hook: {hook_val}")
            time.sleep(0.3)

        # Generate script
        try:
            script = generate_reels_script(brand, topik, hook_val)
            print(f"      Script: {len(script)} chars")

            if "script_notes" in col_map:
                update_cell(service, col_map["script_notes"], row_idx, script)
            if "script_status" in col_map:
                update_cell(service, col_map["script_status"], row_idx, "Done")
            if "script_owner" in col_map:
                update_cell(service, col_map["script_owner"], row_idx, "Dimas")
            if "visual_status" in col_map:
                update_cell(service, col_map["visual_status"], row_idx, "Skip - Video Manual")

            reels_count += 1
            time.sleep(1)
        except Exception as e:
            print(f"      ERROR: {e}")

    print(f"    Generated {reels_count} reels scripts.")

    # Step 6: Fix seed data / placeholder scripts
    print("\n[6] Fixing placeholder/seed data scripts...")
    headers, data_rows, brands = read_sheet_info()
    col_map = get_header_index(headers)
    fix_count = 0

    for row_idx, row in enumerate(data_rows):
        script_notes = get_col(row, col_map, "script_notes")
        script_status = get_col(row, col_map, "script_status").lower()
        brand = get_col(row, col_map, "brand")
        topik = get_col(row, col_map, "topik")
        content_type = get_col(row, col_map, "content_type").lower()
        hook_val = get_col(row, col_map, "hook")

        # Check if script is placeholder/seed data
        is_placeholder = (
            script_status == "done"
            and script_notes
            and ("seed data" in script_notes.lower()
                 or "Poin utama #" in script_notes
                 or len(script_notes) < 200)
        )

        if not is_placeholder or not brand or not topik:
            continue

        cid = get_col(row, col_map, "content_id")
        print(f"    [{cid}] Fixing: {brand} — {topik[:40]}...")

        try:
            if content_type in ("reel", "reels"):
                script = generate_reels_script(brand, topik, hook_val or topik)
                vs = "Skip - Video Manual"
            else:
                script = generate_carousel_script(brand, topik, hook_val or topik)
                vs = "Ready for Visual"

            if "script_notes" in col_map:
                update_cell(service, col_map["script_notes"], row_idx, script)
            if "visual_status" in col_map:
                update_cell(service, col_map["visual_status"], row_idx, vs)
            if "script_owner" in col_map:
                update_cell(service, col_map["script_owner"], row_idx, "Dimas")

            fix_count += 1
            print(f"      Replaced with {len(script)} chars")
            time.sleep(1)
        except Exception as e:
            print(f"      ERROR: {e}")

    print(f"    Fixed {fix_count} placeholder scripts.")

    print("\n" + "=" * 60)
    print("  DONE!")
    print(f"  Hooks fixed: {hook_count}")
    print(f"  Script Owner updated: {owner_count}")
    print(f"  Carousel scripts: {carousel_count}")
    print(f"  Reels scripts: {reels_count}")
    print(f"  Placeholder fixed: {fix_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
