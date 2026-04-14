"""
Build 'Production Tasks - Team' sheet:
- Shows scripts in pipeline: Ready for Production / Ready for Client Review / Need to Review
- 3 checkboxes (one per team member): Firman, Dedi, Asdi
- Each person marks their part done
- Color-coded by status
- Auto-sync will update Master Tracker when relevant boxes checked

Roles:
- Firman: Visual designer (Carousel/Feed/Post) → Canva design
- Dedi: Main editor (Reel/Story video) → Video editing
- Asdi: Social Media Specialist → Caption + Scheduling + Posting (all content)
"""
import os
import sys
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from telegram_bot import (
    read_sheet_info, get_header_index, get_sheets_service,
    SPREADSHEET_ID, SHEET_NAME,
)

NEW_SHEET_NAME = "Production Tasks - Team"
TODAY = datetime(2026, 4, 14)
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2, "": 3}
STATUS_RANK = {
    "ready for production": 0,
    "ready for client review": 1,
    "need to review": 2,
    "no progress": 3,
}


def parse_date(date_str):
    if not date_str:
        return None
    s = date_str.strip()
    s = re.sub(r"(\b[A-Z][a-z]{2})\s+\1", r"\1", s)
    for fmt in ["%d %b %Y", "%d %b", "%b %d, %Y", "%b %d", "%Y-%m-%d", "%d/%m/%Y"]:
        try:
            d = datetime.strptime(s, fmt)
            if d.year == 1900:
                d = d.replace(year=2026)
            return d
        except ValueError:
            continue
    return None


def get_role_needs(content_type):
    """Return which team members need to work on this content type.
    Returns dict with firman/dedi/asdi → True/False.
    """
    ct = content_type.lower()
    needs = {"firman": False, "dedi": False, "asdi": False}

    # Firman = visual designer (Carousel, Feed, Post)
    if any(k in ct for k in ("carousel", "feed", "single", "post")):
        needs["firman"] = True

    # Dedi = video editor (Reel, Story with video)
    if any(k in ct for k in ("reel", "story", "stories")):
        needs["dedi"] = True

    # Asdi = caption + posting (ALL content)
    needs["asdi"] = True

    return needs


def main():
    print("=" * 60)
    print("BUILD PRODUCTION TASKS SHEET — TEAM")
    print("=" * 60)

    headers, data, _ = read_sheet_info()
    col_map = get_header_index(headers)

    def col(row, name):
        idx = col_map.get(name)
        if idx is not None and idx < len(row):
            return row[idx].strip()
        return ""

    # Find scripts in production pipeline
    target_statuses = ("need to review", "ready for client review", "ready for production")
    pending = []
    for row in data:
        ss = col(row, "script_status").lower()
        if ss not in target_statuses:
            continue

        cid = col(row, "content_id")
        if not cid:
            continue

        date_obj = parse_date(col(row, "date"))
        days_until = (date_obj - TODAY).days if date_obj else 999

        ctype = col(row, "content_type")
        roles = get_role_needs(ctype)

        pending.append({
            "cid": cid,
            "brand": col(row, "brand"),
            "type": ctype,
            "topic": col(row, "topik"),
            "hook": col(row, "hook"),
            "date": col(row, "date"),
            "date_obj": date_obj,
            "days_until": days_until,
            "priority": col(row, "priority") or "Medium",
            "status": col(row, "script_status"),
            "script_link": col(row, "script_link"),
            "roles": roles,
        })

    # Sort: Ready for Production first, then by urgency
    pending.sort(key=lambda x: (
        STATUS_RANK.get(x["status"].lower(), 9),
        x["days_until"],
        PRIORITY_RANK.get(x["priority"].lower(), 3),
    ))

    print(f"Pipeline tasks: {len(pending)}")

    service = get_sheets_service()

    # Create or clear new sheet
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    existing_sheets = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}

    if NEW_SHEET_NAME in existing_sheets:
        new_sheet_id = existing_sheets[NEW_SHEET_NAME]
        service.spreadsheets().values().clear(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{NEW_SHEET_NAME}'",
        ).execute()
        print(f"Cleared existing sheet: {NEW_SHEET_NAME}")
    else:
        result = service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={
                "requests": [{
                    "addSheet": {
                        "properties": {
                            "title": NEW_SHEET_NAME,
                            "tabColor": {"red": 0.3, "green": 0.7, "blue": 0.9},
                            "gridProperties": {"rowCount": 300, "columnCount": 14},
                        }
                    }
                }]
            },
        ).execute()
        new_sheet_id = result["replies"][0]["addSheet"]["properties"]["sheetId"]
        print(f"Created new sheet: {NEW_SHEET_NAME} (ID: {new_sheet_id})")

    # Build rows
    sheet_headers = [
        "Firman ✓", "Dedi ✓", "Asdi ✓",
        "Status", "Priority", "Date", "Days",
        "Content ID", "Brand", "Type", "Topic", "Hook",
        "Script Link", "Notes"
    ]

    rows = [sheet_headers]
    for p in pending:
        # Days until post
        days = p["days_until"] if p["days_until"] != 999 else ""

        # Applicable roles = FALSE (checkbox unchecked, need to be checked)
        # Non-applicable roles = TRUE (auto-checked, already "done" because not needed)
        firman_val = False if p["roles"]["firman"] else True
        dedi_val = False if p["roles"]["dedi"] else True
        asdi_val = False if p["roles"]["asdi"] else True

        # Notes: what each person needs to do
        note_parts = []
        if p["roles"]["firman"]:
            note_parts.append("Firman: Canva visual")
        if p["roles"]["dedi"]:
            note_parts.append("Dedi: Video edit")
        if p["roles"]["asdi"]:
            note_parts.append("Asdi: Caption + posting")
        notes = " | ".join(note_parts)

        rows.append([
            firman_val,
            dedi_val,
            asdi_val,
            p["status"],
            p["priority"],
            p["date"],
            days,
            p["cid"],
            p["brand"],
            p["type"],
            p["topic"],
            p["hook"][:60],
            p["script_link"],
            notes,
        ])

    # Write data
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{NEW_SHEET_NAME}'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()
    print(f"Wrote {len(rows)} rows (1 header + {len(pending)} tasks)")

    # Format header, add checkboxes, conditional formatting
    requests = [
        # Bold header + freeze
        {
            "repeatCell": {
                "range": {"sheetId": new_sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.15, "green": 0.3, "blue": 0.5},
                        "textFormat": {
                            "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                            "bold": True,
                        },
                        "horizontalAlignment": "CENTER",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
            }
        },
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": new_sheet_id,
                    "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 3},
                },
                "fields": "gridProperties(frozenRowCount,frozenColumnCount)",
            }
        },
        # Column widths
        {
            "updateDimensionProperties": {
                "range": {"sheetId": new_sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 3},
                "properties": {"pixelSize": 75},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": new_sheet_id, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 4},
                "properties": {"pixelSize": 140},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": new_sheet_id, "dimension": "COLUMNS", "startIndex": 10, "endIndex": 11},
                "properties": {"pixelSize": 280},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": new_sheet_id, "dimension": "COLUMNS", "startIndex": 11, "endIndex": 12},
                "properties": {"pixelSize": 240},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": new_sheet_id, "dimension": "COLUMNS", "startIndex": 13, "endIndex": 14},
                "properties": {"pixelSize": 240},
                "fields": "pixelSize",
            }
        },
        # Conditional formatting:
        # 1. READY FOR PRODUCTION = green (ready to work)
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": new_sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": len(rows),
                        "startColumnIndex": 0,
                        "endColumnIndex": len(sheet_headers),
                    }],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": '=$D2="Ready for Production"'}],
                        },
                        "format": {
                            "backgroundColor": {"red": 0.85, "green": 0.95, "blue": 0.85},
                            "textFormat": {"bold": True},
                        },
                    },
                },
                "index": 0,
            }
        },
        # 2. READY FOR CLIENT REVIEW = blue (waiting)
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": new_sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": len(rows),
                        "startColumnIndex": 0,
                        "endColumnIndex": len(sheet_headers),
                    }],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": '=$D2="Ready for Client Review"'}],
                        },
                        "format": {
                            "backgroundColor": {"red": 0.85, "green": 0.92, "blue": 1.0},
                        },
                    },
                },
                "index": 1,
            }
        },
        # 3. NEED TO REVIEW = gray (not ready yet)
        {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": new_sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": len(rows),
                        "startColumnIndex": 0,
                        "endColumnIndex": len(sheet_headers),
                    }],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": '=$D2="Need to Review"'}],
                        },
                        "format": {
                            "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
                            "textFormat": {"foregroundColor": {"red": 0.5, "green": 0.5, "blue": 0.5}},
                        },
                    },
                },
                "index": 2,
            }
        },
    ]

    # Add checkbox validations for columns A, B, C (rows 2+)
    # Use non-strict so "-" placeholder still works
    for col_idx in range(3):
        requests.append({
            "setDataValidation": {
                "range": {
                    "sheetId": new_sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": len(rows) + 50,
                    "startColumnIndex": col_idx,
                    "endColumnIndex": col_idx + 1,
                },
                "rule": {
                    "condition": {"type": "BOOLEAN"},
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        })

    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": requests},
    ).execute()

    print()
    print("Sheet ready!")
    print(f"  URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid={new_sheet_id}")

    # Counts by status
    from collections import Counter
    status_counts = Counter(p["status"] for p in pending)
    print(f"\nBreakdown:")
    for s, c in status_counts.most_common():
        print(f"  {s}: {c}")

    # Counts by role
    role_counts = {"firman": 0, "dedi": 0, "asdi": 0}
    for p in pending:
        for role, needed in p["roles"].items():
            if needed:
                role_counts[role] += 1
    print(f"\nRole assignments:")
    for role, c in role_counts.items():
        print(f"  {role.capitalize()}: {c}")


if __name__ == "__main__":
    main()
