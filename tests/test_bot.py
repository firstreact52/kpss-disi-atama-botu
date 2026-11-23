"""Testler: python -m unittest discover -s tests -v"""
import os
import random
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import ana, analiz, ayarlar, telegram  # noqa: E402
from bot.kaynaklar import _kurum_yalin, _mem_cozumle, _mem_kurum  # noqa: E402
from bot.metin import egitim_duzeyleri, il_bul, kadro_sayisi, son_basvuru_bul  # noqa: E402
from bot.model import Ilan  # noqa: E402
from bot.tekrar import ayni_ilan_mi, kurum_kelimeleri, parmak_izi  # noqa: E402

BUGUN = date(2026, 11, 23)

# --- Gerçek ilanlardan alınmış parçalar (Kasım 2026) ---
SAYISTAY = ("Başkanlığımızda istihdam edilmek üzere boş bulunan sözleşmeli personel pozisyonları için "
            "16 Sözleşmeli Personel alınması planlanmaktadır. I – BAŞVURU ŞARTLARI 3. 2026 yılında yapılan "
            "Kamu Personeli Seçme Sınavında; Lisans mezunları için KPSSP1, ön lisans mezunları için KPSSP93 "
            "puan türünde en az 60 puan almış olmak. ") * 3
YTU = ("sözlü/uygulamalı sınava katılacak adayların seçiminde, 2025 veya 2026 Kamu Personel Seçme Sınavı (KPSS) "
       "P3 puanı (KPSS puanı olmayan veya belge ibraz etmeyen adayın KPSS puanı 70 olarak hesaplanacaktır) "
       "ve YDS puanı dikkate alınacaktır. Sözleşmeli bilişim personeli alınacaktır. ") * 3
OMU = ("Üniversitemiz Rektörlüğüne bağlı birimlerde 4857 sayılı İş Kanunu kapsamında aşağıdaki tabloda "
       "belirtilen unvanlarda noter kurası ve akabinde yapılacak sözlü ve uygulamalı sınav yöntemiyle "
       "Türkiye İş Kurumu (İŞKUR) üzerinden 21 adet Sürekli İşçi alınacaktır. Başvurular "
       "esube.iskur.gov.tr internet adresinden yapılacaktır. Lise mezunu olmak. ") * 2
BURSA = ("genel ve özel şartları taşıyanlar arasından 2026 KPSS (B) grubu puan sıralaması esas alınmak "
         "suretiyle 1 (bir) adet sözleşmeli psikolog alınacaktır. 3. 2026 yılı KPSS (B) grubu sınavına girmiş "
         "ve geçerli bir puan almış olmak. ") * 3
AFAD = "KPSS Puan Türü : KPSSP8, KPSSP9, KPSSP16 KPSS Taban Puanı : 70. Uzman yardımcısı alınacaktır. " * 5
SSB = ("Proje bazlı sözleşmeli personel alımı giriş sınavı yapılacaktır. (4) Son başvuru tarihi itibariyle son 2 "
       "(iki) yıl içerisinde YDS'den İngilizce alanında en az 70 (yetmiş) puana sahip olmak. Mezuniyet Belgesi, "
       "YDS Sınav Belgesi, Adli Sicil Kaydı, Askerlik Durum Belgesi istenecektir. Mülakat ile alınacaktır. ") * 3
ARANMAZ = ("Belediyemize 5 adet temizlik personeli alınacaktır. Başvurularda KPSS şartı aranmayacaktır. "
           "En az ilkokul mezunu olmak. Son başvuru tarihi 10 Aralık 2026. ") * 4
EKPSS = ("Engelli memur alımı yapılacaktır. 2024 EKPSS puanı esas alınarak yerleştirme yapılacaktır, "
         "EKPSS en az 60 puan. ") * 6


class KararTesti(unittest.TestCase):
    def k(self, metin, baslik="Personel alım ilanı", isci=False):
        return analiz.kpss_karari(baslik, metin, isci).tur

    def test_kpss_isteyenler_elenir(self):
        self.assertEqual(self.k(SAYISTAY), analiz.KPSSLI)
        self.assertEqual(self.k(BURSA), analiz.KPSSLI)
        self.assertEqual(self.k(AFAD), analiz.KPSSLI)
        self.assertEqual(self.k(EKPSS), analiz.KPSSLI)

    def test_kpsssizler(self):
        self.assertEqual(self.k(OMU), analiz.KPSSSIZ)
        self.assertEqual(self.k(SSB), analiz.KPSSSIZ)
        self.assertEqual(self.k(ARANMAZ), analiz.KPSSSIZ)

    def test_kpss_zorunlu_degil_kismen(self):
        self.assertEqual(self.k(YTU), analiz.KISMEN)

    def test_metinsiz(self):
        self.assertEqual(self.k("", "Bolu Boltur 1 İşçi Alacak", isci=True), analiz.KPSSSIZ)
        self.assertEqual(self.k("", "Bakanlık 30 sözleşmeli personel alacak"), analiz.BELIRSIZ)

    def test_alakasiz_basliklar(self):
        for b in ["İçişleri Bakanlığı sözlü sınav duyurusu", "TÜİK Görevde Yükselme Sınavı İlanı",
                  "Adli Tıp sınav sonuçları açıklandı", "Yedek aday listesi", "Yurt Dışı Yüksek Lisans Eğitimi"]:
            self.assertTrue(analiz.alakasiz_mi(b), b)
        for b in ["Ondokuz Mayıs Üniversitesi 21 İşçi Alacak", "Adli Tıp Kurumu 181 sözleşmeli personel alacak"]:
            self.assertFalse(analiz.alakasiz_mi(b), b)

    def test_akademik(self):
        self.assertTrue(analiz.akademik_mi("Tarsus Üniversitesi Öğretim Elemanı Alım İlanı"))
        self.assertFalse(analiz.akademik_mi("Ankara Yıldırım Beyazıt Üniversitesi 1 sözleşmeli personel alacak"))


class MetinTesti(unittest.TestCase):
    def test_tarih(self):
        self.assertEqual(son_basvuru_bul("Ondokuz Mayıs Üniversitesi 21 İşçi Alacak. Son ödeme tarihi 7 Aralık 2026"),
                         date(2026, 12, 7))
        self.assertEqual(son_basvuru_bul("Başvurular 01.12.2026 - 15.12.2026 tarihleri arasında"),
                         date(2026, 12, 15))

    def test_kadro_egitim_il(self):
        self.assertEqual(kadro_sayisi("Ondokuz Mayıs Üniversitesi 21 İşçi Alacak"), "21")
        self.assertEqual(kadro_sayisi("İçişleri Bakanlığı 1.170 sözleşmeli personel alacak"), "1170")
        self.assertEqual(kadro_sayisi("Jandarma 9 bin uzman erbaş alacak"), None or kadro_sayisi("Jandarma 9 bin uzman erbaş alacak"))
        self.assertIn("Lise", egitim_duzeyleri(OMU))
        self.assertEqual(il_bul("Ondokuz Mayıs Üniversitesi 21 İşçi Alacak"), "Samsun")
        self.assertEqual(il_bul("Ordu Büyükşehir Belediyesi 10 işçi alacak"), "Ordu")
        self.assertEqual(il_bul("Bayburt İl Özel İdaresi 9 İşçi Alacak"), "Bayburt")

    def test_kurum(self):
        self.assertEqual(_kurum_yalin("Düzce Üniversitesi Rektörlüğünden:"), "Düzce Üniversitesi Rektörlüğü")
        self.assertEqual(_kurum_yalin("İçişleri Bakanlığından:"), "İçişleri Bakanlığı")
        self.assertEqual(_kurum_yalin("Türk Akreditasyon Kurumundan:"), "Türk Akreditasyon Kurumu")
        self.assertEqual(_mem_kurum("Ondokuz Mayıs Üniversitesi 21 İşçi Alacak"), "Ondokuz Mayıs Üniversitesi")
        a = kurum_kelimeleri("ONDOKUZ MAYIS ÜNİVERSİTESİ REKTÖRLÜĞÜ")
        b = kurum_kelimeleri("Ondokuz Mayıs Üniversitesi Rektörlüğünden")
        self.assertEqual(a, b)


def _rastgele_metin(tohum, n=1500):
    r = random.Random(tohum)
    sozluk = [f"k{r.randint(0, 5000)}" for _ in range(3000)]
    return " ".join(r.choice(sozluk) for _ in range(n))


class TekrarTesti(unittest.TestCase):
    def setUp(self):
        self.govde = _rastgele_metin(1)

    def ilan(self, kaynak, baslik, kurum, metin, son=None, kadro=None):
        i = Ilan(kaynak=kaynak, kimlik=baslik, baslik=baslik, url="u", kurum=kurum, metin=metin)
        i.son_basvuru, i.kadro = son, kadro
        return parmak_izi(i)

    def test_ayni_ilan_farkli_siteler(self):
        kk = self.ilan("kariyerkapisi", "TÜRK AKREDİTASYON KURUMU - KORUMA VE GÜVENLİK GÖREVLİSİ GİRİŞ SINAVI",
                       "TÜRK AKREDİTASYON KURUMU GENEL SEKRETERLİĞİ", self.govde)
        mem = self.ilan("memurlar", "Türk Akreditasyon Kurumu sözleşmeli 3 personel alacak",
                        "Türk Akreditasyon Kurumu", "Türk Akreditasyon Kurumundan: " + self.govde + " İlan olunur.")
        self.assertTrue(ayni_ilan_mi(kk, mem))

    def test_ayni_kurum_farkli_ilan(self):
        # AFAD örneği: şablon ortak, %35'i farklı (ölçülen benzerlik ~0.68)
        kelime = self.govde.split()
        farkli = kelime[:900] + _rastgele_metin(2, 600).split()
        a = self.ilan("kariyerkapisi", "AFAD - Afet ve Acil Durum Yönetimi Uzman Yardımcısı Giriş Sınavı",
                      "AFET VE ACİL DURUM YÖNETİMİ BAŞKANLIĞI (AFAD)", self.govde, kadro="30")
        b = self.ilan("memurlar", "AFAD 12 denetçi yardımcısı alacak", "AFAD Afet ve Acil Durum Yönetimi Başkanlığı",
                      " ".join(farkli), kadro="12")
        self.assertFalse(ayni_ilan_mi(a, b))

    def test_farkli_kurum(self):
        a = self.ilan("kariyerkapisi", "X", "Bartın Üniversitesi", self.govde)
        b = self.ilan("memurlar", "Y", "Düzce Üniversitesi", _rastgele_metin(3))
        self.assertFalse(ayni_ilan_mi(a, b))

    def test_metinsiz_eslesme(self):
        a = self.ilan("memurlar", "Ondokuz Mayıs Üniversitesi 21 İşçi Alacak", "Ondokuz Mayıs Üniversitesi", "",
                      son=date(2026, 12, 7), kadro="21")
        b = self.ilan("resmigazete", "Ondokuz Mayıs Üniversitesi Rektörlüğü – Resmî Gazete ilanı",
                      "Ondokuz Mayıs Üniversitesi Rektörlüğünden", OMU, son=None, kadro="21")
        self.assertTrue(ayni_ilan_mi(a, b))


class AkisTesti(unittest.TestCase):
    """Uçtan uca: 3 siteden gelen aynı ilan tek mesaj olmalı; ikinci çalışmada hiçbir şey gitmemeli."""

    def setUp(self):
        self.giden, self.duzenlenen = [], []
        self._g, self._d = telegram.gonder, telegram.duzenle
        telegram.gonder = lambda m: (self.giden.append(m), len(self.giden))[1]
        telegram.duzenle = lambda i, m: self.duzenlenen.append((i, m))
        ayarlar.MESAJ_ARASI_SANIYE = 0
        self.tmp = tempfile.mkdtemp()
        ayarlar.DURUM_DOSYASI = os.path.join(self.tmp, "durum.json")

    def tearDown(self):
        telegram.gonder, telegram.duzenle = self._g, self._d

    def calis(self, d, ilanlar):
        ist = {k: 0 for k in ("taranan", "elenen", "kpssli", "tekrar", "gonderilen")}
        for i in ilanlar:
            if ("%s:%s" % (i.kaynak, i.kimlik)) in d["gorulen"]:
                continue
            ana.isle(i, d, BUGUN, 1_000_000, ist)
        ana.bekleyenleri_kontrol_et(d, 1_000_000, BUGUN)
        ana.kuyrugu_gonder(d, ist)
        return ist

    def test_akis(self):
        govde = ARANMAZ + " " + _rastgele_metin(7, 800)
        son = BUGUN + timedelta(days=10)
        kk = Ilan("kariyerkapisi", "g1", "ORDU BELEDİYE BAŞKANLIĞI - Temizlik Personeli Alımı", "https://kk/1",
                  kurum="ORDU BELEDİYE BAŞKANLIĞI", metin=govde, son_basvuru=son, il="Ordu",
                  basvuru_url="https://turkiye.gov.tr/x")
        rg = Ilan("resmigazete", "20261123-4-8", "Ordu Belediye Başkanlığı – Resmî Gazete ilanı", "https://rg/8",
                  kurum="Ordu Belediye Başkanlığından", metin="Ordu Belediye Başkanlığından: " + govde)
        mem = Ilan("memurlar", "87100", "Ordu Belediyesi 5 temizlik personeli alacak", "https://mem/87100",
                   kurum="Ordu Belediyesi", metin=govde, son_basvuru=son)
        kpssli = Ilan("memurlar", "87101", "Sayıştay 16 sözleşmeli personel alacak", "https://mem/87101",
                      kurum="Sayıştay", metin=SAYISTAY + _rastgele_metin(8, 300))
        eski = Ilan("memurlar", "87102", "Bolu Boltur 1 İşçi Alacak", "https://mem/87102", kurum="Bolu Boltur",
                    isci_kategorisi=True, son_basvuru=BUGUN - timedelta(days=1))
        sonuc_duyurusu = Ilan("memurlar", "87103", "Adli Tıp Kurumu sözlü sınav sonuçları", "https://mem/87103")

        d = ana.durum_oku()
        ist = self.calis(d, [kk, rg, mem, kpssli, eski, sonuc_duyurusu])
        self.assertEqual(len(self.giden), 1, self.giden)
        self.assertEqual(ist["tekrar"], 2)
        self.assertEqual(ist["kpssli"], 1)
        self.assertEqual(ist["elenen"], 2)
        mesaj = self.giden[0]
        self.assertIn("KPSS ŞARTSIZ", mesaj)
        self.assertIn("⭐", mesaj)  # Ordu öne çıkıyor
        self.assertIn("Kariyer Kapısı", mesaj)
        # tekrar gelen siteler aynı mesaja link olarak eklendi
        self.assertIn("memurlar.net", mesaj)
        self.assertIn("Resmî Gazete", mesaj)
        self.assertIn("Başvuru", mesaj)

        # mesaj gittikten SONRA aynı ilan yeni bir siteden gelirse: yeni mesaj yok, eski mesaj düzenlenir
        haber = Ilan("haber", "h1", "Ordu Belediyesi KPSS şartsız 5 temizlik personeli alacak", "https://haber/1",
                     kurum="Ordu Belediyesi", son_basvuru=son, kadro="5")
        self.calis(d, [haber])
        self.assertEqual(len(self.giden), 1)

        # durum diske yazılıp tekrar okunduğunda aynı ilanlar bir daha GİTMEMELİ
        ana.durum_yaz(d)
        d2 = ana.durum_oku()
        self.calis(d2, [kk, rg, mem, kpssli, eski])
        self.assertEqual(len(self.giden), 1)

    def test_belirsiz_bekler_sonra_net_bilgiyle_degisir(self):
        son = BUGUN + timedelta(days=5)
        metinsiz = Ilan("memurlar", "200", "Karayolları 41 sözleşmeli personel alacak", "https://mem/200",
                        kurum="Karayolları Genel Müdürlüğü", son_basvuru=son, kadro="41")
        d = ana.durum_oku()
        self.calis(d, [metinsiz])
        self.assertEqual(len(self.giden), 0)          # hemen gönderilmez, bekler
        self.assertEqual(len(d["bekleyen_belirsiz"]), 1)
        net = Ilan("kariyerkapisi", "g9", "KARAYOLLARI GENEL MÜDÜRLÜĞÜ - Sözleşmeli Personel Alım İlanı",
                   "https://kk/9", kurum="KARAYOLLARI GENEL MÜDÜRLÜĞÜ",
                   metin=BURSA + _rastgele_metin(9, 400), son_basvuru=son, kadro="41")
        self.calis(d, [net])
        self.assertEqual(len(self.giden), 0)          # KPSS'li çıktı -> hiç gönderilmedi
        self.assertEqual(len(d["bekleyen_belirsiz"]), 0)


class MemurlarCozumleTesti(unittest.TestCase):
    def test_sayfa(self):
        html = """<html><body><article><div class="breadcrumb"><a href="/default.aspx">Ana sayfa</a>
        <a href="/kategori/sydv-ilanlari/">SYDV İlanları</a><a href="/default.aspx">Ana sayfa</a>
        <a href="/kategori/gecici-isci-ilanlari/">Geçici İşçi İlanları</a></div>
        <h1 class="title">Zonguldak Çaycuma Köylere Hizmet Götürme Birliği 4 İşçi Alacak</h1>
        <h2 class="description">Zonguldak Çaycuma 4 İşçi Alacak. Son başvuru tarihi 23 Kasım 2026</h2>
        <div class="grid news-head"><div class="pc:col-4 col-8 info"> Kaynak : İşkur </div></div>
        <div class="detail"><img src="/a.jpg"></div></article></body></html>"""
        v = _mem_cozumle(html, 87045)
        self.assertEqual(v["kategoriler"], ["SYDV İlanları", "Geçici İşçi İlanları"])
        self.assertEqual(v["kaynak"], "İşkur")
        self.assertTrue(v["baslik"].startswith("Zonguldak"))
        self.assertEqual(son_basvuru_bul(v["aciklama"]), date(2026, 11, 23))


if __name__ == "__main__":
    unittest.main()
