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

## Tek Windows giriş noktası

`scripts/central-windows.ps1` varsayılan önizleme, yazma veya ağ yok.
`-Mode Prepare` mevcut izole hazırlık testlerini çalıştırır ve temiz HEAD için
başarı işareti oluşturur. `-Mode Status` salt okunur pilot ön kontrolüdür.
`-Mode StartPanel` aynı test edilmiş commit ile localhost panelini başlatır;
önceden yapılandırılmış sınırlı yerel okuma girdilerini korur. Giriş freni açık,
uzaktan erişim ve otomatik sağlayıcı/görev başlatma yok. AI/DexTerm/Futures özel
çalışma ortamları ve PWA cihaz erişimi ayrıca kurulur. Gerçek Windows testi bekler.

## DexTerm portfoy deney baglantisi

Ayri DexTerm arastirma worktree'sinde mevcut, incelenmis Python ortami ile
`python -m tools.solana_paper_positions --database PATH --risk-mode` komutu
cevrimdisi tarihsel pozisyon raporu uretir. Basarili ciktiyi UTF-8 JSON olarak
ayri yerel dosyada saklayin (Windows PowerShell 5.1 varsayilan UTF-16 yonlendirmesi
yerine UTF-8 kullanin). `CYBERBOT_DEXTERM_REPLAY_REPORT` bu dosyayi gosterir.
Dosya yolu GitHub'a kaydedilmez; islem kasalariyla cakismasi engellenir.
Panel raporun muhasebe tutarliligini ve yetki bayraklarini kontrol eder. Deney
USDC nakdi, gerceklesen K/Z, acik/kapali pozisyon sayilari ve deney giris freni
ayri alt bolumde gorunur. Acik pozisyon varken deney son degeri bilinmez.
Gozlem portfoyunun SOLANA satirinda canli kasa degerleri bos kalir; rapor toplam
portfoye eklenmez. Rapor gecmisi, kaynak tazeligi veya gercek dolum kaniti degildir.
Rapor uretimi su an manuel; surekli DexTerm calismasi ve canli sanal motor
baglantisi ayrica dogrulanmalidir. Eski Solana saglayicisi geri yuklenmez.

## AI öğrenme hafızası ve denetim

Bot Gelişimi ekranı mevcut /api/integration/ai envanterinden beş piyasanın
ayrı kapsam ve rapor sayılarını gösterir. Bu sayılar benzersiz eğitim örneği
veya model başarısı değildir. /api/integration/ai/learning manuel okuma ile
AI dalının ai-dashboard-1 raporunu tüketir. Öğrenme planı, koordinatör, hata ve
karar hafızası, model yaşam döngüsü, Windows görev ve risk denetimi gösterilir.
Öğrenme ve risk kararları yalnız BTCUSDT / Binance USD-M araştırma kapsamındadır;
diğer piyasalara genellenmez. Ham tahminler, yollar ve kimlik bilgileri gösterilmez.
AI PR #1 ve bağımlılıkları aynı checkout'ta doğrulanmadan bağlantı aktif olmaz.
Varsayılan kapalıdır; panel eğitim, zamanlanmış görev veya emir başlatmaz.

## Ortak haber ve bildirim arşivi

CYBERBOT_NOTIFICATION_DB ve CYBERBOT_RESEARCH_NEWS_DB, ayrı bildirim çalışanın
ürettiği notifications.sqlite3 ve research-news.sqlite3 dosyalarına işaret eder.
Mevcut Haber Merkezi /api/integration/inbox ve /api/integration/news üzerinden
son 50 uygun kaydı salt okunur gösterir. BINANCE_FUTURES kaynak etiketi FUTURES
olarak eşlenir; küresel kayıtlar seçilen piyasa ile gösterilir. Okunmamış sayısı
sadece görünen pencereyi kapsar. Ham olay anahtarları, abonelik bilgisi ve URL'ler
aktarılmaz. Haber içeriği ve fiyat etkisi doğrulanmış kabul edilmez.
Bu bağlantı ayrı çalışanın kurulumunu, kaynak yetkilerini, bildirim kuyruğunu,
push aboneliğini, VAPID yapılandırmasını veya cihaz teslim testini yapmaz.
Mobil erişim mevcut güvenli erişim korumasına tabidir; mutasyon açılmaz.

## Bildirim motorunun birleşik sürümü

Bildirim çalışma motoru ve çevrimdışı testleri aynı geliştirme dalına seçici
aktarılmıştır. Mevcut panel ve erişim kontrolü korunur. Windows başlatıcısında
`-Mode StartPanel -ConnectNotifications` aynı kullanıcının .cyberbot-private
altındaki üç salt okunur girdiyi seçer; çalışanı başlatmaz, abonelik oluşturmaz.
Ayrı bildirim ortamı için tools/notification_setup.ps1 önizleme ile incelenir;
kurulum ve çalıştırma açık onay ister. Worker varsayılan olarak başlamaz;
--enable olmadan çalışmaz, --push olmadan cihaz teslimi yapmaz. Mevcut RSS
arşiv köprüsü CYBERBOT_NOTIFICATION_NEWS_BRIDGE=1 ile ayrıca etkinleştirilir;
canlı haber kaynakları ve veri hakları ayrıca doğrulanır. Push API, service
worker ve gerçek cihaz teslimi henüz merkezi panelde etkin değildir.

## DexTerm merkezi tarama motoru (seçici aktarım)

DexTerm MCP tarama, aday değerlendirme ve arşiv modülleri aynı checkout'a
aktarıldı. Eski Solana sağlayıcısı, genel havuz taraması ve pilot geri yüklenmedi.
Ayrı, incelenmiş DexTerm checkout'u sabit PIN ve Node çalışma ortamı gerektirir.
Önce kaynak ve bağımlılık haklarını doğrulayın; gerçek emir ve giriş yetkisi yok.
Açık izin ve CYBERBOT_PILOT_KILL_SWITCH=1, CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED=1,
CYBERBOT_DEXTERM_ARCHIVE ile aynı ayrı arşiv yolu gerekli. Tek döngü:
`python -m tools.dexterm_central_cycle --dexterm-root PATH --database PATH --enable`.
Varsayılan kapalı. Döngü sadece tarama ve aday incelemesini arşivler; panel
mevcut arşiv okuyucusu ile görür. Likidite araştırma eşiği 100000 USD olarak
önceki aday politikasından korunur; güvenlik veya işlem uygunluğu kanıtı değil.
Havuz köprüsü ve canlı kotasyon toplama ayrı sağlayıcı uyarlaması gerektirir.
Aşağıdaki güncelleme ile arşiv doğrulayıcısı ve çevrimdışı replay aktarıldı.

## DexTerm çevrimdışı pozisyon motoru (güncelleme)

Sadece DexTerm arşiv kayıtlarını okuyan dexterm_paper_positions, dexterm_paper_replay,
dexterm_exit_validation, dexterm_exit_history ve dexterm_route_accounting modülleri
aktarıldı. Eski sağlayıcıya ağ çağrısı veya işlem motoru bağlantısı yoktur. Kesin
miktarlı çıkış kayıtları arşivde doğrulanabilir; yeni canlı çıkış kotasyonu çekilmez.
Mevcut hak onayı ve giriş freni ile, ayrı CYBERBOT_DEXTERM_ARCHIVE ve
CYBERBOT_DEXTERM_REPLAY_REPORT yolları tanımlıyken `python -m tools.dexterm_publish_replay --enable`
çevrimdışı deney raporunu atomik yazar. Varsayılan kapalı, veri kapsamı kesilmişse
rapor yayımlanmaz. İki arşiv okuması tek atomik anlık görüntü değildir; rapor
üretirken arşiv yazıcısını durdurun. Geçerli açık pozisyon fiyatı yoksa değer boş
kalır. Canlı sanal yürütme, süreklilik ve ileri öğrenme kanıtı değildir.

## DexTerm AI öğrenme ve deney hafızası

Geçmiş kesin miktarlı kotasyonlardan kronolojik veri seti, sınır örtüşmesi
ayıklaması, strateji karşılaştırması, lojistik referans, isteğe bağlı LightGBM,
River gecikmeli replay, konsensüs ve adaptif ağırlık deneyi aktarılmıştır.
Gemini değerlendirme paketi manuel ve çevrimdışıdır. Üretim modeli kaydedilmez,
otomatik terfi yapılmaz. Deney kapısı en az 100 erken/50 geç örnek, her bölümde
her sınıftan 15 örnek ve 5 farklı mint gerektirir. Kesilmiş arşiv engeldir.
Ayrı CYBERBOT_DEXTERM_MODEL_HISTORY SQLite yolu ve mevcut arşiv yolu gerekir.
Arşiv yazıcısı kapalıyken, açık araştırma hakları ve giriş freni ile
`python -m tools.dexterm_central_learning --enable` engel/deney kaydını yazar.
İsteğe bağlı deney için --allow-experiment; modeller için --lightgbm --river
--adaptive. Varsayılan üretim eğitimi yok. Bot Gelişimi sayfasında DexTerm hafızası
/api/integration/ai/dexterm üzerinden salt okunur gösterilir. River ölçümü sabit
model ölçümü ile doğrudan karşılaştırılamaz. Canlı ileri performans, yeni çıkış
kotasyonu toplama ve PC üzerinde yerel model çalışma zamanı henüz doğrulanmadı.
