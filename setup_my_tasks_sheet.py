"""
Build 'My Tasks - Dimas' sheet:
- Lists all scripts at Script Status = 'Done' (pending Dimas approval)
- Sorted by urgency (date ASC, priority DESC)
- Has checkbox column to mark as done → triggers Apps Script to update Master Tracker
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

NEW_SHEET_NAME = "My Tasks - Dimas"
TODAY = datetime(2026, 4, 13)
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2, "": 3}


def parse_date(date_str):
    """Parse various date formats. Return datetime or None."""
    if not date_str:
        return None
    s = date_str.strip()
    # Clean up "1 Apr Apr" → "1 Apr"
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


def main():
    print("=" * 60)
    print("BUILD MY TASKS SHEET — DIMAS")
    print("=" * 60)

    headers, data, _ = read_sheet_info()
    col_map = get_header_index(headers)

    def col(row, name):
        idx = col_map.get(name)
        if idx is not None and idx < len(row):
            return row[idx].strip()
        return ""

    # Find Done scripts
    pending = []
    for row in data:
        if col(row, "script_status").lower() != "done":
            continue
        date_obj = parse_date(col(row, "date"))
        days_until = (date_obj - TODAY).days if date_obj else 999
        pending.append({
            "cid": col(row, "content_id"),
            "brand": col(row, "brand"),
            "type": col(row, "content_type"),
            "topic": col(row, "topik"),
            "hook": col(row, "hook"),
            "date": col(row, "date"),
            "date_obj": date_obj,
            "days_until": days_until,
            "priority": col(row, "priority") or "Medium",
            "script_link": col(row, "script_link"),
        })

    # Sort: urgent first (days_until ASC, then priority HIGH first)
    pending.sort(key=lambda x: (x["days_until"], PRIORITY_RANK.get(x["priority"].lower(), 3)))

    print(f"Pending Dimas approval: {len(pending)} scripts")

    service = get_sheets_service()

    # Step 1: Create new sheet (or clear if exists)
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    existing_sheets = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}

    if NEW_SHEET_NAME in existing_sheets:
        new_sheet_id = existing_sheets[NEW_SHEET_NAME]
        # Clear it
        service.spreadsheets().values().clear(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{NEW_SHEET_NAME}'",
        ).execute()
        print(f"Cleared existing sheet: {NEW_SHEET_NAME}")
    else:
        # Create new sheet
        result = service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={
                "requests": [{
                    "addSheet": {
                        "properties": {
                            "title": NEW_SHEET_NAME,
                            "tabColor": {"red": 1.0, "green": 0.6, "blue": 0.0},
                            "gridProperties": {"rowCount": 200, "columnCount": 11},
                        }
                    }
                }]
            },
        ).execute()
        new_sheet_id = result["replies"][0]["addSheet"]["properties"]["sheetId"]
        print(f"Created new sheet: {NEW_SHEET_NAME} (ID: {new_sheet_id})")

    # Step 2: Build rows
    sheet_headers = [
        "Done?", "Urgency", "Days Until", "Date", "Priority",
        "Content ID", "Brand", "Type", "Topic", "Hook", "Script Link"
    ]

    rows = [sheet_headers]
    for p in pending:
        urgency_label = (
            "OVERDUE" if p["days_until"] < 0
            else "TODAY" if p["days_until"] == 0
            else "URGENT" if p["days_until"] <= 3
            else "SOON" if p["days_until"] <= 7
            else "LATER"
        )
        rows.append([
            False,  # Done? checkbox
            urgency_label,
            p["days_until"] if p["days_until"] != 999 else "",
            p["date"],
            p["priority"],
            p["cid"],
            p["brand"],
            p["type"],
            p["topic"],
            p["hook"][:80],
            p["script_link"],
        ])

    # Step 3: Write data
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{NEW_SHEET_NAME}'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()
    print(f"Wrote {len(rows)} rows (1 header + {len(pending)} tasks)")

    # Step 4: Format header + add checkbox + conditional formatting
    requests = [
        # Bold header row + freeze
        {
            "repeatCell": {
                "range": {"sheetId": new_sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
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
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
        # Add checkbox to Done? column (col A, rows 2+)
        {
            "setDataValidation": {
                "range": {
                    "sheetId": new_sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": len(rows) + 50,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                },
                "rule": {
                    "condition": {"type": "BOOLEAN"},
                    "showCustomUi": True,
                    "strict": True,
                },
            }
        },
        # Column widths
        {
            "updateDimensionProperties": {
                "range": {"sheetId": new_sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 60},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": new_sheet_id, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
                "properties": {"pixelSize": 90},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": new_sheet_id, "dimension": "COLUMNS", "startIndex": 8, "endIndex": 9},
                "properties": {"pixelSize": 280},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": new_sheet_id, "dimension": "COLUMNS", "startIndex": 9, "endIndex": 10},
                "properties": {"pixelSize": 280},
                "fields": "pixelSize",
            }
        },
        # Conditional formatting: OVERDUE = red bg
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
                            "values": [{"userEnteredValue": '=$B2="OVERDUE"'}],
                        },
                        "format": {
                            "backgroundColor": {"red": 1.0, "green": 0.85, "blue": 0.85},
                            "textFormat": {"bold": True, "foregroundColor": {"red": 0.7, "green": 0, "blue": 0}},
                        },
                    },
                },
                "index": 0,
            }
        },
        # Conditional formatting: TODAY = orange
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
                            "values": [{"userEnteredValue": '=$B2="TODAY"'}],
                        },
                        "format": {
                            "backgroundColor": {"red": 1.0, "green": 0.92, "blue": 0.75},
                            "textFormat": {"bold": True},
                        },
                    },
                },
                "index": 1,
            }
        },
        # URGENT = yellow
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
                            "values": [{"userEnteredValue": '=$B2="URGENT"'}],
                        },
                        "format": {
                            "backgroundColor": {"red": 1.0, "green": 0.97, "blue": 0.85},
                        },
                    },
                },
                "index": 2,
            }
        },
        # Strike-through when Done? = TRUE
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
                            "values": [{"userEnteredValue": "=$A2=TRUE"}],
                        },
                        "format": {
                            "backgroundColor": {"red": 0.85, "green": 0.93, "blue": 0.83},
                            "textFormat": {"strikethrough": True, "foregroundColor": {"red": 0.5, "green": 0.5, "blue": 0.5}},
                        },
                    },
                },
                "index": 3,
            }
        },
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": requests},
    ).execute()

    print()
    print("Sheet ready!")
    print(f"  URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit#gid={new_sheet_id}")
    print(f"  Total tasks: {len(pending)}")
    overdue = sum(1 for p in pending if p['days_until'] < 0)
    today = sum(1 for p in pending if p['days_until'] == 0)
    urgent = sum(1 for p in pending if 0 < p['days_until'] <= 3)
    print(f"  OVERDUE: {overdue} | TODAY: {today} | URGENT (next 3 days): {urgent}")


if __name__ == "__main__":
    main()
