"""İlk gerçek deneme çalışmasında (23 Kasım 2026) görülen sorunların testleri."""
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import ana, analiz, ayarlar, kaynaklar, telegram  # noqa: E402
from bot.model import Ilan  # noqa: E402

BUGUN = date(2026, 11, 23)


class AkademikRGTesti(unittest.TestCase):
    def test_resmi_gazete_akademik_ilan_elenir(self):
        # RG başlığı sadece kurum adı; akademik olduğu metinden anlaşılmalı
        metin = ("Üniversitemiz birimlerine 2547 sayılı Kanun uyarınca Doktor Öğretim Üyesi ve Öğretim Görevlisi "
                 "alınacaktır. Adayların ALES puanı ve yabancı dil puanı değerlendirilecektir. ") * 5
        self.assertTrue(analiz.akademik_mi("Düzce Üniversitesi Rektörlüğü – Resmî Gazete ilanı (23.11.2026)", metin))

    def test_isci_ilani_akademik_sayilmaz(self):
        metin = ("Üniversitemize 21 adet sürekli işçi alınacaktır. Noter kurası ile belirlenecektir. "
                 "Öğretim üyesi kadroları bu ilana dahil değildir. ") * 5
        self.assertFalse(analiz.akademik_mi("Ondokuz Mayıs Üniversitesi Rektörlüğü – Resmî Gazete ilanı", metin))


class SahteYanit:
    def __init__(self, icerik):
        self.content = icerik.encode()
        self.status_code = 200

    def raise_for_status(self):
        pass


class SahteOturum:
    def __init__(self, rss):
        self.rss = rss

    def get(self, url, timeout=None):
        return SahteYanit(self.rss)


class HaberTesti(unittest.TestCase):
    RSS = """<rss><channel>
    <item><title>Karayolları KPSS şartsız sürekli işçi alacak! - Yozgat Haber - Yozgat Son Dakika Haberleri</title>
      <link>https://a/1</link><source>Yozgat Haber</source></item>
    <item><title>Karayolları KPSS’siz Sürekli İşçi Alacak! En Az İlköğretim Mezunu ve Günlük 2.665 TL Yevmiye</title>
      <link>https://b/2</link><source>B Haber</source></item>
    <item><title>Sağlık Bakanlığı'ndan KPSS'siz işçi alımı ne zaman?</title><link>https://c/3</link></item>
    <item><title>Mustafa Çiftçi açıkladı: KPSS'siz ve 50-60 KPSS ile İçişleri Bakanlığı'na personel</title>
      <link>https://d/4</link></item>
    <item><title>Batman Belediyesi KPSS'siz işçi alımı yapacak</title><link>https://e/5</link></item>
    </channel></rss>"""

    def setUp(self):
        self.eski = kaynaklar.time.sleep
        kaynaklar.time.sleep = lambda s: None

    def tearDown(self):
        kaynaklar.time.sleep = self.eski

    def test_spekulasyon_elenir_site_adi_atilir(self):
        ilanlar = kaynaklar.haber_tara(SahteOturum(self.RSS), lambda a: True)
        basliklar = [i.baslik for i in ilanlar]
        self.assertIn("Karayolları KPSS şartsız sürekli işçi alacak!", basliklar)
        self.assertFalse(any("ne zaman" in b for b in basliklar))
        self.assertFalse(any("açıkladı" in b for b in basliklar))
        self.assertTrue(any("Batman" in b for b in basliklar))

    def test_ayni_ilanin_farkli_haberleri_tek_mesaj(self):
        giden = []
        eski_g = telegram.gonder
        telegram.gonder = lambda m: (giden.append(m), len(giden))[1]
        ayarlar.MESAJ_ARASI_SANIYE = 0
        ayarlar.DURUM_DOSYASI = os.path.join(tempfile.mkdtemp(), "d.json")
        try:
            ilanlar = kaynaklar.haber_tara(SahteOturum(self.RSS), lambda a: True)
            d = ana.durum_oku()
            ist = {k: 0 for k in ("taranan", "elenen", "kpssli", "tekrar", "gonderilen")}
            for i in ilanlar:
                ana.isle(i, d, BUGUN, 1_000_000, ist)
            ana.kuyrugu_gonder(d, ist)
        finally:
            telegram.gonder = eski_g
        karayollari = [m for m in giden if "Karayolları" in m]
        self.assertEqual(len(karayollari), 1, giden)
        self.assertEqual(len(giden), 2)  # Karayolları + Batman


class PdfYedekTesti(unittest.TestCase):
    def test_bozuk_pdf_hata_verir_ama_cokmez(self):
        with self.assertRaises(Exception):
            kaynaklar._pdf_metni(b"%PDF-1.4 bozuk dosya")


if __name__ == "__main__":
    unittest.main()


class IkiKanalTesti(unittest.TestCase):
    def test_yonlendirme(self):
        from bot import ayarlar, telegram
        eski = (ayarlar.TELEGRAM_KANAL, ayarlar.TELEGRAM_KANAL_KPSSLI, ayarlar.TELEGRAM_CHAT_ID)
        try:
            ayarlar.TELEGRAM_KANAL, ayarlar.TELEGRAM_KANAL_KPSSLI, ayarlar.TELEGRAM_CHAT_ID = "@siz", "@li", "1"
            self.assertEqual(telegram.hedef_sohbet("🟢 <b>KPSS ŞARTSIZ</b>"), "@siz")
            self.assertEqual(telegram.hedef_sohbet("🔵 <b>KPSS ŞARTLI</b>"), "@li")
            self.assertEqual(telegram.hedef_sohbet("🤖 özet"), "1")
        finally:
            ayarlar.TELEGRAM_KANAL, ayarlar.TELEGRAM_KANAL_KPSSLI, ayarlar.TELEGRAM_CHAT_ID = eski
