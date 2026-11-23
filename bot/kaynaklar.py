"""İlan kaynakları. Her fonksiyon sadece YENİ ilanları döndürür."""
import hashlib
import io
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import ayarlar
from .metin import (bbcode_temizle, il_bul, kadro_sayisi, sade, son_basvuru_bul, tireleri_birlestir,
                    tr_tarih_bul)
from .model import Ilan

log = logging.getLogger("kaynak")


def oturum() -> requests.Session:
    s = requests.Session()
    tekrar = Retry(total=3, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
                   allowed_methods=frozenset(["GET", "POST"]))
    s.mount("https://", HTTPAdapter(max_retries=tekrar))
    s.mount("http://", HTTPAdapter(max_retries=tekrar))
    s.headers.update({"User-Agent": ayarlar.USER_AGENT, "Accept-Language": "tr-TR,tr;q=0.9"})
    return s


def _iso_tarih(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:19]).date()
    except ValueError:
        return None


# =====================================================================
# 1) KARİYER KAPISI  (resmî kamu işe alım platformu, açık JSON API)
# =====================================================================
KK_API = "https://api.kariyerkapisi.gov.tr/api"
KK_ATLA_TURLER = ("görevde yükselme", "yurt dışı eğitim", "belge başvurusu", "tercih ilan",
                  "yeterlik sınav", "merkezi yerleştirme")
KK_AKADEMIK_TURLER = ("öğretim üyesi", "öğretim görevlisi", "araştırma görevlisi")


def kariyerkapisi_tara(s: requests.Session, yeni_mi):
    # Not: Kariyer Kapısı API'si yurt dışı sunuculardan (GitHub) gelen bağlantıları kabul etmeyebilir.
    # Bu yüzden kısa zaman aşımı + tekrar denemesiz istek; diğer kaynaklar beklemesin.
    r = requests.post(f"{KK_API}/ilan/GetIseAlimPage", timeout=(6, 25), headers=dict(s.headers),
                      json={"krM_ID": 0, "searchText": "", "il": "0", "ilanTuru": "0"})
    r.raise_for_status()
    liste = r.json().get("searchIlan")
    if liste is None:
        raise RuntimeError("Kariyer Kapısı yanıtında 'searchIlan' yok (site yapısı değişmiş olabilir)")

    sonuc = []
    for it in liste:
        guid = it.get("guid")
        if not guid or not yeni_mi(f"kariyerkapisi:{guid}"):
            continue
        tur = (it.get("ilanTuru") or "").strip(" ,")
        tur_k = tur.replace("İ", "i").lower()
        ilan = Ilan(
            kaynak="kariyerkapisi", kimlik=guid,
            baslik=(it.get("ilanBaslik") or "").strip(),
            kurum=(it.get("kurumAdi") or "").strip(),
            url=f"https://kariyerkapisi.gov.tr/IlanDetay?i={guid}",
            son_basvuru=_iso_tarih(it.get("bitTarih")),
            ek_bilgi=tur,
            kategoriler=[tur] if tur else [],
        )
        if any(a in tur_k for a in KK_ATLA_TURLER):
            ilan.kategoriler.append("ATLA")
        if any(a in tur_k for a in KK_AKADEMIK_TURLER):
            ilan.kategoriler.append("akademik")
        if "işçi" in tur_k or "işci" in tur_k:
            ilan.isci_kategorisi = True

        if it.get("ilanTipi") == 1:
            try:
                d = requests.post(f"{KK_API}/ilan/GetIlanPreviewPublic", json={"ilanGuid": guid},
                                  timeout=(6, 25), headers=dict(s.headers))
                d.raise_for_status()
                dj = d.json() or {}
                ilan.metin = bbcode_temizle(dj.get("ilanMetni") or "")
                if dj.get("eDevletteGorunsun") and dj.get("eDevletServisURL"):
                    ilan.basvuru_url = dj["eDevletServisURL"]
                elif dj.get("basvuruLinki"):
                    ilan.basvuru_url = dj["basvuruLinki"]
                if dj.get("kontenjan"):
                    ilan.kadro = str(dj["kontenjan"])
                time.sleep(0.5)
            except Exception as e:  # detay alınamazsa ilan atlanır, bir sonraki çalışmada tekrar denenir
                log.warning("Kariyer Kapısı detay alınamadı, sonra tekrar denenecek %s: %s", guid, e)
                continue
        else:
            ilan.basvuru_url = it.get("basvuruLinki") or ""
            if ilan.basvuru_url:
                ilan.url = ilan.basvuru_url

        ilan.kadro = ilan.kadro or kadro_sayisi(ilan.baslik, ilan.metin)
        ilan.il = il_bul(ilan.kurum, ilan.baslik, ilan.metin[:600])
        sonuc.append(ilan)
    return sonuc


# =====================================================================
# 2) RESMÎ GAZETE – Çeşitli İlanlar (her ilan ayrı PDF)
# =====================================================================
RG = "https://www.resmigazete.gov.tr"


def _pdf_metni(icerik: bytes) -> str:
    metin = ""
    try:
        from pypdf import PdfReader
        okuyucu = PdfReader(io.BytesIO(icerik))
        parcalar = []
        for sayfa in okuyucu.pages[:30]:
            try:
                parcalar.append(sayfa.extract_text() or "")
            except Exception:
                continue
        metin = "\n".join(parcalar)
    except Exception as e:
        log.info("pypdf okuyamadı (%s), pdfminer deneniyor", e)
    if len(metin.strip()) < 200:
        try:
            from pdfminer.high_level import extract_text
            metin = extract_text(io.BytesIO(icerik), maxpages=30) or metin
        except Exception as e:
            log.info("pdfminer de okuyamadı: %s", e)
            if not metin.strip():
                raise
    return tireleri_birlestir(metin)


def resmigazete_tara(s: requests.Session, yeni_mi, bugun):
    sonuc = []
    sayfa_bulundu = False
    for gun in (bugun, bugun - timedelta(days=1)):
        kod = gun.strftime("%Y%m%d")
        url = f"{RG}/ilanlar/eskiilanlar/{gun:%Y}/{gun:%m}/{kod}-4.htm"
        r = s.get(url, timeout=30)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        sayfa_bulundu = True
        html = r.content.decode("cp1254", errors="replace")
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not re.search(r"\.(pdf|htm)$", href, re.I) or not href.startswith(kod):
                continue
            kimlik = href.rsplit(".", 1)[0]
            anahtar = f"resmigazete:{kimlik}"
            if not yeni_mi(anahtar):
                continue
            kurum = re.sub(r"\s+", " ", a.get_text(" ")).strip().rstrip(":").strip()
            tam = urljoin(url, href)
            metin = ""
            try:
                d = s.get(tam, timeout=60)
                d.raise_for_status()
                if href.lower().endswith(".pdf"):
                    metin = _pdf_metni(d.content[:15_000_000])
                else:
                    metin = BeautifulSoup(d.content.decode("cp1254", errors="replace"), "lxml").get_text("\n")
                time.sleep(0.4)
            except Exception as e:
                log.warning("Resmî Gazete ilanı okunamadı, sonra tekrar denenecek %s: %s", tam, e)
                continue
            baslik = f"{_kurum_yalin(kurum)} – Resmî Gazete ilanı ({gun:%d.%m.%Y})"
            ilan = Ilan(kaynak="resmigazete", kimlik=kimlik, baslik=baslik, kurum=kurum, url=tam, metin=metin)
            ilan.son_basvuru = son_basvuru_bul(metin)
            ilan.kadro = kadro_sayisi("", metin)
            ilan.il = il_bul(kurum, metin[:800])
            sonuc.append(ilan)
    return sonuc, sayfa_bulundu


def _kurum_yalin(kurum: str) -> str:
    """'Düzce Üniversitesi Rektörlüğünden' -> 'Düzce Üniversitesi Rektörlüğü'"""
    k = kurum.strip().rstrip(":").strip()
    if re.search(r"[aeıioöuü](ndan|nden)$", k):      # Rektörlüğünden, Bakanlığından, Kurumundan
        return k[:-4]
    if re.search(r"(dan|den|tan|ten)$", k):          # Merkezden
        return k[:-3]
    return k


# =====================================================================
# 3) MEMURLAR.NET – ilan numaraları sırayla taranır (hiçbir ilan atlanmaz)
# =====================================================================
MEM = "https://ilan.memurlar.net"
MEM_KATEGORI_SAYFALARI = ["/", "/kategori/4b-ilanlari/?Expire=false", "/kategori/daimi-isci-ilanlari/?Expire=false",
                          "/kategori/gecici-isci-ilanlari/?Expire=false", "/kategori/genel-ilanlar/?Expire=false",
                          "/kategori/akademik-ilanlar-devlet/?Expire=false"]
MEM_ISCI = ("daimi işçi", "geçici işçi", "sydv", "engelli", "eski hükümlü", "terörle mücadele")
MEM_ATLA = ("kpss-a", "kpss-b", "özel okul", "yatay geçiş", "öğrenci alım", "yüksek lisans", "yurt dışı burs",
            "yök duyuru", "akademik ilanlar (vakıf)")


def _mem_cozumle(html: str, ilan_no: int):
    soup = BeautifulSoup(html, "lxml")
    art = soup.find("article")
    if not art:
        return None
    bc = art.find("div", class_="breadcrumb")
    kategoriler = []
    if bc:
        for a in bc.find_all("a"):
            t = a.get_text(strip=True)
            if t and t.lower() != "ana sayfa" and t not in kategoriler:
                kategoriler.append(t)
    h1 = art.find("h1")
    baslik = h1.get_text(" ", strip=True) if h1 else ""
    h2 = art.find("h2", class_="description")
    aciklama = h2.get_text(" ", strip=True) if h2 else ""
    kaynak_bilgi = ""
    for div in art.find_all("div", class_="info"):
        t = div.get_text(" ", strip=True)
        if t.lower().startswith("kaynak"):
            kaynak_bilgi = t.split(":", 1)[-1].strip()
    detay = art.find("div", class_="detail")
    metin = tireleri_birlestir(detay.get_text("\n", strip=True)) if detay else ""
    belgeler = [urljoin(MEM, a["href"]) for a in (detay.find_all("a", href=True) if detay else [])
                if re.search(r"\.pdf($|\?)", a["href"], re.I)]
    return {"no": ilan_no, "kategoriler": kategoriler, "baslik": baslik, "aciklama": aciklama,
            "kaynak": kaynak_bilgi, "metin": metin, "belgeler": belgeler}


def _mem_kurum(baslik: str) -> str:
    m = re.split(r"\s(\d[\d.]*|bin)\s|\s(?:alacak|alım|öğretim|sözleşmeli|personel|işçi|engelli|geçici)\b",
                 baslik, maxsplit=1, flags=re.I)
    return (m[0] if m else baslik).strip()


def memurlar_en_buyuk_no(s: requests.Session) -> int:
    en_buyuk = 0
    for yol in MEM_KATEGORI_SAYFALARI:
        try:
            r = s.get(MEM + yol, timeout=30)
            if r.ok:
                for n in re.findall(r"/ilan/(\d{4,7})/", r.text):
                    en_buyuk = max(en_buyuk, int(n))
        except requests.RequestException:
            continue
    return en_buyuk


def memurlar_tara(s: requests.Session, yeni_mi, durum: dict):
    """durum: {'son_no': int|None, 'eksikler': {no: ilk_deneme_ts}} (yerinde güncellenir)"""
    en_buyuk = memurlar_en_buyuk_no(s)
    if en_buyuk == 0:
        raise RuntimeError("memurlar.net sayfalarında hiç ilan numarası bulunamadı (site yapısı değişmiş olabilir)")

    son_no = durum.get("son_no")
    if not son_no:
        son_no = en_buyuk - ayarlar.ILK_CALISMA_GERIYE_ILAN
    eksikler = durum.setdefault("eksikler", {})
    simdi = time.time()

    denenecek = sorted({int(n) for n in eksikler})[:200]  # daha önce boş dönen numaraları tekrar dene
    sonuc, bos_seri, no, taranan = [], 0, son_no, 0
    en_son_dolu = son_no

    def isle(n):
        r = s.get(f"{MEM}/ilan/{n}", timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return _mem_cozumle(r.content.decode("cp1254", errors="replace"), n)

    for n in denenecek:
        try:
            v = isle(n)
        except requests.RequestException:
            continue
        if v:
            eksikler.pop(str(n), None)
            sonuc.append(v)
        elif simdi - eksikler.get(str(n), simdi) > 3 * 86400:
            eksikler.pop(str(n), None)

    while taranan < ayarlar.MEMURLAR_MAKS_TARAMA:
        no += 1
        taranan += 1
        v = isle(no)
        time.sleep(0.25)
        if v is None:
            bos_seri += 1
            if no <= en_buyuk:
                eksikler.setdefault(str(no), simdi)
            if no > en_buyuk and bos_seri >= ayarlar.MEMURLAR_ARDISIK_BOS_LIMIT:
                break
            continue
        bos_seri = 0
        en_son_dolu = no
        sonuc.append(v)

    # boş numaralar için: en son DOLU numarayı kaydet; ondan sonrakiler bir dahaki sefere yine denenir
    durum["son_no"] = max(en_son_dolu, durum.get("son_no") or 0)
    for k in list(eksikler):
        if int(k) > durum["son_no"]:
            eksikler.pop(k)

    ilanlar = []
    for v in sonuc:
        anahtar = f"memurlar:{v['no']}"
        if not yeni_mi(anahtar):
            continue
        metin = v["metin"]
        if len(sade(metin)) < 300 and v["belgeler"]:
            # metin PDF ekindeyse onu oku
            try:
                d = s.get(v["belgeler"][0], timeout=60)
                if d.ok and d.content[:4] == b"%PDF":
                    metin = (metin + "\n" + _pdf_metni(d.content[:15_000_000])).strip()
            except Exception as e:
                log.warning("memurlar PDF eki okunamadı: %s", e)
        kat_k = [k.replace("İ", "i").lower() for k in v["kategoriler"]]
        ilan = Ilan(
            kaynak="memurlar", kimlik=str(v["no"]), baslik=v["baslik"], kurum=_mem_kurum(v["baslik"]),
            url=f"{MEM}/ilan/{v['no']}", metin=metin, kategoriler=list(v["kategoriler"]),
            ek_bilgi=f"Kaynak: {v['kaynak']}" if v["kaynak"] else "",
        )
        ilan.isci_kategorisi = any(any(i in k for i in MEM_ISCI) for k in kat_k) or "işkur" in v["kaynak"].lower()
        if any(any(a in k for a in MEM_ATLA) for k in kat_k):
            ilan.kategoriler.append("ATLA")
        if any("akademik" in k for k in kat_k):
            ilan.kategoriler.append("akademik")
        ilan.son_basvuru = son_basvuru_bul(v["aciklama"]) or son_basvuru_bul(metin)
        ilan.kadro = kadro_sayisi(v["baslik"], metin)
        ilan.il = il_bul(v["baslik"], metin[:600])
        ilanlar.append(ilan)
    return ilanlar


# =====================================================================
# 4) GOOGLE HABERLER – "KPSS şartsız" haberleri (güvenlik ağı)
# =====================================================================
HABER_SORGULARI = ['"KPSS şartsız" alım', '"KPSS\'siz" personel alımı', '"KPSS şartı aranmaksızın"',
                   '"KPSS şartı olmadan" alım']
_HABER_KPSSSIZ = re.compile(r"kpss('?siz| sartsiz| sarti (aranmaksizin|olmadan|aranmiyor|yok)| olmadan)")
_HABER_KURUM = re.compile(r"(universite|belediye|bakanlig|mudurlug|baskanlig|kurumu|a\.s|hastane|vakf|"
                          r"genel mudurluk|ajansi|valilig|kaymakamlig|tcdd|ptt|trt|thy|botas|tki|eti maden|"
                          r"karayollari|dsi|ogm|meteoroloji|kizilay|tubitak|havelsan|aselsan|tusas|roketsan)")
_HABER_GENEL = re.compile(r"(hangi kurumlar|nasil basvurulur\?*$|ilanlari (yayimlandi|yayinlandi)|"
                          r"\biskur is ilanlari\b|bu (hafta|ay)|gunun ilanlari|guncel ilanlar|liste(si)?$)")
# Soru / tahmin / açıklama haberleri (somut ilan değil)
_HABER_SPEKULASYON = re.compile(r"(\?|ne zaman|nasil|acikladi|iddia|bekleniyor|merak edilen|yeni detay|"
                                r"neler\b|hangi\b|kimler|olacak mi|yapilacak mi)")


def haber_tara(s: requests.Session, yeni_mi):
    sonuc, gorulen = [], set()
    for sorgu in HABER_SORGULARI:
        url = ("https://news.google.com/rss/search?q=" + quote_plus(sorgu + " when:2d")
               + "&hl=tr&gl=TR&ceid=TR:tr")
        r = s.get(url, timeout=30)
        r.raise_for_status()
        kok = ET.fromstring(r.content)
        for item in kok.iter("item"):
            baslik = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            kaynak = (item.findtext("source") or "").strip()
            parcalar = re.split(r"\s+[-|–]\s+", baslik)   # "Başlık - Site Adı - Son Dakika" -> "Başlık"
            if len(parcalar) > 1 and len(parcalar[0]) >= 25:
                baslik = parcalar[0].strip()
            t = sade(baslik)
            if not _HABER_KPSSSIZ.search(t) or not _HABER_KURUM.search(t) or _HABER_GENEL.search(t):
                continue
            if _HABER_SPEKULASYON.search(t):
                continue
            if not re.search(r"(alim|alacak|alinacak|isci|personel|memur|eleman)", t):
                continue
            kimlik = hashlib.sha1(t.encode()).hexdigest()[:16]
            if kimlik in gorulen or not yeni_mi(f"haber:{kimlik}"):
                continue
            gorulen.add(kimlik)
            try:
                yayin = parsedate_to_datetime(item.findtext("pubDate"))
                if datetime.now(yayin.tzinfo) - yayin > timedelta(days=2):
                    continue
            except Exception:
                pass
            ilan = Ilan(kaynak="haber", kimlik=kimlik, baslik=baslik, url=link,
                        kurum=re.split(r"\b(kpss|\d)", baslik, maxsplit=1, flags=re.I)[0].strip(" :-'"),
                        ek_bilgi=kaynak)
            ilan.kadro = kadro_sayisi(baslik)
            ilan.il = il_bul(baslik)
            ilan.son_basvuru = tr_tarih_bul(baslik) if "son" in t else None
            sonuc.append(ilan)
        time.sleep(1)
    return sonuc
