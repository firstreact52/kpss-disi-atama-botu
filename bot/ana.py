"""KPSS dışı atama botu – ana akış.

Her çalışmada:
  1) Tüm kaynakları tara, sadece yeni ilanları al
  2) Alım ilanı mı, süresi dolmuş mu, KPSS istiyor mu -> karar ver
  3) Daha önce başka siteden gelmiş mi -> tekrar kontrolü
  4) Telegram'a gönder, durumu kaydet
"""
import json
import logging
import os
import sys
import time
from datetime import datetime, date
from zoneinfo import ZoneInfo

from . import ayarlar, telegram
from .analiz import (BELIRSIZ, KISMEN, KPSSLI, KPSSSIZ, Karar, akademik_mi, alakasiz_mi,
                     alim_ilani_mi, kpss_karari)
from .kaynaklar import haber_tara, kariyerkapisi_tara, memurlar_tara, oturum, resmigazete_tara
from .metin import egitim_duzeyleri, sade
from .model import KAYNAK_ADLARI, KAYNAK_ONCELIK, Ilan
from .tekrar import ayni_ilan_mi, parmak_izi

log = logging.getLogger("bot")
TZ = ZoneInfo(ayarlar.ZAMAN_DILIMI)
AYLAR_TR = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül",
            "Ekim", "Kasım", "Aralık"]


# ------------------------------------------------------------------ durum dosyası
def durum_oku(yol=None) -> dict:
    yol = yol or ayarlar.DURUM_DOSYASI
    if os.path.exists(yol):
        with open(yol, encoding="utf-8") as f:
            d = json.load(f)
    else:
        d = {}
    d.setdefault("surum", 1)
    d.setdefault("gorulen", {})
    d.setdefault("kayitlar", [])
    d.setdefault("bekleyen_belirsiz", [])
    d.setdefault("kuyruk", [])
    d.setdefault("memurlar", {})
    d.setdefault("kaynak_sagligi", {})
    d.setdefault("gunluk", {})
    return d


def durum_yaz(d: dict, yol=None):
    if ayarlar.DENEME:
        return
    yol = yol or ayarlar.DURUM_DOSYASI
    os.makedirs(os.path.dirname(yol) or ".", exist_ok=True)
    gecici = yol + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=0, separators=(",", ":"))
    os.replace(gecici, yol)  # yarım yazılmış dosya kalmasın


def temizle(d: dict, simdi: float):
    sinir_gorulen = simdi - 150 * 86400
    d["gorulen"] = {k: v for k, v in d["gorulen"].items() if v >= sinir_gorulen}
    sinir = simdi - ayarlar.KAYIT_SAKLAMA_GUN * 86400
    d["kayitlar"] = [k for k in d["kayitlar"] if k["ts"] >= sinir]


# ------------------------------------------------------------------ mesaj
def tarih_tr(t: date) -> str:
    return f"{t.day} {AYLAR_TR[t.month]} {t.year}"


def mesaj_govdesi(ilan: Ilan, karar: Karar, bugun: date) -> str:
    k = telegram.kacis
    etiket = {KPSSSIZ: "🟢 <b>KPSS ŞARTSIZ</b>",
              KISMEN: "🟡 <b>KISMEN KPSS ŞARTSIZ</b>",
              BELIRSIZ: "❔ <b>KPSS DURUMU BELİRSİZ</b>"}.get(karar.tur, "")
    if ilan.kaynak == "haber":
        etiket += "  <i>(haber)</i>"
    satirlar = [etiket]
    if ilan.il and ilan.il in ayarlar.ONE_CIKAN_ILLER:
        satirlar.append(f"⭐ <b>{k(ilan.il)}</b>")
    satirlar.append(f"\n<b>{k(ilan.baslik)}</b>")
    if ilan.kurum and sade(ilan.kurum) not in sade(ilan.baslik):
        satirlar.append(f"🏛 {k(ilan.kurum)}")
    if ilan.kadro:
        satirlar.append(f"👥 Kadro: {k(ilan.kadro)}")
    egitim = egitim_duzeyleri(ilan.metin[:8000]) if ilan.metin else []
    if egitim:
        satirlar.append(f"🎓 Eğitim: {k(', '.join(egitim))}")
    if ilan.il:
        satirlar.append(f"📍 Yer: {k(ilan.il)}")
    if ilan.son_basvuru:
        kalan = (ilan.son_basvuru - bugun).days
        ek = "bugün son gün!" if kalan == 0 else f"{kalan} gün kaldı"
        satirlar.append(f"⏳ Son başvuru: <b>{tarih_tr(ilan.son_basvuru)}</b> ({ek})")
    if ilan.ek_bilgi and ilan.kaynak == "kariyerkapisi":
        satirlar.append(f"🗂 Tür: {k(ilan.ek_bilgi)}")
    satirlar.append(f"📝 {k(karar.neden)}")
    return "\n".join(satirlar)


def linkler_satiri(linkler) -> str:
    parcalar = [f'<a href="{telegram.kacis(u)}">{telegram.kacis(ad)}</a>' for ad, u in linkler]
    return "🔗 " + " | ".join(parcalar)


def ilan_linkleri(ilan: Ilan):
    ad = KAYNAK_ADLARI.get(ilan.kaynak, ilan.kaynak)
    if ilan.kaynak == "haber" and ilan.ek_bilgi:
        ad = f"Haber ({ilan.ek_bilgi})"
    l = [[ad, ilan.url]]
    if ilan.basvuru_url and ilan.basvuru_url != ilan.url:
        l.append(["Başvuru", ilan.basvuru_url])
    return l


def tam_mesaj(kayit: dict) -> str:
    m = kayit["govde"] + "\n" + linkler_satiri(kayit["linkler"])
    if kayit.get("notlar"):
        m += "\n" + "\n".join(kayit["notlar"])
    return m[:4000]


# ------------------------------------------------------------------ değerlendirme
def degerlendir(ilan: Ilan, bugun: date):
    """(karar, atlama_nedeni) döndürür. atlama_nedeni doluysa ilan gönderilmez/kaydedilmez."""
    if "ATLA" in ilan.kategoriler:
        return None, "tür"
    if alakasiz_mi(ilan.baslik):
        return None, "alım ilanı değil"
    akademik = "akademik" in ilan.kategoriler or akademik_mi(ilan.baslik, ilan.metin)
    if akademik and not ayarlar.AKADEMIK_ILANLAR:
        return None, "akademik"
    if ilan.kaynak in ("resmigazete",) and ilan.metin and not alim_ilani_mi(ilan.baslik, ilan.metin):
        return None, "alım ilanı değil"
    if ilan.kaynak == "resmigazete" and not ilan.metin:
        return None, "okunamadı"  # RG başlığı sadece kurum adı; memurlar/Kariyer Kapısı zaten yakalar
    if ilan.son_basvuru and ilan.son_basvuru < bugun:
        return None, "süresi dolmuş"
    if ilan.kaynak == "haber":
        return Karar(KPSSSIZ, "Haberde KPSS şartı olmadığı yazıyor — resmî ilanı mutlaka kontrol et."), None
    return kpss_karari(ilan.baslik, ilan.metin, ilan.isci_kategorisi), None


def eslesen_bul(iz, kaynak, liste):
    for kayit in liste:
        if ayni_ilan_mi(iz, kayit["iz"], ayni_kaynak=(kaynak == kayit["kaynak"])):
            return kayit
    return None


def isle(ilan: Ilan, d: dict, bugun: date, simdi: float, istatistik: dict):
    d["gorulen"][ilan.anahtar] = simdi
    istatistik["taranan"] += 1
    karar, atla = degerlendir(ilan, bugun)
    if atla:
        istatistik["elenen"] += 1
        log.info("ELENDİ (%s): %s", atla, ilan.baslik[:90])
        return
    iz = parmak_izi(ilan)

    # ---- tekrar kontrolü: bekleyen belirsizler + geçmiş kayıtlar
    bekleyen = eslesen_bul(iz, ilan.kaynak, d["bekleyen_belirsiz"])
    if bekleyen and karar.tur != BELIRSIZ:
        # daha iyi bilgi geldi: bekleyen belirsiz ilanı bırak, bunu normal işle
        d["bekleyen_belirsiz"].remove(bekleyen)
        log.info("Belirsiz ilan için net bilgi geldi: %s", ilan.baslik[:80])
    elif bekleyen:
        bekleyen["linkler"] += [l for l in ilan_linkleri(ilan) if l not in bekleyen["linkler"]]
        istatistik["tekrar"] += 1
        return

    eski = eslesen_bul(iz, ilan.kaynak, reversed(d["kayitlar"]))
    if eski:
        istatistik["tekrar"] += 1
        log.info("TEKRAR (%s ile aynı): %s", eski["anahtar"], ilan.baslik[:80])
        degisti = False
        for l in ilan_linkleri(ilan):
            if l[1] not in [x[1] for x in eski["linkler"]] and ilan.kaynak != "haber":
                eski["linkler"].append(l)
                degisti = True
        # Daha resmî kaynak farklı bir sonuç söylüyorsa uyar
        if eski.get("karar") in (KPSSSIZ, BELIRSIZ, KISMEN) and karar.tur == KPSSLI and \
                KAYNAK_ONCELIK[ilan.kaynak] <= KAYNAK_ONCELIK[eski["kaynak"]]:
            eski.setdefault("notlar", []).append(
                f"⚠️ <b>Güncelleme:</b> {KAYNAK_ADLARI[ilan.kaynak]} metninde KPSS şartı görünüyor, dikkat!")
            degisti = True
        if eski.get("karar") == BELIRSIZ and karar.tur in (KPSSSIZ, KISMEN):
            eski.setdefault("notlar", []).append(f"✅ <b>Güncelleme:</b> {telegram.kacis(karar.neden)}")
            degisti = True
        if degisti and eski.get("mesaj_id"):
            d["kuyruk"].append({"tip": "duzenle", "anahtar": eski["anahtar"]})
        return

    kayit = {"anahtar": ilan.anahtar, "kaynak": ilan.kaynak, "karar": karar.tur, "iz": iz, "ts": simdi,
             "baslik": ilan.baslik[:200], "son": iz["son"], "linkler": ilan_linkleri(ilan)}

    if karar.tur == KPSSLI:
        istatistik["kpssli"] += 1
        log.info("KPSS'Lİ: %s | %s", ilan.baslik[:80], karar.kanit[:1])
        d["kayitlar"].append(kayit)
        return
    if karar.tur == KISMEN and not ayarlar.KISMEN_KPSSSIZ_GONDER:
        d["kayitlar"].append(kayit)
        return

    kayit["govde"] = mesaj_govdesi(ilan, karar, bugun)
    if karar.tur == BELIRSIZ:
        if ayarlar.BELIRSIZ_GONDER:
            d["bekleyen_belirsiz"].append(kayit)
        return
    d["kayitlar"].append(kayit)
    d["kuyruk"].append({"tip": "yeni", "anahtar": ilan.anahtar})
    log.info("GÖNDERİLECEK (%s): %s", karar.tur, ilan.baslik[:90])


def bekleyenleri_kontrol_et(d: dict, simdi: float, bugun: date):
    kalan = []
    for kayit in d["bekleyen_belirsiz"]:
        if kayit.get("son") and date.fromisoformat(kayit["son"]) < bugun:
            continue
        if simdi - kayit["ts"] >= ayarlar.BELIRSIZ_BEKLEME_SAAT * 3600:
            d["kayitlar"].append(kayit)
            d["kuyruk"].append({"tip": "yeni", "anahtar": kayit["anahtar"]})
        else:
            kalan.append(kayit)
    d["bekleyen_belirsiz"] = kalan


def kuyrugu_gonder(d: dict, istatistik: dict):
    kayit_haritasi = {k["anahtar"]: k for k in d["kayitlar"]}
    gonderilen = 0
    while d["kuyruk"] and gonderilen < ayarlar.MAKS_MESAJ_HER_TUR:
        is_ = d["kuyruk"][0]
        kayit = kayit_haritasi.get(is_["anahtar"])
        if kayit is None:
            d["kuyruk"].pop(0)
            continue
        if is_["tip"] == "yeni":
            if kayit.get("mesaj_id"):
                d["kuyruk"].pop(0)  # zaten gönderilmiş, asla ikinci kez gönderme
                continue
            kayit["mesaj_id"] = telegram.gonder(tam_mesaj(kayit))
            istatistik["gonderilen"] += 1
            gonderilen += 1
        else:
            if kayit.get("mesaj_id"):
                telegram.duzenle(kayit["mesaj_id"], tam_mesaj(kayit))
        d["kuyruk"].pop(0)
        durum_yaz(d)  # her mesajdan sonra kaydet: çökme olsa bile aynı mesaj tekrar gitmez
        time.sleep(ayarlar.MESAJ_ARASI_SANIYE)


# ------------------------------------------------------------------ kaynak sağlığı
def saglik_bildir(d: dict, ad: str, hata: Exception | None):
    s = d["kaynak_sagligi"].setdefault(ad, {"hata": 0, "uyari": False})
    if hata is None:
        if s.get("uyari"):
            _guvenli_gonder(f"✅ <b>{KAYNAK_ADLARI[ad]}</b> tekrar çalışıyor.")
        s.update(hata=0, uyari=False, son_basari=time.time())
        return
    s["hata"] = s.get("hata", 0) + 1
    s["son_hata"] = str(hata)[:300]
    if s["hata"] >= ayarlar.HATA_UYARI_ESIGI and not s.get("uyari"):
        s["uyari"] = True
        _guvenli_gonder(f"⚠️ <b>{KAYNAK_ADLARI[ad]}</b> art arda {s['hata']} kez okunamadı.\n"
                        f"Hata: <code>{telegram.kacis(str(hata)[:250])}</code>\n"
                        f"Diğer kaynaklar taranmaya devam ediyor.")


def _guvenli_gonder(metin):
    try:
        telegram.gonder(metin)
    except Exception as e:
        log.error("Telegram'a gönderilemedi: %s", e)


def gunluk_ozet(d: dict, yerel: datetime):
    bugun = yerel.date().isoformat()
    g = d["gunluk"]
    if yerel.hour < ayarlar.GUNLUK_OZET_SAATI or d.get("son_ozet") == bugun:
        return
    durumlar = []
    for ad in ("kariyerkapisi", "resmigazete", "memurlar", "haber"):
        s = d["kaynak_sagligi"].get(ad)
        if s is None:
            continue
        durumlar.append(("✅" if s.get("hata", 0) == 0 else "⚠️") + " " + KAYNAK_ADLARI[ad])
    _guvenli_gonder(
        "🤖 <b>Günlük kontrol – bot çalışıyor</b>\n"
        f"Taranan ilan: {g.get('taranan', 0)}\n"
        f"Gönderilen KPSS'siz: {g.get('gonderilen', 0)}\n"
        f"KPSS'li diye elenen: {g.get('kpssli', 0)}\n"
        f"Tekrar engellenen: {g.get('tekrar', 0)}\n"
        f"Diğer elenen (süresi geçmiş, sonuç duyurusu vb.): {g.get('elenen', 0)}\n"
        + "\n".join(durumlar))
    d["son_ozet"] = bugun


# ------------------------------------------------------------------ çalıştır
def calistir():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    d = durum_oku()
    simdi = time.time()
    yerel = datetime.now(TZ)
    bugun = yerel.date()
    temizle(d, simdi)

    if d["gunluk"].get("tarih") != bugun.isoformat():
        d["gunluk"] = {"tarih": bugun.isoformat()}
    istatistik = {k: 0 for k in ("taranan", "elenen", "kpssli", "tekrar", "gonderilen")}

    ilk_calisma = not d.get("ilk_calisma_bitti")
    if ilk_calisma:
        _guvenli_gonder("🚀 <b>KPSS dışı atama botu başladı.</b>\n"
                        "Önce son bir haftanın hâlâ açık olan ilanlarını gönderiyorum, "
                        "sonra sadece yeni ilanlar gelecek.")

    yeni_mi = lambda anahtar: anahtar not in d["gorulen"]  # noqa: E731
    s = oturum()

    gorevler = [
        ("kariyerkapisi", lambda: kariyerkapisi_tara(s, yeni_mi)),
        ("resmigazete", lambda: resmigazete_tara(s, yeni_mi, bugun)[0]),
        ("memurlar", lambda: memurlar_tara(s, yeni_mi, d["memurlar"])),
    ]
    if ayarlar.HABERLERI_TARA:
        gorevler.append(("haber", lambda: haber_tara(s, yeni_mi)))

    for ad, fonk in gorevler:
        try:
            ilanlar = fonk()
            saglik_bildir(d, ad, None)
            log.info("%s: %d yeni ilan", ad, len(ilanlar))
        except Exception as e:
            log.exception("%s okunamadı", ad)
            saglik_bildir(d, ad, e)
            continue
        for ilan in ilanlar:
            try:
                isle(ilan, d, bugun, simdi, istatistik)
            except Exception:
                log.exception("İlan işlenemedi: %s", ilan.anahtar)
        durum_yaz(d)

    bekleyenleri_kontrol_et(d, simdi, bugun)
    try:
        kuyrugu_gonder(d, istatistik)
    except telegram.TelegramHata as e:
        log.error("Telegram hatası, kalan mesajlar sonraki çalışmada gönderilecek: %s", e)

    for k, v in istatistik.items():
        d["gunluk"][k] = d["gunluk"].get(k, 0) + v
    d["ilk_calisma_bitti"] = True
    d["son_calisma"] = yerel.isoformat(timespec="seconds")
    gunluk_ozet(d, yerel)
    durum_yaz(d)
    log.info("Bitti: %s | kuyrukta kalan: %d", istatistik, len(d["kuyruk"]))
    return 0


if __name__ == "__main__":
    sys.exit(calistir())
