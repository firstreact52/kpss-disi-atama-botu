from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Ilan:
    kaynak: str                 # "kariyerkapisi" | "resmigazete" | "memurlar" | "haber"
    kimlik: str                 # kaynak içinde benzersiz numara
    baslik: str
    url: str
    kurum: str = ""
    metin: str = ""
    basvuru_url: str = ""
    son_basvuru: Optional[date] = None
    kategoriler: list = field(default_factory=list)
    isci_kategorisi: bool = False
    kadro: Optional[str] = None
    il: Optional[str] = None
    ek_bilgi: str = ""          # ör. Kariyer Kapısı ilan türü

    @property
    def anahtar(self) -> str:
        return f"{self.kaynak}:{self.kimlik}"


KAYNAK_ADLARI = {
    "kariyerkapisi": "Kariyer Kapısı",
    "resmigazete": "Resmî Gazete",
    "memurlar": "memurlar.net",
    "haber": "Google Haberler",
}
# Tekrar durumunda hangi kaynağın bilgisi daha güvenilir (küçük = daha resmî)
KAYNAK_ONCELIK = {"kariyerkapisi": 0, "resmigazete": 1, "memurlar": 2, "haber": 3}
