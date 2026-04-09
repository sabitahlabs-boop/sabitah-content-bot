import random
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

def generate_carousel_ideas(topik):
    templates = [
        {
            "judul": f"Panduan Lengkap {topik} untuk Pemula",
            "slides": [
                f"🔥 Panduan Lengkap {topik} untuk Pemula (Cover menarik)",
                f"Apa itu {topik}? Definisi singkat & kenapa ini penting di 2026",
                f"3 Kesalahan fatal yang sering dilakukan pemula di {topik}",
                f"Step 1: Langkah pertama memulai {topik} dari nol",
                f"Step 2: Tools & resource gratis untuk belajar {topik}",
                f"Step 3: Cara konsisten & mengukur progress kamu",
                f"💾 Save post ini! Follow untuk tips {topik} lainnya (CTA)",
            ],
        },
        {
            "judul": f"5 Mitos tentang {topik} yang Harus Kamu Tahu",
            "slides": [
                f"⚡ 5 Mitos tentang {topik} yang Masih Dipercaya! (Cover)",
                f"Mitos 1: '{topik} itu susah' — Faktanya: siapa pun bisa mulai",
                f"Mitos 2: 'Butuh modal besar' — Faktanya: bisa mulai dari Rp0",
                f"Mitos 3: 'Sudah terlambat untuk mulai' — Faktanya: belum!",
                f"Mitos 4: 'Harus punya bakat' — Faktanya: skill bisa dilatih",
                f"Mitos 5: 'Hasilnya lama' — Faktanya: tergantung strategi kamu",
                f"💡 Mana mitos yang pernah kamu percaya? Tulis di komentar! (CTA)",
            ],
        },
        {
            "judul": f"Rutinitas Harian untuk Menguasai {topik}",
            "slides": [
                f"⏰ Rutinitas Harian untuk Jago {topik} (Cover)",
                f"Pagi: 15 menit riset & baca update terbaru soal {topik}",
                f"Siang: Praktik langsung — learning by doing {topik}",
                f"Sore: Review & catat apa yang sudah dipelajari hari ini",
                f"Malam: Gabung komunitas & diskusi tentang {topik}",
                f"Weekend: Buat mini project / portofolio dari {topik}",
                f"🚀 Konsistensi > Motivasi. Share ke teman yang butuh ini! (CTA)",
            ],
        },
        {
            "judul": f"{topik}: Dulu vs Sekarang",
            "slides": [
                f"🔄 {topik}: Dulu vs Sekarang — Perubahannya Gila! (Cover)",
                f"Dulu: {topik} cuma dikenal segelintir orang",
                f"Sekarang: {topik} jadi skill yang dicari banyak perusahaan",
                f"Dulu: Belajar {topik} harus kursus mahal",
                f"Sekarang: Bisa belajar {topik} gratis dari mana saja",
                f"Apa yang bakal berubah di {topik} dalam 5 tahun ke depan?",
                f"📌 Setuju? Tag teman kamu yang perlu tahu ini! (CTA)",
            ],
        },
        {
            "judul": f"Red Flags di Dunia {topik} yang Wajib Dihindari",
            "slides": [
                f"🚩 Red Flags di {topik} — Jangan Sampai Kena! (Cover)",
                f"Red Flag 1: Janji hasil instan tanpa effort di {topik}",
                f"Red Flag 2: 'Guru' yang nggak punya portofolio nyata",
                f"Red Flag 3: Komunitas toxic yang meremehkan pemula",
                f"Red Flag 4: Metode belajar {topik} yang sudah outdated",
                f"Green Flag: Ciri mentor & sumber belajar {topik} yang bagus",
                f"✅ Save biar nggak lupa! Follow untuk tips {topik} (CTA)",
            ],
        },
        {
            "judul": f"Cara Menghasilkan Uang dari {topik}",
            "slides": [
                f"💰 Cara Menghasilkan Uang dari {topik} (Cover)",
                f"Peluang 1: Freelance — jual skill {topik} kamu ke klien",
                f"Peluang 2: Buat konten edukasi tentang {topik} di sosmed",
                f"Peluang 3: Jual produk digital (template, course, ebook)",
                f"Peluang 4: Konsultasi & mentoring untuk pemula di {topik}",
                f"Berapa potensi penghasilan? Breakdown realistis per bulan",
                f"🔥 Mau mulai dari mana? Comment 'MULAI'! (CTA)",
            ],
        },
        {
            "judul": f"Starter Pack Belajar {topik} di 2026",
            "slides": [
                f"🎒 Starter Pack {topik} 2026 — Semua yang Kamu Butuhkan (Cover)",
                f"Mindset: Growth mindset & siap gagal dulu sebelum berhasil",
                f"Tools gratis terbaik untuk belajar {topik} dari nol",
                f"Channel YouTube & akun IG yang wajib di-follow untuk {topik}",
                f"Komunitas & grup belajar {topik} yang aktif dan supportif",
                f"Target 30 hari pertama kamu belajar {topik}",
                f"📚 Bookmark sekarang! Share ke teman yang mau mulai (CTA)",
            ],
        },
    ]

    random.shuffle(templates)
    return templates[:5]


def main():
    print("=" * 60)
    print("   INSTAGRAM CAROUSEL IDEA GENERATOR")
    print("=" * 60)

    topik = input("\nMasukkan topik konten: ").strip()
    if not topik:
        print("Topik tidak boleh kosong!")
        return

    ideas = generate_carousel_ideas(topik)

    print(f"\n{'=' * 60}")
    print(f"   5 Ide Carousel Instagram untuk: \"{topik}\"")
    print(f"{'=' * 60}")

    for i, idea in enumerate(ideas, 1):
        print(f"\n{'─' * 60}")
        print(f"  IDE #{i}: {idea['judul']}")
        print(f"{'─' * 60}")
        for j, slide in enumerate(idea["slides"], 1):
            print(f"  Slide {j}: {slide}")

    print(f"\n{'=' * 60}")
    print("  Selesai! Pilih ide favorit kamu dan mulai desain 🎨")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
    input("\nTekan Enter untuk keluar...")
