"""
Fetch isi 5 Google Docs (script konten) menggunakan fungsi yang sama
dengan fetch_doc_text() di telegram_bot.py, lalu simpan ke extracted_scripts.txt.

Read-only — tidak menyentuh Sheet atau file lain.

Usage:
    py fetch_scripts_to_txt.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from googleapiclient.discovery import build
from telegram_bot import get_google_credentials, fetch_doc_text

# Documents to fetch
DOCS = [
    ("SB-008", "1YRgFI52HKXJkM1d0zJNazF_wLup5kFzzkj5a8suqVsI"),
    ("CT-027", "15Cumro1zOrcmJ2R2hnlFKhr8Baqdd67_3uCOJP1gR94"),
    ("LG-024", "1i6bnw0A71UWhwLhFB91UwgWg3pCtJwXZ-QAFp2Vb-8A"),
    ("DF-026", "13jUvt8Zm9-tE1WsuNRmYXjjxZ3xcE07bxlVEGXMoApE"),
    ("HB-010", "13AQ2MFY4jElUNNfDcr46ZcWmE6V6mwD8v3cOCVIv8IU"),
]

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extracted_scripts.txt")


def main():
    creds = get_google_credentials()
    docs_service = build("docs", "v1", credentials=creds)

    output_parts = []
    success = 0
    failed = 0

    for cid, doc_id in DOCS:
        print(f"Fetching {cid}...")
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        content = fetch_doc_text(docs_service, doc_url)

        if content:
            success += 1
            print(f"  OK ({len(content)} chars)")
        else:
            failed += 1
            print(f"  FAILED — empty content")
            content = "[EMPTY — failed to fetch]"

        output_parts.append(f"=== [{cid}] ===\n{content}\n")

    # Write all to single file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(output_parts))

    print()
    print("=" * 60)
    print(f"Success: {success}/{len(DOCS)}")
    print(f"Failed:  {failed}/{len(DOCS)}")
    print(f"Output:  {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
