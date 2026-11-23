"""Metin yardımcıları: Türkçe sadeleştirme, tarih, kadro sayısı, eğitim, il."""
import re
from datetime import date

_TR = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
                     "â": "a", "î": "i", "û": "u", "’": "'", "‘": "'", "`": "'"})


def kucult(s: str) -> str:
    """Türkçe kurallarla küçült (İ->i, I->ı)."""
    return (s or "").replace("İ", "i").replace("I", "ı").lower()


def sade(s: str) -> str:
    """Küçük harf + Türkçe karakterleri at + boşlukları tekle. Karşılaştırma ve regex için."""
    s = kucult(s).translate(_TR)
    s = s.replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip()


def bbcode_temizle(s: str) -> str:
    s = re.sub(r"\[/?[a-zA-Z*]+(=[^\]]*)?\]", " ", s or "")
    return s


def tireleri_birlestir(s: str) -> str:
    """PDF satır sonu bölmelerini birleştir: 'alına-\\ncak' -> 'alınacak'."""
    return re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s or "")


def kelimeler(s: str):
    return re.findall(r"[a-z0-9]+", sade(s))


# ---------------- Tarih ----------------
AYLAR = {"ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6,
         "temmuz": 7, "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12}

_AY_RE = "|".join(AYLAR)


def tr_tarih_bul(s: str):
    """'7 Aralık 2026' biçimindeki ilk tarihi date olarak döndür."""
    m = re.search(r"\b(\d{1,2})\s+(" + _AY_RE + r")\s+(20\d\d)\b", sade(s))
    if not m:
        return None
    try:
        return date(int(m.group(3)), AYLAR[m.group(2)], int(m.group(1)))
    except ValueError:
        return None


def son_basvuru_bul(metin: str):
    """İlan metninden son başvuru tarihini bulmaya çalışır."""
    t = sade(metin)
    # "son basvuru tarihi 7 aralik 2026" / "son odeme tarihi ..." (memurlar bu ifadeyi kullanıyor)
    m = re.search(r"son (?:basvuru|odeme)(?: tarihi)?\s*[:\-]?\s*(\d{1,2}\s+(?:" + _AY_RE + r")\s+20\d\d)", t)
    if m:
        return tr_tarih_bul(m.group(1))
    # "... 01.12.2026 - 15.12.2026 tarihleri arasında" -> ikinci tarih
    m = re.search(r"(\d{1,2})[./](\d{1,2})[./](20\d\d)\s*[-–]\s*(\d{1,2})[./](\d{1,2})[./](20\d\d)", t)
    if m:
        try:
            return date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
        except ValueError:
            pass
    m = re.search(r"son basvuru[^.]{0,40}?(\d{1,2})[./](\d{1,2})[./](20\d\d)", t)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None


# ---------------- Kadro sayısı ----------------
def kadro_sayisi(baslik: str, metin: str = ""):
    for kaynak in (baslik, metin[:1500]):
        t = sade(kaynak)
        m = re.search(r"(?:toplam\s+)?(\d{1,3}(?:[.,]\d{3})*|\d+)\s*(?:\(\w+\)\s*)?(?:adet\s+)?"
                      r"(?:bin\s+)?(?:surekli\s+|gecici\s+|sozlesmeli\s+|daimi\s+)?"
                      r"(isci|personel|memur|eleman|uzman|kisi|kadro|ogretim|polis|bekci|asistan|"
                      r"koruma|guvenlik|temizlik|sofor|hemsire|ebe|teknisyen|tekniker|muhendis)", t)
        if m:
            sayi = m.group(1).replace(".", "").replace(",", "")
            if "bin" in t[m.start():m.end()]:
                try:
                    return str(int(sayi) * 1000)
                except ValueError:
                    pass
            return sayi
    return None


# ---------------- Eğitim ----------------
_EGITIM = [
    ("İlkokul/Ortaokul", r"\b(ilkokul|ilkogretim|ortaokul)\b"),
    ("Lise", r"\b(lise|ortaogretim|meslek lisesi)\b"),
    ("Ön lisans", r"\bon ?lisans\b"),
    ("Lisans", r"(?<!on )(?<!on)\blisans\b"),
]


def egitim_duzeyleri(metin: str):
    t = sade(metin)
    return [ad for ad, desen in _EGITIM if re.search(desen, t)]


# ---------------- İl ----------------
ILLER = ["Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Aksaray", "Amasya", "Ankara", "Antalya",
         "Ardahan", "Artvin", "Aydın", "Balıkesir", "Bartın", "Batman", "Bayburt", "Bilecik", "Bingöl",
         "Bitlis", "Bolu", "Burdur", "Bursa", "Çanakkale", "Çankırı", "Çorum", "Denizli", "Diyarbakır",
         "Düzce", "Edirne", "Elazığ", "Erzincan", "Erzurum", "Eskişehir", "Gaziantep", "Giresun",
         "Gümüşhane", "Hakkari", "Hatay", "Iğdır", "Isparta", "İstanbul", "İzmir", "Kahramanmaraş",
         "Karabük", "Karaman", "Kars", "Kastamonu", "Kayseri", "Kilis", "Kırıkkale", "Kırklareli",
         "Kırşehir", "Kocaeli", "Konya", "Kütahya", "Malatya", "Manisa", "Mardin", "Mersin", "Muğla",
         "Muş", "Nevşehir", "Niğde", "Ordu", "Osmaniye", "Rize", "Sakarya", "Samsun", "Şanlıurfa",
         "Siirt", "Sinop", "Şırnak", "Sivas", "Tekirdağ", "Tokat", "Trabzon", "Tunceli", "Uşak", "Van",
         "Yalova", "Yozgat", "Zonguldak"]
# Kurum adında il adı geçmeyen yaygın üniversiteler
_KURUM_IL = {"ondokuz mayis": "Samsun", "karadeniz teknik": "Trabzon", "dumlupinar": "Kütahya",
             "bozok": "Yozgat", "tarsus": "Mersin", "ataturk universitesi": "Erzurum",
             "ege universitesi": "İzmir", "dokuz eylul": "İzmir", "hacettepe": "Ankara",
             "gazi universitesi": "Ankara", "odtu": "Ankara", "orta dogu teknik": "Ankara",
             "yildirim beyazit": "Ankara", "yildiz teknik": "İstanbul", "marmara": "İstanbul",
             "erciyes": "Kayseri", "cukurova": "Adana", "akdeniz universitesi": "Antalya",
             "uludag": "Bursa", "pamukkale": "Denizli", "firat universitesi": "Elazığ",
             "inonu": "Malatya", "selcuk": "Konya", "harran": "Şanlıurfa", "dicle": "Diyarbakır",
             "anadolu universitesi": "Eskişehir", "cumhuriyet universitesi": "Sivas",
             "gaziosmanpasa": "Tokat", "kafkas": "Kars", "sutcu imam": "Kahramanmaraş",
             "mustafa kemal": "Hatay", "adnan menderes": "Aydın", "celal bayar": "Manisa",
             "zonguldak bulent": "Zonguldak", "recep tayyip": "Rize", "nigde omer": "Niğde"}
_ILLER_SADE = [(sade(i), i) for i in ILLER]


def il_bul(*metinler):
    for s in metinler:
        t = sade(s or "")[:400]
        for anahtar, il in _KURUM_IL.items():
            if anahtar in t:
                return il
        for sade_il, il in _ILLER_SADE:
            if re.search(r"\b" + re.escape(sade_il) + r"(?:'?(?:da|de|ta|te|in|un|nin|nun|daki|deki|ili))?\b", t):
                return il
    return None
