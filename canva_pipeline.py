"""
Canva Visual Pipeline — Semi-automated design workflow.

Flow:
1. Scan Sheet untuk rows dengan Visual Status = "Ready for Visual" & Canva Link kosong
2. Buat design di Canva (1080x1080 IG Square) dengan judul brand + topik
3. Tulis edit link asli ke kolom Canva Link
4. Update Visual Status → "Designed — Pending Review"
5. Kirim notifikasi ke Telegram (optional)

Usage:
    py canva_pipeline.py              # Process all ready rows
    py canva_pipeline.py --dry-run    # Preview tanpa create design
    py canva_pipeline.py --notify     # Kirim notifikasi ke Telegram
"""
import sys
import os
import json
import time
import argparse
import urllib.request
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram_bot import (
    read_sheet_info, get_header_index, ensure_sheet_headers,
    get_sheets_service, col_to_letter,
    SPREADSHEET_ID, SHEET_NAME, CANVA_ACCESS_TOKEN,
)

CANVA_API_BASE = "https://api.canva.com/rest/v1"

# Canva token bisa dari env atau dari telegram_bot
CANVA_TOKEN = os.environ.get("CANVA_ACCESS_TOKEN", "") or CANVA_ACCESS_TOKEN
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
REPORT_CHAT_ID = os.environ.get("REPORT_CHAT_ID", "")


def canva_create_design(title):
    """Create a 1080x1080 design via Canva Connect API. Returns (design_id, edit_url, view_url)."""
    if not CANVA_TOKEN:
        raise ValueError("CANVA_ACCESS_TOKEN tidak di-set. Set env var atau jalankan canva_oauth_manual.py dulu.")

    data = json.dumps({
        "design_type": {
            "type": "custom",
            "width": 1080,
            "height": 1080,
        },
        "title": title[:255],
    }).encode()

    req = urllib.request.Request(
        f"{CANVA_API_BASE}/designs",
        data=data,
        headers={
            "Authorization": f"Bearer {CANVA_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())

    design = result.get("design", {})
    return (
        design.get("id", ""),
        design.get("urls", {}).get("edit_url", ""),
        design.get("urls", {}).get("view_url", ""),
    )


def update_cell(service, col_idx, row_idx, value):
    """Update single cell. row_idx = 0-based data row index."""
    cell = f"'{SHEET_NAME}'!{col_to_letter(col_idx)}{row_idx + 3}"
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=cell,
        valueInputOption="RAW",
        body={"values": [[value]]},
    ).execute()
    return cell


def get_col(row, col_map, field):
    idx = col_map.get(field)
    if idx is not None and idx < len(row):
        return row[idx].strip()
    return ""


def send_telegram_notification(message):
    """Kirim notifikasi ke Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not REPORT_CHAT_ID:
        return False
    try:
        data = urllib.parse.urlencode({
            "chat_id": REPORT_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=data,
        )
        urllib.request.urlopen(req)
        return True
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Canva Visual Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't create designs")
    parser.add_argument("--notify", action="store_true", help="Send Telegram notification")
    args = parser.parse_args()

    print("=" * 60)
    print("  CANVA VISUAL PIPELINE")
    print("=" * 60)

    if not CANVA_TOKEN and not args.dry_run:
        print("\n[ERROR] CANVA_ACCESS_TOKEN tidak di-set!")
        print("Jalankan: py canva_oauth_manual.py")
        print("Atau set env: CANVA_ACCESS_TOKEN=...")
        return

    # Read sheet
    service = get_sheets_service()
    headers, data_rows, _ = read_sheet_info()
    headers = ensure_sheet_headers(headers)
    col_map = get_header_index(headers)

    print(f"\nTotal rows: {len(data_rows)}")

    # Find rows that need designs
    ready_rows = []
    for row_idx, row in enumerate(data_rows):
        visual_status = get_col(row, col_map, "visual_status").lower()
        canva_link = get_col(row, col_map, "canva_link")
        content_type = get_col(row, col_map, "content_type").lower()
        script_status = get_col(row, col_map, "script_status").lower()

        # Only process: Visual Status = "ready for visual" AND no Canva Link AND script done
        if (visual_status == "ready for visual"
                and not canva_link
                and script_status == "done"
                and content_type in ("carousel", "single post")):
            ready_rows.append((row_idx, row))

    print(f"Ready for design: {len(ready_rows)} rows\n")

    if not ready_rows:
        print("Tidak ada konten yang perlu dibuatkan design.")
        return

    # Process each row
    created = []
    errors = []

    for row_idx, row in ready_rows:
        brand = get_col(row, col_map, "brand")
        topik = get_col(row, col_map, "topik")
        content_id = get_col(row, col_map, "content_id")
        content_type = get_col(row, col_map, "content_type")

        title = f"{brand} — {topik}"[:100]
        print(f"  [{content_id}] {title}")

        if args.dry_run:
            print(f"    [DRY RUN] Would create design: {title}")
            created.append({"content_id": content_id, "brand": brand, "topik": topik, "edit_url": "(dry run)"})
            continue

        try:
            design_id, edit_url, view_url = canva_create_design(title)
            print(f"    Design created: {design_id}")
            print(f"    Edit: {edit_url[:80]}...")

            # Update Sheet: Canva Link
            update_cell(service, col_map["canva_link"], row_idx, edit_url)

            # Update Sheet: Visual Status → "Designed — Pending Review"
            update_cell(service, col_map["visual_status"], row_idx, "Designed — Pending Review")

            created.append({
                "content_id": content_id,
                "brand": brand,
                "topik": topik,
                "edit_url": edit_url,
                "view_url": view_url,
            })

            # Rate limit: 20 req/min for Canva API
            time.sleep(3)

        except Exception as e:
            print(f"    [ERROR] {e}")
            errors.append({"content_id": content_id, "error": str(e)})

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  RESULTS")
    print(f"{'=' * 60}")
    print(f"  Created: {len(created)}")
    print(f"  Errors:  {len(errors)}")

    if created:
        print(f"\n  Designs untuk di-review editor:")
        print(f"  {'─' * 56}")
        for item in created:
            print(f"  [{item['content_id']}] {item['brand']} — {item['topik'][:35]}")
            if not args.dry_run:
                print(f"    Edit: {item['edit_url'][:80]}...")
        print(f"  {'─' * 56}")

    if errors:
        print(f"\n  Errors:")
        for err in errors:
            print(f"  [{err['content_id']}] {err['error']}")

    # Telegram notification
    if args.notify and created and not args.dry_run:
        lines = [f"🎨 *Canva Pipeline — {len(created)} design baru!*\n"]
        for item in created:
            lines.append(f"• [{item['content_id']}] {item['brand']} — {item['topik'][:40]}")
            lines.append(f"  [Edit di Canva]({item['edit_url']})")
        lines.append(f"\nVisual Status: *Designed — Pending Review*")
        lines.append("Silakan review dan edit design-nya.")

        msg = "\n".join(lines)
        if send_telegram_notification(msg):
            print(f"\n  Telegram notification sent!")
        else:
            print(f"\n  Telegram notification failed (token/chat ID missing)")

    print()


if __name__ == "__main__":
    main()
