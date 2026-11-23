import html
import logging
import time

import requests

from . import ayarlar

log = logging.getLogger("telegram")


class TelegramHata(Exception):
    pass


def _cagir(metot: str, veri: dict):
    if not ayarlar.TELEGRAM_TOKEN or not ayarlar.TELEGRAM_CHAT_ID:
        raise TelegramHata("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID ayarlı değil")
    url = f"https://api.telegram.org/bot{ayarlar.TELEGRAM_TOKEN}/{metot}"
    for deneme in range(4):
        try:
            r = requests.post(url, json=veri, timeout=30)
        except requests.RequestException as e:
            time.sleep(3 * (deneme + 1))
            hata = e
            continue
        j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code == 429:
            time.sleep(int(j.get("parameters", {}).get("retry_after", 5)) + 1)
            continue
        if j.get("ok"):
            return j["result"]
        hata = j.get("description") or r.text[:200]
        if r.status_code < 500:
            break
        time.sleep(3)
    raise TelegramHata(str(hata))


_deneme_sayac = 0

# İlan mesajları bu işaretlerle başlar ve kanala gider. Diğer her şey (başlangıç, özet, uyarı)
# sadece yöneticinin kendi sohbetine gider; böylece uyarılar asla herkese açık kanala düşmez.
ILAN_ISARETLERI = ("\U0001F7E2", "\U0001F7E1", "\u2754")


def hedef_sohbet(metin: str) -> str:
    if ayarlar.TELEGRAM_KANAL and metin.startswith(ILAN_ISARETLERI):
        return ayarlar.TELEGRAM_KANAL
    return ayarlar.TELEGRAM_CHAT_ID


def gonder(metin: str) -> int:
    global _deneme_sayac
    if ayarlar.DENEME:
        _deneme_sayac += 1
        print("\n----- [DENEME] Telegram mesajı -----\n" + metin, flush=True)
        return _deneme_sayac
    sonuc = _cagir("sendMessage", {
        "chat_id": hedef_sohbet(metin), "text": metin, "parse_mode": "HTML",
        "disable_web_page_preview": True,
    })
    return sonuc["message_id"]


def duzenle(mesaj_id: int, metin: str):
    if ayarlar.DENEME:
        print(f"\n----- [DENEME] {mesaj_id} numaralı mesaj güncellendi -----\n" + metin, flush=True)
        return
    try:
        _cagir("editMessageText", {
            "chat_id": hedef_sohbet(metin), "message_id": mesaj_id, "text": metin,
            "parse_mode": "HTML", "disable_web_page_preview": True,
        })
    except TelegramHata as e:
        # 48 saatten eski mesajlar düzenlenemeyebilir, sorun değil
        log.info("Mesaj düzenlenemedi: %s", e)


def kacis(s) -> str:
    return html.escape(str(s or ""), quote=False)
