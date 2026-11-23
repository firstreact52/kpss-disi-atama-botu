"""İlanın KPSS isteyip istemediğine ve gerçekten bir alım ilanı olup olmadığına karar verir."""
import re
from dataclasses import dataclass, field

from .metin import sade

# Karar türleri
KPSSSIZ = "kpsssiz"        # KPSS şartı yok
KISMEN = "kismen"          # bazı kadrolarda yok / KPSS zorunlu değil
KPSSLI = "kpssli"          # KPSS şartı var -> gönderilmez
BELIRSIZ = "belirsiz"      # metin okunamadı
ALAKASIZ = "alakasiz"      # alım ilanı değil (sonuç, görevde yükselme, burs...)


@dataclass
class Karar:
    tur: str
    neden: str
    kanit: list = field(default_factory=list)


# ---- KPSS İSTEYEN ifadeler ----
_KPSS_VAR = [
    r"\be?kpss\)? ?-?p ?\d{1,3}\b",                                # KPSSP3, KPSS P93, (KPSS) P3, EKPSS
    r"\be?kpss[^.;]{0,60}puan(i|lari)? (dikkate|esas)",
    r"\bp ?(3|93|94|1|2|4|5|6|7|8|9|\d{2})\b puan turu",
    r"\be?kpss[^.;]{0,140}(en az|asgari|taban puan|puan sirala|basari sira|puan turunden|puan turu)",
    r"kamu personel(i)? secme sinav[^.;]{0,220}(en az|asgari|puan turunden|puan sirala|basari sira|girmis|almis)",
    r"\be?kpss ?\(?[ab]\)? grubu[^.;]{0,100}(girmis|puan|sinav)",
    r"\be?kpss taban puan",
    r"\bkpss puan(i|lari)? esas",
    r"merkezi yerlestirme",
]
# ---- KPSS İSTEMEYEN ifadeler ----
_KPSS_YOK = [
    r"\be?kpss[^.;]{0,80}(aranmaz|aranmayacak|aranmamakta|aranmaksizin|aranmayacaktir|zorunlu degil|sarti yok|sarti bulunmamakta|sart degil)",
    r"(sinav|kpss) puan[i]? (sarti )?aranmaksizin",
    r"\bkpss puan[i]? olmayan",
    r"\bkpss (sarti|puani) (olmadan|aranmadan)",
    r"\bkpss'?siz\b",
]
# ---- İŞKUR / noter kurası ile işçi alımı (KPSS yok) ----
_ISCI = [
    r"noter (huzurunda )?(kura|cekilis)",
    r"(turkiye is kurumu|iskur)[^.;]{0,200}(surekli isci|gecici isci|isci alin|isci talep|ilan)",
    r"(surekli|gecici|daimi) isci[^.;]{0,200}(turkiye is kurumu|iskur)",
    r"esube\.iskur\.gov\.tr",
]
# ---- Alım ilanı değil (başlığa bakılır) ----
_ALAKASIZ_BASLIK = [
    r"\bsonuc", r"sozlu sinav duyurusu", r"yedek (aday|liste)", r"basari (listesi|sirasi)",
    r"\biptal\b", r"\bduzeltme\b", r"degisiklik ilani", r"giris belgesi", r"sinav yerleri",
    r"mulakat (tarih|listesi|sonuc)", r"gorevde yukselme", r"unvan degisikligi", r"yatay gecis",
    r"\bburs\b", r"yurt ?disi (egitim|yuksek lisans)", r"yeterlik sinavi", r"tercih (ilani|kilavuzu)",
    r"belge basvurusu", r"\bkayit\b.*\bogrenci", r"ogrenci alim", r"atama (sonuc|listesi)",
    r"\bkesinlesen\b", r"\bnihai\b",
]
# ---- Gerçekten personel alımı mı (metne bakılır) ----
_ALIM = [
    r"(personel|isci|eleman|memur|uzman|sozlesmeli|ogretim (uyesi|elemani|gorevlisi)|arastirma gorevlisi|"
    r"koruma|guvenlik|bekci|polis|hemsire|teknisyen|tekniker|muhendis|sofor|asistan|avukat|ebe|"
    r"uzman yardimcisi|denetci yardimcisi|mufettis yardimcisi|aday|erbas|astsubay|subay|er )"
    r"[^.;]{0,160}(alin(acak|acaktir|ir|masi)|alim(i|ina)?\b|istihdam edil|temin edil|atama yapil|"
    r"sinav(i|la)? (ile|yapil)|kadro(su|lari)?na)",
    r"alim ilani", r"istihdam edilmek uzere", r"\balinacaktir\b", r"\balacak\b",
]
_AKADEMIK = r"(ogretim (uyesi|elemani|gorevlisi)|arastirma gorevlisi|doktor ogretim|docent|profesor)"


def _bul(desenler, t):
    kanit = []
    for d in desenler:
        m = re.search(d, t)
        if m:
            bas = max(0, m.start() - 40)
            kanit.append(t[bas:m.end() + 40].strip())
    return kanit


def alakasiz_mi(baslik: str) -> bool:
    t = sade(baslik)
    return any(re.search(d, t) for d in _ALAKASIZ_BASLIK)


def alim_ilani_mi(baslik: str, metin: str) -> bool:
    t = sade(baslik + " . " + metin[:6000])
    return any(re.search(d, t) for d in _ALIM)


def akademik_mi(baslik: str, metin: str = "") -> bool:
    """Sadece akademik kadro içeren ilan mı? (idari personel de varsa False)"""
    b = sade(baslik)
    if re.search(_AKADEMIK, b) and not re.search(r"(sozlesmeli personel|isci|idari|memur|bilisim)", b):
        return True
    t = sade(metin[:4000])
    if re.search(_AKADEMIK, t) and not re.search(
            r"(sozlesmeli personel|isci alin|surekli isci|4/b|memur kadro|bilisim personeli|"
            r"hemsire|tekniker|teknisyen|koruma ve guvenlik)", t):
        return not b or bool(re.search(_AKADEMIK, b)) or "akademik" in b
    return False


def kpss_karari(baslik: str, metin: str, isci_kategorisi: bool = False) -> Karar:
    """Asıl karar fonksiyonu."""
    t = sade((baslik or "") + " . " + (metin or ""))
    metin_var = len(sade(metin or "")) >= 300

    var = _bul(_KPSS_VAR, t)
    yok = _bul(_KPSS_YOK, t)
    isci = _bul(_ISCI, t)

    if var and (yok or isci):
        return Karar(KISMEN, "Bazı kadrolarda KPSS şartı yok ya da KPSS zorunlu değil — ilanı mutlaka kontrol et.",
                     (yok or isci)[:1] + var[:1])
    if var:
        return Karar(KPSSLI, "KPSS puanı isteniyor.", var[:2])
    if yok:
        return Karar(KPSSSIZ, "İlanda KPSS şartı aranmadığı açıkça yazıyor.", yok[:1])
    if isci:
        return Karar(KPSSSIZ, "İŞKUR üzerinden işçi alımı (genelde noter kurasıyla, KPSS yok).", isci[:1])
    if metin_var:
        return Karar(KPSSSIZ, "İlan metninin tamamı tarandı, KPSS şartı geçmiyor.", [])
    if isci_kategorisi:
        return Karar(KPSSSIZ, "İşçi alımı ilanı (bu tür alımlarda KPSS istenmez). Metin resim olduğu için okunamadı.", [])
    return Karar(BELIRSIZ, "İlan metni okunamadı (resim/PDF olabilir). KPSS şartını ilandan kontrol et.", [])
