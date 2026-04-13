"""
Rewrite all Oma Hera scripts to match the new brand guidelines:
- Christian context (Tuhan, Yesus, Injil, ayat Alkitab spesifik)
- Indonesian only (no English mid-script)
- Spoken word format (no markdown bold)
- Visual cues only in HOOK
- Closing blessing: "Tuhan memberkati cucu Oma"
- Reverent, contemplative tone

For each script:
1. Read existing script from Google Doc
2. Use Claude API to rewrite per new guidelines
3. Write back to the same Google Doc (replace content)
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from googleapiclient.discovery import build
import anthropic

from telegram_bot import (
    read_sheet_info, get_header_index, fetch_doc_text,
    get_google_credentials, load_brand_guidelines,
    ANTHROPIC_API_KEY,
)


def rewrite_script(claude_client, brand_info, content_id, topic, hook, original_script):
    """Use Claude to rewrite a script per new guidelines."""

    visual = brand_info.get("visual", {})
    fmt = brand_info.get("script_format", {})

    prompt = f"""Tulis ulang script Reels Instagram untuk brand "Oma Hera" sesuai brand guidelines yang BARU di bawah.

CONTENT ID: {content_id}
TOPIC: {topic}
HOOK ASLI (kalau ada): {hook}

SCRIPT LAMA (sebagai referensi konten — JANGAN ditiru style-nya):
{original_script}

BRAND GUIDELINES OMA HERA (BARU):
- Tone: {brand_info.get('tone', '')}
- Target: {brand_info.get('target', '')}
- Bahasa: {brand_info.get('bahasa', '')}
- Background tokoh: {brand_info.get('background', '')}
- Religious context: {brand_info.get('religious_context', '')}

RULES PENTING:
{chr(10).join('- ' + r for r in brand_info.get('rules', []))}

SCRIPT FORMAT YANG WAJIB:
{chr(10).join(s for s in fmt.get('structure', []))}

FORMAT RULES (yang DILARANG):
{chr(10).join('- ' + r for r in fmt.get('format_rules', []))}

CONTOH PEMBUKA:
{fmt.get('example_opening', '')}

CONTOH PENUTUP:
{fmt.get('example_closing', '')}

REFERENSI STYLE — INI YANG DIINGINKAN (script asli dari client):

HOOK (visual + suara pelan) (visual berita: wabah penyakit, konflik, perang — cepat, tidak terlalu lama)
OMA HERA: "Cucu Oma… kita harus jujur mengakui satu hal: dunia hari ini memang sudah tidak baik-baik saja."
"Di berbagai tempat, kita melihat perang. Kita mendengar berita tentang wabah penyakit yang terus berkembang. Semua ini bukan cerita jauh… tapi ada di depan mata kita."
"Dan Oma teringat… ternyata semua ini sudah tertulis di Alkitab."
"Yesus sendiri berkata dalam Injil Matius 24:7: 'Akan timbul bangsa melawan bangsa dan kerajaan melawan kerajaan, dan akan ada kelaparan serta wabah penyakit di berbagai tempat.'"
"Cucu Oma… ayat ini bukan ditulis untuk menakut-nakuti kita."
"Justru ini adalah panggilan supaya kita hidup lebih bertanggung jawab."
"Jangan takut… tetapi hadapi dengan bijak."
"Jaga kesehatan jasmani kita. Jaga kesehatan mental kita. Dan jangan lupa, jaga kesehatan rohani kita."
"Terus belajar hal-hal baru. Terus bertumbuh. Dan terus peduli satu sama lain."
"Cucu Oma… kita memang tidak tahu kapan semua ini akan berakhir. Tapi satu hal pasti: Tuhan tetap memegang kendali atas hidup kita."
"Berjaga-jagalah tanpa panik. Berimanlah tanpa menutup mata."
"Tuhan memberkati cucu Oma."

INSTRUKSI:
1. Pertahankan TOPIK dan SUBSTANSI dari script lama (jangan ubah pesan utamanya)
2. Tapi ubah TOTAL style-nya supaya match style referensi di atas
3. Cite ayat Alkitab yang RELEVAN dan SPESIFIK untuk topiknya (bukan ayat acak — yang benar-benar nyambung sama topik)
4. Indonesia murni — JANGAN ada English
5. Tutup dengan blessing variant "Tuhan memberkati cucu Oma"
6. Output HANYA script-nya, tanpa metadata, tanpa header "Content ID:" dll
7. Mulai langsung dari "HOOK (visual + ...)\\nOMA HERA: \\"...\\""
"""

    msg = claude_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def update_doc_content(docs_service, doc_url, new_content, header_metadata):
    """Replace doc content with new script."""
    import re
    match = re.search(r"/document/d/([a-zA-Z0-9_-]+)", doc_url)
    if not match:
        return False
    doc_id = match.group(1)

    # Get current doc to find end index
    doc = docs_service.documents().get(documentId=doc_id).execute()
    end_index = doc["body"]["content"][-1]["endIndex"] - 1

    # Build full text with metadata header (matching existing format)
    full_text = (
        f"{header_metadata}"
        f"========================================\n\n"
        f"{new_content}\n"
    )

    requests = []
    if end_index > 1:
        requests.append({
            "deleteContentRange": {
                "range": {"startIndex": 1, "endIndex": end_index}
            }
        })
    requests.append({
        "insertText": {"location": {"index": 1}, "text": full_text}
    })

    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": requests},
    ).execute()
    return True


def main():
    print("=" * 60)
    print("REWRITE OMA HERA SCRIPTS — Match new brand guidelines")
    print("=" * 60)

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    guidelines = load_brand_guidelines()
    brand_info = guidelines.get("Oma Hera")
    if not brand_info:
        print("ERROR: Oma Hera brand not found in guidelines")
        sys.exit(1)

    print(f"Religious context: {brand_info.get('religious_context', 'N/A')[:80]}...")
    print()

    # Read sheet
    headers, data, _ = read_sheet_info()
    col_map = get_header_index(headers)

    def col(row, name):
        idx = col_map.get(name)
        if idx is not None and idx < len(row):
            return row[idx].strip()
        return ""

    # Find all Oma Hera scripts with script_link
    oh_scripts = []
    for row in data:
        if col(row, "brand").lower() == "oma hera" and col(row, "script_link"):
            oh_scripts.append({
                "cid": col(row, "content_id"),
                "topic": col(row, "topik"),
                "type": col(row, "content_type"),
                "hook": col(row, "hook"),
                "link": col(row, "script_link"),
            })

    print(f"Found {len(oh_scripts)} Oma Hera scripts to rewrite")
    print()

    # Setup clients
    creds = get_google_credentials()
    docs_service = build("docs", "v1", credentials=creds)
    claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    success = 0
    failed = 0
    errors = []

    for i, script in enumerate(oh_scripts, 1):
        print(f"[{i}/{len(oh_scripts)}] {script['cid']}: {script['topic'][:50]}")

        try:
            # Fetch original
            print("  Fetching original...")
            original = fetch_doc_text(docs_service, script["link"])
            if not original:
                print("  SKIP: empty original")
                failed += 1
                errors.append(f"{script['cid']}: empty original")
                continue

            # Rewrite via Claude
            print("  Rewriting via Claude...")
            new_script = rewrite_script(
                claude_client, brand_info,
                script["cid"], script["topic"], script["hook"], original
            )

            # Build header metadata
            header = (
                f"Content ID: {script['cid']}\n"
                f"Brand: Oma Hera\n"
                f"Tipe: {script['type']}\n"
                f"Topik: {script['topic']}\n"
                f"Hook: {script['hook']}\n"
            )

            # Update doc
            print("  Writing to Google Doc...")
            ok = update_doc_content(docs_service, script["link"], new_script, header)
            if ok:
                success += 1
                print(f"  OK ({len(new_script)} chars)")
            else:
                failed += 1
                errors.append(f"{script['cid']}: failed to write doc")

            # Rate limit
            time.sleep(2)

        except Exception as e:
            failed += 1
            errors.append(f"{script['cid']}: {e}")
            print(f"  ERROR: {e}")

    print()
    print("=" * 60)
    print(f"REWRITE COMPLETE")
    print("=" * 60)
    print(f"Success: {success}/{len(oh_scripts)}")
    print(f"Failed:  {failed}/{len(oh_scripts)}")
    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
