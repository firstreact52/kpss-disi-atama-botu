"""Aynı ilanın farklı sitelerden tekrar gelmesini engeller.

Her ilan için 3 parmak izi tutulur:
  1) kurum adı kelimeleri (Rektörlüğü, Başkanlığı gibi genel ekler atılmış)
  2) ilan metninin MinHash imzası (aynı ilan farklı sitelerde ~%90+ aynı metin)
  3) başlık kelimeleri, son başvuru tarihi, kadro sayısı
"""
import base64
import re
import struct
import zlib

from .metin import kelimeler

_GENEL = {
    "t", "c", "tc", "rektorlugu", "rektorlugunden", "rektorluk", "baskanligi", "baskanligindan", "baskanlik",
    "genel", "mudurlugu", "mudurlugunden", "mudurluk", "bakanligi", "bakanligindan", "kurumu", "kurumundan",
    "kurum", "baskanligi'ndan", "sekreterligi", "sekreterliginden", "daire", "dairesi", "personel", "insan",
    "kaynaklari", "grup", "birim", "birimi", "il", "ilce", "ve", "ile", "a", "s", "as", "anonim", "sirketi",
    "sirketinden", "mudurlugune", "valiligi", "valiliginden", "kaymakamligi", "kaymakamligindan", "baskani",
    "baskanligina", "merkezi", "merkezinden", "komutanligi", "komutanligindan", "the", "alim", "ilani",
    "ilan", "alacak", "alinacak", "isci", "sozlesmeli", "personeli", "surekli", "gecici", "adet", "yili",
    "duyurusu", "sinavi", "giris", "kadro", "kadrosu",
}
_BASLIK_GENEL = _GENEL | {"universitesi", "belediye", "belediyesi", "bakanligi", "ilani", "alimi", "alim"}

# Türkçe ablatif eklerini at (Rektörlüğünden -> Rektörlüğü)
_EK = re.compile(r"(ndan|nden|dan|den|tan|ten)$")


def kurum_kelimeleri(kurum: str):
    out = set()
    for k in kelimeler(kurum):
        if re.fullmatch(r"\d+", k):
            continue
        k2 = _EK.sub("", k) if len(k) > 7 else k
        if k in _GENEL or k2 in _GENEL or len(k2) < 2:
            continue
        out.add(k2[:7])  # kök benzeri: ilk 7 harf (universitesi/universitesinden eşleşsin)
    return out


def baslik_kelimeleri(baslik: str):
    return {k[:7] for k in kelimeler(baslik) if k not in _BASLIK_GENEL and not k.isdigit() and len(k) > 2}


def jaccard(a, b):
    a, b = set(a), set(b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def kapsama(a, b):
    """Küçük kümenin ne kadarı büyükte var."""
    a, b = set(a), set(b)
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


# ---------- MinHash ----------
# Ölçüm (Kasım 2026): aynı ilan memurlar.net ve Kariyer Kapısı'nda ~%95+ aynı;
# aynı kurumun iki FARKLI ilanı (AFAD uzman / denetçi yrd.) %68 benzer. Eşikler buna göre.
_P = 4294967311  # 2^32'den büyük asal
_N = 128
_KATSAYI = [((i * 2654435761 + 97) % _P or 1, (i * 2246822519 + 13) % _P) for i in range(1, _N + 1)]


def minhash(metin: str, k: int = 5) -> str:
    ks = kelimeler(metin)
    if len(ks) < 40:
        return ""
    parcalar = {zlib.crc32(" ".join(ks[i:i + k]).encode()) for i in range(len(ks) - k + 1)}
    imza = [min(((a * h + b) % _P) & 0xFFFFFFFF for h in parcalar) for a, b in _KATSAYI]
    return base64.b64encode(struct.pack(f"<{_N}I", *imza)).decode()


def minhash_benzerlik(m1: str, m2: str):
    if not m1 or not m2:
        return None
    a = struct.unpack(f"<{_N}I", base64.b64decode(m1))
    b = struct.unpack(f"<{_N}I", base64.b64decode(m2))
    return sum(1 for x, y in zip(a, b) if x == y) / _N


def parmak_izi(ilan) -> dict:
    return {
        "kurum": sorted(kurum_kelimeleri(ilan.kurum or ilan.baslik)),
        "baslik": sorted(baslik_kelimeleri(ilan.baslik)),
        "mh": minhash(ilan.metin) if ilan.metin else "",
        "son": ilan.son_basvuru.isoformat() if ilan.son_basvuru else None,
        "kadro": ilan.kadro,
        "kaynak": ilan.kaynak,
    }


def ayni_ilan_mi(p1: dict, p2: dict, ayni_kaynak: bool = False) -> bool:
    """İki parmak izi aynı ilana mı ait?"""
    haber = "haber" in (p1.get("kaynak"), p2.get("kaynak"))
    if ayni_kaynak and not haber:
        # Aynı site aynı ilanı iki farklı numarayla yayınlamaz (güncellemeler aynı numarada kalır).
        # Haberler hariç: aynı ilan için birçok gazete ayrı haber yapar.
        return False
    kurum = max(jaccard(p1["kurum"], p2["kurum"]), kapsama(p1["kurum"], p2["kurum"]) * 0.9)
    mh = minhash_benzerlik(p1.get("mh"), p2.get("mh"))

    if mh is not None:
        if mh >= 0.9 or (mh >= 0.8 and kurum >= 0.3):
            return True                      # metin neredeyse birebir aynı
        if mh >= 0.55 and kurum >= 0.5:
            # aynı kurumun benzer şablonlu farklı ilanları olabilir -> ek kanıt iste
            kadro_celisiyor = p1.get("kadro") and p2.get("kadro") and p1["kadro"] != p2["kadro"]
            bas = jaccard(p1["baslik"], p2["baslik"])
            baslik_celisiyor = p1["baslik"] and p2["baslik"] and bas < 0.15
            return not kadro_celisiyor and not baslik_celisiyor
        return False                         # iki metin de var ve yeterince benzemiyor

    if kurum < 0.6:
        return False
    # Metinlerden biri yoksa: kurum aynı + şu ipuçlarından biri
    if p1.get("son") and p1.get("son") == p2.get("son"):
        return True
    if p1.get("kadro") and p1.get("kadro") == p2.get("kadro"):
        return True
    bas = jaccard(p1["baslik"], p2["baslik"])
    if bas >= 0.5:
        return True
    if haber and kurum >= 0.8:
        return True    # haber başlıkları çok farklı yazılır; kurum aynıysa aynı ilan say
    # Tarih/kadro bilinmiyorsa ve başlıklar çelişmiyorsa (biri çok genelse) aynı say
    if not (p1.get("son") and p2.get("son")) and not (p1.get("kadro") and p2.get("kadro")):
        return bas >= 0.25 or not p1["baslik"] or not p2["baslik"]
    return False
