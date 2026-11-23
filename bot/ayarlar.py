"""Botun tüm ayarları. Değiştirmek istediğin her şey burada."""
import os


def _bool(ad, varsayilan):
    deger = os.environ.get(ad)
    if deger is None or deger == "":
        return varsayilan
    return deger.strip().lower() in ("1", "true", "evet", "yes", "on")


# --- Telegram (GitHub Secrets'tan gelir) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# DENEME=1 ise mesajlar Telegram'a gitmez, sadece ekrana yazılır (durum da kaydedilmez)
DENEME = _bool("DENEME", False)

# --- Neler gönderilsin ---
AKADEMIK_ILANLAR = _bool("AKADEMIK_ILANLAR", False)   # öğretim üyesi / ar-gör ilanları (ALES ile alınır)
KISMEN_KPSSSIZ_GONDER = _bool("KISMEN_KPSSSIZ_GONDER", True)  # bazı kadrolarda KPSS şartı yoksa
BELIRSIZ_GONDER = _bool("BELIRSIZ_GONDER", True)      # metni okunamayan ilanlar (uyarıyla)
HABERLERI_TARA = _bool("HABERLERI_TARA", True)        # Google Haberler güvenlik ağı

# Bu illerdeki ilanlar mesajda ⭐ ile işaretlenir (virgülle ayır, boş bırakılabilir)
ONE_CIKAN_ILLER = [i.strip() for i in (os.environ.get("ONE_CIKAN_ILLER") or "Ordu").split(",") if i.strip()]

# --- Çalışma sınırları ---
MAKS_MESAJ_HER_TUR = 80          # bir çalışmada en fazla bu kadar mesaj (fazlası sıraya girer)
MESAJ_ARASI_SANIYE = 1.6         # Telegram hız sınırı için
BELIRSIZ_BEKLEME_SAAT = 6        # metinsiz ilan için daha iyi kaynak beklenir
ILK_CALISMA_GERIYE_ILAN = 150    # ilk çalışmada memurlar'da geriye kaç ilan bakılsın (~1 hafta)
MEMURLAR_ARDISIK_BOS_LIMIT = 8   # art arda bu kadar boş numara görünce tarama durur
MEMURLAR_MAKS_TARAMA = 250       # bir çalışmada en fazla bu kadar numara
HATA_UYARI_ESIGI = 2             # bir kaynak art arda bu kadar çalışmada hata verirse uyarı (2 = 1 gün)
GUNLUK_OZET_SAATI = 18           # bu saatten sonraki ilk çalışmada (akşam) "bot çalışıyor" özeti
KAYIT_SAKLAMA_GUN = 60           # tekrar kontrolü için geçmiş kaç gün tutulsun

DURUM_DOSYASI = os.environ.get("DURUM_DOSYASI", "durum/durum.json")
ZAMAN_DILIMI = "Europe/Istanbul"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
