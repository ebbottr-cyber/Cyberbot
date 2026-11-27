# Merkezi entegrasyon ve PC teslim kontrolü

Bu dal mevcut Obsidian web/PWA ana ekranını korur. Yeni durum API'leri mevcut
erişim koruması altında salt okunurdur; hiçbir işlem, model terfisi, veri indirme
veya zamanlanmış görev başlatmaz.

## Yerel bağlantılar (Windows)

- CYBERBOT_DEXTERM_ARCHIVE: DexTerm araştırma dalının yerel SQLite arşiv yolu.
  application_id 0x43594458 ve user_version 1 gerekir. İçe aktarım zamanı veri
  kotasyon zamanı değildir. Eski Solana işlem/radar kodu geri yüklenmez.
- CYBERBOT_AI_PANEL_ENABLED=1: yalnızca ayrı AI araştırma dalı başarıyla
  birleştirildikten, yerel veri hakları ve çalışma zamanı incelendikten sonra.
  Varsayılan kapalı; model yükleme/eğitme başlatılmaz.
- CYBERBOT_NOTIFICATION_HEALTH_FILE: bildirim çalışanın ürettiği yerel
  notification-health.json yolu. Görev durumu cihaz teslim kanıtı değildir.

Gerçek yollar, kimlik bilgileri ve kaynak arşivler GitHub'a yüklenmez.
Ayarları yerel PowerShell oturumunda ve mevcut güvenli başlatıcıyla kullanın;
başlatıcı ayarları ayrıca kontrol edilmelidir.

## Sürüm kontrolü

1. PR #3 tam Linux/Windows/Chromium CI ve eşzamanlı main değişiklikleri.
2. PR #1 AI dalı testleri ve incelemesi; ayrı araştırma modülleri doğrulanmadan
   açılmaz. AI paneli mevcut modülü isteğe bağlı okur.
3. DexTerm dalından sadece istenen kapsam ve bağımlılıkların seçici aktarımı;
   eski Solana sağlayıcı kodunu geri getirmeyin.
4. Bildirim/haber dalı: mevcut erişim kontrolü, CSRF, CSP ve service worker ile
   uyumlu gerçek route ve cihaz bildirim entegrasyonu ayrıca incelenir.
5. BIST, NASDAQ, XETRA veri yetkisi; Binance public veri; DexTerm runtime.
6. PC üzerinde setup-windows.ps1, start-windows.ps1 ve güvenli PWA bağlantısı,
   sağlık kontrolleri, gerçek veriyle ileri gözlem testi. Gerçek emir kapalı.

## Panel API'leri

- GET /api/integration/status
- GET /api/integration/ai
- GET /api/integration/notifications

Yalnızca mevcut durum kayıtları. Birleşik canlı yürütme veya tamamlanmış cihaz
kurulumu anlamına gelmez.

## Ortak gözlem portföyü ve risk

GET /api/integration/portfolio, BIST/NASDAQ/XETRA/FUTURES gözlem kasalarını
mevcut pilot muhasebesinden okur. TRY, USD ve USDT ayrı gösterilir; XETRA pilotu
EUR fiyatını USD hesabına dönüştürür. Eski Solana pilotu bu kapsamdan çıkarılır;
DexTerm USDC portföyü bağlanana kadar değerler boş kalır. Sentetik demo bakiyeleri,
araştırma replay sonuçları ve gözlem kasaları birleştirilmez. Taze değerleme yoksa
kasa değeri, günlük K/Z ve düşüş bilinmez. Giriş freni salt okunur; yerel risk
koşulları emir yetkisi değildir. Ayrı okuma anları atomik değildir.
