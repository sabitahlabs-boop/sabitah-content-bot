"""Seed test data: 1 carousel per brand ke Google Sheet."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram_bot import (
    read_sheet_info, get_header_index, get_next_content_id,
    ensure_sheet_headers, append_to_sheet,
)

TEST_DATA = [
    {"brand": "Sabitah", "topik": "5 Tanda Brand Kamu Butuh Rebranding"},
    {"brand": "County", "topik": "Kesalahan Pembukuan yang Bikin UMKM Rugi"},
    {"brand": "LEGUS", "topik": "Hak Hukum yang Jarang Diketahui Pengusaha"},
    {"brand": "Defarchy", "topik": "Kenapa Sepeda Listrik Cocok Buat Commuting Jakarta"},
    {"brand": "Playpod", "topik": "Tempat Kerja Remote yang Bikin Fokus"},
    {"brand": "Happy Baby", "topik": "5 Produk Wajib untuk Bayi Baru Lahir"},
    {"brand": "Personal Brand Dimas", "topik": "Cara Gue Bangun 7 Bisnis Sekaligus"},
]


def main():
    print("Reading sheet...")
    headers, data_rows, brands = read_sheet_info()
    headers = ensure_sheet_headers(headers)
    col_map = get_header_index(headers)

    print(f"Headers: {len(headers)} columns")
    print(f"Existing rows: {len(data_rows)}")
    print()

    for item in TEST_DATA:
        brand = item["brand"]
        topik = item["topik"]
        content_id = get_next_content_id(data_rows, brand)

        # Placeholder script sebagai test data
        script = (
            f"SLIDE 1 (COVER):\n{topik}\n\n"
            f"SLIDE 2:\nPembukaan tentang {topik.lower()}\n\n"
            f"SLIDE 3:\nPoin utama #1\n\n"
            f"SLIDE 4:\nPoin utama #2\n\n"
            f"SLIDE 5:\nPoin utama #3\n\n"
            f"SLIDE 6:\nKesimpulan dan insight\n\n"
            f"SLIDE 7 (CTA):\nFollow untuk tips lainnya!"
        )

        print(f"  Adding: {brand} — {topik} ({content_id})")

        append_to_sheet(
            headers=headers,
            col_map=col_map,
            brand=brand,
            content_id=content_id,
            date_str="",
            content_type="Carousel",
            topik=topik,
            angle="",
            full_output=script,
            qa_status="seed data",
        )

        # Update data_rows untuk content_id berikutnya
        headers, data_rows, brands = read_sheet_info()
        col_map = get_header_index(headers)

    print(f"\nDone! {len(TEST_DATA)} rows ditambahkan ke Sheet.")


if __name__ == "__main__":
    main()
