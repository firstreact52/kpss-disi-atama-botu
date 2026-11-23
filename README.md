# KPSS Dışı Atama Botu

Kamu kurumlarının **KPSS istemeyen** alım ilanlarını her 15 dakikada bir tarar ve Telegram'a gönderir. Ücretsizdir (GitHub Actions).

## Nereleri tarar?
| Kaynak | Nasıl |
|---|---|
| **Kariyer Kapısı** (kariyerkapisi.gov.tr) | Resmî API, ilan metninin tamamı okunur |
| **Resmî Gazete – Çeşitli İlanlar** | Bugünün ve dünün ilan PDF'leri okunur |
| **ilan.memurlar.net** | İlan numaraları **tek tek sırayla** kontrol edilir, hiçbir ilan atlanmaz (İŞKUR işçi ilanları dahil) |
| **Google Haberler** | "KPSS şartsız" haberleri (yedek güvenlik ağı) |

## Neye göre karar verir?
- 🟢 **KPSS ŞARTSIZ**: ilanda "KPSS aranmaz" yazıyor, İŞKUR/noter kurasıyla işçi alımı ya da metnin tamamında KPSS geçmiyor
- 🟡 **KISMEN**: bazı kadrolarda KPSS yok ya da KPSS zorunlu değil
- ❔ **BELİRSİZ**: ilan metni resim, okunamadı (6 saat daha iyi bir kaynak beklenir, yoksa uyarıyla gönderilir)
- ❌ Gönderilmez: KPSS puanı isteyenler, süresi geçmişler, sonuç/sözlü sınav duyuruları, görevde yükselme, burs, akademik ilanlar (açılabilir)

## Tekrar engeli
Aynı ilan 3 siteden gelse bile **tek mesaj** gelir. Bot ilan metinlerini karşılaştırır (aynı ilan %90+ aynıdır), kurum adına, son başvuru tarihine ve kadro sayısına bakar. Yeni site bulunursa eski mesaja link olarak eklenir.

## Kurulum (bir kere, ~10 dk)
1. **Telegram botu**: Telegram'da `@BotFather` → `/newbot` → verilen **token**'ı kopyala. (Trend botundaki botu da kullanabilirsin.)
2. **Chat ID**: Botuna bir mesaj at, sonra tarayıcıda `https://api.telegram.org/bot<TOKEN>/getUpdates` aç, `"chat":{"id":...}` sayısını kopyala.
3. **GitHub**: Yeni bir repo aç (**Public** önerilir: dakika sınırı yok), bu klasördeki dosyaların hepsini yükle.
4. Repo → **Settings → Secrets and variables → Actions → New repository secret**:
   - `TELEGRAM_TOKEN` = token
   - `TELEGRAM_CHAT_ID` = chat id
5. **Actions** sekmesi → botu etkinleştir → "KPSS dışı atama botu" → **Run workflow**.
   İlk seferde son 1 haftanın hâlâ açık ilanları gelir, sonra sadece yeniler.

> Private repo kullanacaksan GitHub ücretsiz 2000 dk/ay verir; o zaman `bot.yml` içinde `*/15` yerine `*/30` yaz.

## İsteğe bağlı ayarlar
Repo → Settings → Secrets and variables → Actions → **Variables**:
- `ONE_CIKAN_ILLER` = `Ordu,Samsun` → bu illerdeki ilanlar ⭐ ile işaretlenir (varsayılan: Ordu)
- `AKADEMIK_ILANLAR` = `1` → öğretim üyesi/ar-gör ilanları da gelsin
- `HABERLERI_TARA` = `0` → Google Haberler kapansın

## Her şey yolunda mı?
- Her akşam 21:00'de **"Bot çalışıyor"** özeti gelir (kaç ilan tarandı, kaç tane elendi).
- Bir site 6 kez üst üste okunamazsa Telegram'a **uyarı** gelir, düzelince haber verir.
- Deneme: Actions → Run workflow → "Deneme modu" işaretle → mesajlar Telegram'a gitmez, çıktıda görünür.

## Dosyalar
- `bot/kaynaklar.py` – siteleri okuyan kısım
- `bot/analiz.py` – KPSS kararı
- `bot/tekrar.py` – tekrar engeli
- `bot/ana.py` – ana akış, Telegram mesajı
- `durum/durum.json` – görülen ilanlar (bot kendisi günceller, elle silme)
