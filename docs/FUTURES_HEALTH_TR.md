# Futures Health Monitor & Diagnostic Logs V1

Windows Prepare sonrası salt okunur rapor:
```powershell
.\scripts\futures-windows.ps1 -Mode Health
```

Supervisor/Watchdog Windows modlarında teşhis kaydı etkinleştirilir.
Ayrı CYBERBOT_FUTURES_DIAGNOSTICS_DB SQLite dosyasında sembol başına son
10000 olay tutulur. Son 24 saatin tutulan olay sayıları ve yeniden başlatma
beklemeleri, son 30 olay, veri toplama, ileri tahmin MAE/yön doğruluğu,
AI hafıza ve sanal risk güvenliği tek JSON raporunda görünür.
Ham hata metni, API anahtarı, ağ gövdesi veya tüm ortam değişkenleri
kaydedilmez. Yalnız izinli durum kodları ve sınırlı sayısal alanlar.

Doğrudan CLI için CYBERBOT_FUTURES_DIAGNOSTICS_ENABLED=1 gerekir (yazma).
Watchdog kendi ve çocuk olaylarını kaydeder; çocukta çift kayıt kapalıdır.
Yazma hatası terminale bildirilir, mevcut pozisyon gözlemi durdurulmaz.
Bu durumda teşhis kaydı eksik olabilir. Son olayın tazeliği süreç veya
canlı bağlantı kanıtı değildir. Ayrı kaynak anlık görüntüleri atomik
ortak kasa raporu değildir. Kayıtlar yereldir; Telegram, panel,
uzak telemetri veya gerçek emir yoktur.
