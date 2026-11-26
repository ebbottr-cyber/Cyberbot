# Cyberbot — Obsidian

Bağımsız Türkçe piyasa araştırması ve yalnızca sanal işlem platformu. EBBot veya Daily Stock Analysis kaynak kodu kullanılmamıştır.

## Sürüm 0.1
- FastAPI, SQLite, mobil uyumlu Türkçe web paneli.
- BIST, NASDAQ, XETRA ve Solana için sentetik örnek veriler.
- Uzun pozisyon sanal defteri: ücret, fiyat kayması, işlem riski, pozisyon limiti, günlük kayıp ve düşüş sınırı.
- Basit hareketli ortalama geçmiş veri deneyi.
- Gerçek emir, cüzdan imzalama, özel anahtar veya borsa işlem API'si yoktur.
- Canlı veri, cüzdan analizi, AI ajanları, gelişmiş laboratuvar ve PWA kurulumu henüz hazır değildir.

## Yerel çalıştırma (Python 3.11/3.12)
```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn cyberbot.api:app --host 127.0.0.1 --port 8000
```
Panel: http://127.0.0.1:8000

Test: `python -m unittest discover -s tests -v`.
Veri dosyası: `var/paper.sqlite3` (CYBERBOT_DB ile değiştirilebilir).
Uygulama yalnız yerel istemciler için tasarlanmıştır. İnternete açmayın; uzaktan erişim için ayrı kimlik doğrulama, TLS ve güvenlik incelemesi gerekir.
Tüm fiyatlar **sentetik ve USD cinsindendir**; gerçek piyasa performansı değildir.
