"""
Rewrite all scripts NOT yet edited by Dimas to match his new style:
- Uses brand-specific script_format from brand_guidelines.json
- Emoji section markers 🎬 🎯 🎠
- Timestamp precise (0-5 detik, 5-20 detik)
- Ellipsis pacing
- Brand-specific signature phrases & positioning
- Skips: Oma Hera (already rewritten), Lebaran/Ramadan content, scripts already edited by Dimas
"""
import os
import sys
import time
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from googleapiclient.discovery import build
import anthropic

from telegram_bot import (
    read_sheet_info, get_header_index, fetch_doc_text,
    get_google_credentials, load_brand_guidelines,
    ANTHROPIC_API_KEY,
)

# CIDs Dimas already edited — skip these
DIMAS_EDITED = {
    'SB-001', 'SB-002', 'CT-002', 'CT-003', 'CT-004',
    'DF-001', 'DF-002', 'DF-003', 'HB-001', 'HB-002',
    'PB-001', 'PB-002', 'PB-003'
}

# Keywords to detect seasonal content in topic/hook
SEASONAL_KEYWORDS = ['lebaran', 'ramadan', 'mudik', 'pasca lebaran', 'setelah lebaran', 'habis lebaran']


def is_seasonal(topic, hook, brief):
    text = f'{topic} {hook} {brief}'.lower()
    return any(k in text for k in SEASONAL_KEYWORDS)


def build_rewrite_prompt(brand_info, brand_name, cid, topic, hook, content_type, original):
    fmt = brand_info.get('script_format', {})
    signature = brand_info.get('signature_phrases', [])
    positioning = brand_info.get('positioning', '')

    # Determine if this is reel or carousel
    ct_lower = content_type.lower()
    if 'carousel' in ct_lower:
        template = fmt.get('carousel_template', '')
        format_type = 'CAROUSEL'
    elif 'reel' in ct_lower or 'story' in ct_lower:
        template = fmt.get('reel_template', '')
        format_type = 'REEL'
    elif 'feed' in ct_lower or 'single' in ct_lower or 'post' in ct_lower:
        # Use carousel template for single feed post
        template = fmt.get('carousel_template', '')
        format_type = 'FEED POST'
    else:
        template = fmt.get('reel_template', '')
        format_type = content_type

    format_rules = fmt.get('format_rules', [])

    prompt = f"""Tulis ulang script konten Instagram untuk brand "{brand_name}" dengan GAYA BARU.

CONTENT INFO:
- Content ID: {cid}
- Topic: {topic}
- Hook: {hook}
- Type: {content_type} ({format_type})

BRAND POSITIONING:
{positioning}

BRAND TONE: {brand_info.get('tone', '')}
TARGET: {brand_info.get('target', '')}
BAHASA: {brand_info.get('bahasa', '')}
CTA STYLE: {brand_info.get('cta', '')}

SIGNATURE PHRASES (gunakan natural, jangan semua dipaksa):
{chr(10).join('- ' + p for p in signature)}

RULES PENTING:
{chr(10).join('- ' + r for r in brand_info.get('rules', []))}

TEMPLATE FORMAT (WAJIB ikuti struktur ini):
{template}

FORMAT RULES:
{chr(10).join('- ' + r for r in format_rules)}

SCRIPT LAMA (hanya sebagai referensi substansi — JANGAN ditiru style-nya):
{original if original else '(kosong)'}

INSTRUKSI:
1. Pertahankan TOPIK dan SUBSTANSI dari script lama (pesan utamanya tetap)
2. Ubah TOTAL style dan format-nya supaya match template baru
3. Pakai gaya Dimas:
   - Emoji section markers (🎬 🎯 🎠)
   - Timestamp precise (0-5 detik, 5-20 detik, dll) untuk Reels
   - Ellipsis "…" untuk pacing
   - Pattern "Bukan X… tapi Y"
   - "👉" marker di carousel untuk takeaway
   - Acting directions (pause), (beat), (senyum dikit)
4. TIDAK BOLEH pakai topik Lebaran/Ramadan/mudik/THR — kalau original punya itu, ganti jadi evergreen
5. Output HANYA script-nya, tanpa metadata header (tidak perlu "Content ID:", "Brand:", dll di awal)
6. Mulai langsung dari emoji marker atau SLIDE 1 (COVER)
"""
    return prompt


def update_doc_content(docs_service, doc_url, new_content, header_metadata):
    """Replace doc content with new script."""
    match = re.search(r"/document/d/([a-zA-Z0-9_-]+)", doc_url)
    if not match:
        return False
    doc_id = match.group(1)

    try:
        doc = docs_service.documents().get(documentId=doc_id).execute()
        end_index = doc["body"]["content"][-1]["endIndex"] - 1

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
    except Exception as e:
        print(f"    ERROR update: {e}")
        return False


def main():
    print("=" * 60)
    print("REWRITE UNEDITED SCRIPTS (New Dimas Style)")
    print("=" * 60)

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    guidelines = load_brand_guidelines()
    creds = get_google_credentials()
    docs_service = build("docs", "v1", credentials=creds)
    claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    headers, data, _ = read_sheet_info()
    col_map = get_header_index(headers)

    def col(row, name):
        idx = col_map.get(name)
        if idx is not None and idx < len(row):
            return row[idx].strip()
        return ""

    # Scan for scripts that need rewriting
    candidates = []
    for row in data:
        cid = col(row, "content_id")
        if not cid:
            continue

        brand = col(row, "brand")
        if brand == 'Oma Hera':
            continue  # Already rewritten with different rules

        ss = col(row, "script_status").lower()
        # Skip archived
        if 'archived' in ss or 'skip' in ss:
            continue

        # Skip Dimas already edited
        if cid in DIMAS_EDITED:
            continue

        script_link = col(row, "script_link")
        if not script_link:
            continue

        topic = col(row, "topik")
        hook = col(row, "hook")
        brief = col(row, "brief")

        # Skip seasonal (they should already be archived, but double-check)
        if is_seasonal(topic, hook, brief):
            continue

        # Only rewrite if Script Status suggests it has content ("Done", "Ready for Production")
        if ss not in ('done', 'ready for production'):
            continue

        candidates.append({
            'cid': cid,
            'brand': brand,
            'topic': topic,
            'hook': hook,
            'type': col(row, 'content_type'),
            'link': script_link,
        })

    print(f"Found {len(candidates)} scripts to rewrite")
    print()

    if not candidates:
        print("Nothing to rewrite!")
        return

    success = 0
    failed = 0
    errors = []

    for i, c in enumerate(candidates, 1):
        print(f"[{i}/{len(candidates)}] {c['cid']} | {c['brand']} | {c['type']}")
        print(f"  Topic: {c['topic'][:55]}")

        try:
            brand_info = guidelines.get(c['brand'])
            if not brand_info:
                print(f"  SKIP: brand '{c['brand']}' not in guidelines")
                failed += 1
                continue

            # Fetch original
            print("  Fetching original...")
            original = fetch_doc_text(docs_service, c['link'])

            # Build prompt and call Claude
            print("  Rewriting via Claude...")
            prompt = build_rewrite_prompt(
                brand_info, c['brand'], c['cid'],
                c['topic'], c['hook'], c['type'], original
            )

            msg = claude_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2500,
                messages=[{"role": "user", "content": prompt}],
            )
            new_script = msg.content[0].text.strip()

            # Build header
            header = (
                f"Content ID: {c['cid']}\n"
                f"Brand: {c['brand']}\n"
                f"Tipe: {c['type']}\n"
                f"Topik: {c['topic']}\n"
                f"Hook: {c['hook']}\n"
            )

            # Update doc
            print("  Writing to Google Doc...")
            ok = update_doc_content(docs_service, c['link'], new_script, header)
            if ok:
                success += 1
                print(f"  OK ({len(new_script)} chars)")
            else:
                failed += 1
                errors.append(f"{c['cid']}: failed to write doc")

            time.sleep(2)

        except Exception as e:
            failed += 1
            errors.append(f"{c['cid']}: {e}")
            print(f"  ERROR: {e}")

    print()
    print("=" * 60)
    print(f"COMPLETE")
    print("=" * 60)
    print(f"Success: {success}/{len(candidates)}")
    print(f"Failed:  {failed}/{len(candidates)}")
    if errors:
        print("\nErrors:")
        for e in errors[:20]:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
