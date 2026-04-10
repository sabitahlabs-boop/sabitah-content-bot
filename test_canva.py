"""Test Canva API — verifikasi access token bekerja."""
import urllib.request
import json
import os

TOKEN = os.environ.get("CANVA_ACCESS_TOKEN", "")
if not TOKEN:
    TOKEN = input("Paste CANVA_ACCESS_TOKEN: ").strip()

API = "https://api.canva.com/rest/v1"

print("\n[1] Test: List designs...")
req = urllib.request.Request(
    f"{API}/designs",
    headers={"Authorization": f"Bearer {TOKEN}"},
)
try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    items = data.get("items", [])
    print(f"    OK! Ditemukan {len(items)} design(s).")
    for d in items[:3]:
        print(f"    - {d.get('title', 'Untitled')} | {d.get('urls', {}).get('view_url', 'N/A')}")
except urllib.error.HTTPError as e:
    print(f"    GAGAL: {e.code} - {e.read().decode()}")

print("\n[2] Test: Create design (1080x1080 IG Square)...")
create_data = json.dumps({
    "design_type": {
        "type": "custom",
        "width": 1080,
        "height": 1080,
    },
    "title": "Test Sabitah Bot - Hapus Saja",
}).encode()
req2 = urllib.request.Request(
    f"{API}/designs",
    data=create_data,
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    },
    method="POST",
)
try:
    with urllib.request.urlopen(req2) as resp:
        result = json.loads(resp.read())
    design = result.get("design", {})
    print(f"    OK! Design dibuat.")
    print(f"    Title : {design.get('title')}")
    print(f"    ID    : {design.get('id')}")
    print(f"    Edit  : {design.get('urls', {}).get('edit_url', 'N/A')}")
    print(f"    View  : {design.get('urls', {}).get('view_url', 'N/A')}")
    print(f"\n    Buka link Edit di browser untuk lihat design-nya!")
except urllib.error.HTTPError as e:
    print(f"    GAGAL: {e.code} - {e.read().decode()}")

input("\nTekan Enter untuk keluar...")
