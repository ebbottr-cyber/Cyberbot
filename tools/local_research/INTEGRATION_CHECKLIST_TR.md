# AI araştırma dalı — ana dal entegrasyon kontrolü

## İncelenen Git sürümleri (27 Kasım 2026)

- Ortak ata: ff84d033beea0283c2ecf32e783a1d45a88b0a2d
- Ana dal: 4b1ecc7802860970f6a013ef377bde4d66cd88b2
- Araştırma dalı: 78f1c2187364bf89f25f2357475f7aca911a016b
- Araştırma dalı 160 commit ileride, 88 commit geride. Sayılar bu denetime özgüdür.
- Offline entegrasyon #650 ve Watchdog #640 başarılı. Başlangıç kontrolü #681
  denetim sırasında kuyrukta. Birleşik dal testi yapılmadı.

## Birleştirme sırası

1. Ana dalın ve araştırma dalının güncel SHA değerlerini yeniden al. İncelenen
   SHA'lar değişmişse fark listesini tekrar değerlendir. Açık PR #1'i kontrol et.
2. Temiz, ayrı bir entegrasyon dalı/worktree kullan. Ana dalı veya yerel veri
   dizinlerini doğrudan değiştirme. Çatışmada otomatik ours/theirs kullanma.
3. Ortak ataya göre iki dalın da değiştirdiği dosyalar:
   - .github/workflows/ci.yml: ana daldaki 3.12 Futures AI bağımlılık kurulumu
     ve Futures Windows önizlemesini, araştırma dalındaki AI script parse,
     önizleme ve readiness JSON denetimleriyle birlikte koru.
   - cyberbot/pilot_decisions.py: ana dalın Futures davranışı, izinleri ve
     güvenlik kapıları korunmalı. Araştırma dalının observed_regime importu
     ve regime_diagnostic alanını yalnızca tanısal olarak ekle; gerçek karar
     HOLD ve emir bayrakları değişmemeli. İki dosya için üç yönlü diff incele.
4. Ana dalın Solana eski sağlayıcı/araç/test silmelerini geri getirme. Dexterm
   çalışması ayrı yürütülüyor. Araştırma dalındaki eski SOLANA market-memory
   kapsamını yeni Dexterm bağlantısı olarak sunma; kapsamı ayrıca değerlendir.
5. Ana dalın db_paths.py değişiklikleri Futures AI, training, forward ve
   diagnostics veritabanlarını ayırıyor. Yerel araştırma dosyaları ile
   ortam değişkenleri üzerinden ayarlanmış bu yolların çakışmadığını doğrula.
   checked() koruma kontrolü yapar ama dönen sözlük bütün korunan yolları
   içermediğinden yalnızca dönüş değerine güvenme.
6. Futures AI bridge ile Chronos araştırma protokolü ayrı kalmalı:
   Futures köprüsü kendi özelliklerini, hedeflerini ve risk raporlarını
   kullanır; local_research modeli BTCUSDT 1m Chronos/mean/AR1 tahminleri
   üzerinden çalışır. Aynı model adı bir veri protokolü eşitliği değildir.
   MAE ölçümlerini tek lider tablosunda karıştırma.
7. AI dashboard snapshot() salt okunur rapor üretir; henüz HTTP/PWA route'u
   oluşturmaz. Panel entegrasyonu kimlik doğrulamalı ve salt okunur olmalı.
   Model metni, anahtar, yerel dosya yolu veya ham piyasa verisi yayınlama.
8. Birleşik kaynak üzerinde Windows ve Linux 3.11/3.12 test matrisi, browser
   smoke, PowerShell parse/preview, sentetik AI entegrasyonu ve Futures
   güvenlik testlerini çalıştır. Yerel çalışma ortamlarının native inference
   doğrulaması ayrı yapılır. Başarı kesinleşmeden ana dala merge yapma.

## Yerel PC başlangıç sırası (henüz uygulanmadı)

- Mevcut süreçleri, görevleri ve yerel veritabanı yedeklerini kontrol et.
- ai-readiness-windows.ps1 varsayılan salt okunur kontrolü çalıştır.
- setup-ai-windows.ps1 -IncludeReviewRuntime ile önizle; yalnız eksik
  ortamları operatör onayıyla kur. Mevcut Chronos'u koru.
- Offline native model smoke, kaynak sınırları ve veri kullanım hakkını doğrula.
- Araştırma görevlerini önce devre dışı kaydet; mevcut görevleri ezme.
- Chronos ve River ileriye dönük tahminlerini ve panel raporlarını doğrula.
- Yeterli yeni veri yoksa LightGBM/paired/challenger işleri beklemeli.
- Gerçek emirler ve otomatik model terfisi kapalı kalır. Sanal emir sisteminin
  hazır olduğu bu rapordan çıkarılamaz.

Bu belge birleşik kaynak kodu veya başarılı merge kanıtı değildir.
