"""Kanal profil resmini çizer ve (TELEGRAM_TOKEN varsa) kanala yükler.
Çalıştırma: python araclar/kanal_resmi.py  -> kanal_resmi.png
"""
import io
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BOYUT = 640
FONT_YOLLARI = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"]


def font(boyut):
    for y in FONT_YOLLARI:
        if os.path.exists(y):
            return ImageFont.truetype(y, boyut)
    return ImageFont.load_default(boyut)


def ortala(d, metin, f, y, renk):
    x0, y0, x1, y1 = d.textbbox((0, 0), metin, font=f)
    d.text(((BOYUT - (x1 - x0)) / 2 - x0, y - y0), metin, font=f, fill=renk)
    return x0, y0, x1, y1


def ciz() -> Image.Image:
    img = Image.new("RGB", (BOYUT, BOYUT))
    d = ImageDraw.Draw(img)
    # Lacivertten koyu teal'e dikey geçiş
    ust, alt = (14, 32, 66), (10, 92, 98)
    for y in range(BOYUT):
        t = y / BOYUT
        d.line([(0, y), (BOYUT, y)], fill=tuple(int(ust[i] + (alt[i] - ust[i]) * t) for i in range(3)))

    # Hafif parlama
    parilti = Image.new("L", (BOYUT, BOYUT), 0)
    ImageDraw.Draw(parilti).ellipse((90, 40, 550, 420), fill=70)
    parilti = parilti.filter(ImageFilter.GaussianBlur(90))
    img = Image.composite(Image.new("RGB", (BOYUT, BOYUT), (60, 140, 170)), img, parilti)
    d = ImageDraw.Draw(img)

    # "KPSS" ve üstünde kırmızı çapraz çizgi (= KPSS yok)
    f_kpss = font(150)
    x0, y0, x1, y1 = d.textbbox((0, 0), "KPSS", font=f_kpss)
    gen, yuk = x1 - x0, y1 - y0
    sol = (BOYUT - gen) / 2
    ust_y = 180
    d.text((sol - x0, ust_y - y0), "KPSS", font=f_kpss, fill=(255, 255, 255))
    pay = 8
    d.line([(sol - pay, ust_y + yuk + pay), (sol + gen + pay, ust_y - pay)], fill=(235, 64, 64), width=22)

    # Alt yazı
    f_alt = font(58)
    ortala(d, "ŞARTSIZ", f_alt, ust_y + yuk + 48, (255, 196, 61))
    f_alt2 = font(38)
    ortala(d, "KAMU İLANLARI", f_alt2, ust_y + yuk + 125, (210, 232, 240))
    return img


def yukle(png: bytes):
    import requests
    token = os.environ["TELEGRAM_TOKEN"]
    kanal = os.environ.get("TELEGRAM_KANAL", "@kpsssizilanlar")
    r = requests.post(f"https://api.telegram.org/bot{token}/setChatPhoto", data={"chat_id": kanal},
                      files={"photo": ("kanal.png", png, "image/png")}, timeout=60)
    print(r.status_code, r.text[:300])
    r.raise_for_status()
    if not r.json().get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    tampon = io.BytesIO()
    ciz().save(tampon, "PNG")
    png = tampon.getvalue()
    with open("kanal_resmi.png", "wb") as f:
        f.write(png)
    print("kanal_resmi.png yazıldı,", len(png), "bayt")
    if os.environ.get("TELEGRAM_TOKEN"):
        yukle(png)
