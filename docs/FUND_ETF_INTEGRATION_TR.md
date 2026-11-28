# Fon & ETF — aktarım kontrol listesi

Dal: feature/free-fund-etf-research. Hedef: integration/cyberbot-master. Main/master ve diğer dallar değiştirilmemelidir. CI sonuçları commit SHA bazında GitHub Actions üzerinden doğrulanmadan birleştirme yapılmamalıdır.

## Ortak dosyalar

- cyberbot/api.py: uygulama başında fund_etf_router kaydı ve home() yanıtında with_fund_menu çağrısı. Hedef dalın diğer yönlendiricileri korunur.
- cyberbot/web/index.html: ortak kaynak dosyası taban haline geri alındı; menü bağlantısı fund_etf_api.with_fund_menu tarafından mevcut Futures menüsünün önüne sunucu tarafında eklenir. Böylece hedef panelin kendi değişiklikleri üzerine yazılmaz. Menü sözleşmesi tarayıcı testiyle kontrol edilir.
- Yeni cyberbot/fund_etf_api.py ve cyberbot/web/fund_etf.html: salt okunur JSON ve Türkçe TEFAS/ETF alt sekmeleri. Mevcut uygulama erişim kontrolü, CSP ve no-store politikası kullanılır.
- Yeni .github/workflows/fund-etf-ci.yml: yalnız geliştirme dalı ve hedefe açılan Fon & ETF PR'ı için Windows/Linux 3.11/3.12 + Chromium masaüstü/mobil testi. Diğer CI dosyaları korunur.

## Kurulum ve yerel kontrol

Python 3.11/3.12. Önce mevcut Cyberbot sanal ortamında:
```
python -m pip install -r requirements.txt -r requirements-fund-etf.txt
python -m unittest discover -s tests -p "test_fund_etf*.py" -v
python -m pip install "playwright>=1.50,<2"
python -m playwright install chromium
python -m tools.fund_etf_browser_smoke
```
Linux Chromium sistem bağımlılıkları gerekirse playwright install --with-deps chromium. Windows'ta tzdata IANA saat dilimleri için gereklidir.

config/fund-etf.example.json dosyasını var/fund-etf-config.json olarak yerel kopyalayın. Varsayılan ayar veri veya emir oluşturmaz. Kullanım hakkı olan fon/ETF kataloglarını ve fiyat arşivini ilgili import fonksiyonları ile yükleyin. SQLite ve konfigürasyon dosyalarını Git'e eklemeyin.

```
python -m tools.fund_etf_worker --status
python -m tools.fund_etf_worker
python -m tools.fund_etf_worker --loop --interval 3600
```
Windows: scripts/fund-etf-windows.ps1 -Mode Status / Once / Continuous. Register devre dışı görev oluşturur; Start açık operatör seçimi gerektirir. Ağ varsayılan kapalıdır. Yahoo etkinleştirmek için yalnız kullanım hakkı ve sağlayıcı koşulları teyit edilince CLI --enable-yahoo. TEFAS için sağlayıcıya ait ücretsiz otomatik resmi API teyit edilmedi; izinli yerel CSV dışa aktarımını worker yeniden okur. Ücretli fallback yok. context_imports ile rights_confirmed=true olan yerel macro_csv/news_json dosyaları içe alınır. Veri üreticisinin lisansı, tarih ve kaynak doğrulaması ayrıca gerekir.

Gemini: GEMINI_API_KEY yalnız yerel ortamda, gemini.enabled=true, free_tier_confirmed=true, model ve limit (en çok 10/döngü). Ücretsiz kota ve faturalandırma kullanıcı tarafından teyit edilmeli; hata halinde yerel Türkçe gerekçe. Gemini işlem veya model terfi yetkisine sahip değildir. Ollama bu modülde kullanılmaz.

## Merkezi döngü

refresh_jobs -> veri kalite kontrolü -> kategori bazlı tarama -> makro/haber filtresi -> Türkçe araştırma kararı -> isteğe bağlı geçmiş walk-forward/ML -> JSON panel. portfolios, optimizations ve paper_replays ayrı isteğe bağlı konfigürasyon listeleridir. paper_replays fiyatı arşivden alır, kullanıcı tanımlı ürün kuralları/takvim/emir dizisini replay eder; gerçek emir yok. Gerçek zamanlı sanal otomatik emir üretimi veya doğrulanmış valör kaynağı mevcut değildir. P&L yalnız bekleyen emir/temettü olmadan ve yayınlanmış fiyatla hesaplanır; vergi, hisse bölünmesi ve gerçek yürütme simülasyonu henüz yok. Gerçek piyasa testi değildir.

## Kabul koşulları

Dört OS/Python işi, Chromium işi ve hedef dalda tam regresyon; gerçek CI logları gereklidir. Canlı sağlayıcı kimliği, lisans, ücretsiz kota, ürün valör/temettü verisi ve iPhone Safari yerel cihaz doğrulaması ayrı kabul koşullarıdır. CI fixture verisi gerçek piyasa performansı değildir. Entegrasyon için hedef dalın son haliyle çakışma kontrolü ayrıca yapılmalıdır. Bu belge test sonucu iddia etmez.

## Otomatik sanal emir defteri

paper_accounts varsayılan boş listedir. Her kayıt: id, market, symbol, currency, source, initial_cash, enabled=true, terms_confirmed=true, rules, sessions ve isteğe bağlı dividends/max_entry_fraction. Hesap başına izole sanal bakiye; varsayılan giriş payı %20, üst sınır %25. Ürün koşulları ve takvim hesap açılışından sonra sabittir; değişiklik yeni hesap kimliği gerektirir. Worker yalnız yeni, taze ve risk süzgecinden geçen araştırma sinyalinden emir üretir; aynı fiyat gözleminde tekrar emir yoktur. Fiyatlama yerel bugünden sonraki bir seans olmalıdır. Tamamlanmış yerel günler üzerinden valör replay; gün içi yeni emirler bloke gösterilir, gerçek yürütme değildir. SQLite defteri fiyat arşivi yanında <arşiv-adı>.auto-paper.sqlite3 olarak saklanır. Eski fiyat değişirse otomatik işlem engellenir. İşlem geçmişi ve durum özeti salt okunur panelde gösterilir. Gerçek emir ve broker bağlantısı yoktur. Veri yenileme başarısız olduğunda merkezi döngü durur, valör ilerlemez; ayrı operatör incelemesi gerekir. Takvim/temettü değişikliği ve vergi yönetimi otomatik değildir.

## Bot Gelişimi Merkezi

Ortak cyberbot/development_api.py dosyasında yalnız panel() yanıtına with_fund_development eklenir. Statik development.html değiştirilmez; ayrı fund_etf_development_fragment.html mevcut ekranın sonuna eklenir. /api/fund-etf/development salt okunur; diğer piyasaların sayaçları değişmez. Tamamlanmış walk-forward ve ortak model karşılaştırması, fiyat serisi SHA-256 özeti + kapsam + politika sürümü + aşama ile tekilleştirilir. Yetersiz sonuçlar sayılmaz; örtüşen geçmiş dönemler bağımsız kanıt değildir. Arşiv yanında <arşiv-adı>.development.sqlite3 tutulur; özel arşiv yolu için CYBERBOT_FUND_ETF_DEVELOPMENT ayarlanmalıdır. Sanal performans yalnız güncel panel snapshot'ından gösterilir. Model terfisi, canlı kârlılık ve sürekli öğrenme doğrulanmış değildir. evaluation_limit > 0 ve evaluate_models=true yerel yapılandırmada seçilmelidir. Bu iki yeni SQLite defteri henüz ortak yedekleme kapsamına alınmamıştır.

## Veri sağlayıcıları (2026-11-28)

TEFAS yeni web JSON fiyat geçmişi adaptörü: provider=tefas, market=TEFAS, symbol, currency=TRY, months=60, rights_confirmed=true, free_access_confirmed=true. Teknik şema: https://github.com/eneshikmetkayim/Tefas-API/blob/main/TEFAS_API.md (topluluk dokümanı, resmi kullanım izni değildir). Otomatik erişim hakkı ve ücretsiz kullanım teyit edilmeden etkinleştirmeyin. 403/429, HTML, hatalı yanıt ve boş geçmişte durur. Canlı erişim test edilmedi.

Stooq: provider=stooq, market=ETF, symbol (katalog kodu), provider_symbol (Stooq kodu), currency, rights_confirmed=true, free_access_confirmed=true, identity_reviewed=true. Kimlik, borsa ve para birimi eşleşmesi operatör tarafından teyit edilir. sources.ETF açıkça seçilir; Yahoo ve Stooq geçmişleri birleştirilmez. Stooq'un düzeltilmiş fiyatları Yahoo kapanışlarıyla eşdeğer olmayabilir. source_checks: market, symbol, currency, primary, secondary, tolerance (varsayılan 0.01), min_overlap (20). Uyumsuzluk tüm yeni alış incelemelerini durdurur. Kaynak otomatik değiştirilmez; ücretli fallback yoktur. CSV yolu korunur. Tüm yeni ayarlar varsayılan kapalıdır. Önceki TEFAS CSV sınırlaması bu deneysel adaptörle genişletildi, canlı servis ve kullanım hakkı kabul koşulları devam ediyor.

## SQLite yedekleme ve kurtarma

Yeni örnek konfigürasyonda backup.enabled=true ve backup.destination=var/fund-etf-backups. Mevcut konfigürasyonlar değiştirilmez; alan yoksa devre dışıdır. Worker tarama sonrasında günün ilk doğrulanmış yedeğini oluşturur; aynı UTC gününde yeniden kullanır, yeni sanal işlem/öğrenme defteri oluştuğunda yeni paket oluşturur. Daha yeni değişiklikler o günün ilk paketinde bulunmaz. Yedekleme hatası rapora yansır, tamamlanmış sanal işlemler geri alınmaz. Otomatik eski dosya silme yoktur; disk alanı izlenmeli ve harici diske kopyalanmalıdır. Her SQLite dosyası online backup API ile alınır, bütünlük ve SHA-256 doğrulanır; dosyalar arası atomiklik garanti edilmez. Tutarlı manuel yedek için tüm yazıcıları durdurun. Ana fiyat arşivi zorunlu, henüz oluşmamış sanal defter ve gelişim defteri manifestte eksik olarak belirtilir. Konfigürasyon, kaynak CSV dosyaları, API anahtarları ve snapshot yedeğe dahil değildir. Bunlar ayrı ve güvenli biçimde saklanmalıdır.

Komutlar (sanal ortam):

```
python -m tools.fund_etf_backup backup
python -m tools.fund_etf_backup verify --bundle var/fund-etf-backups/PAKET
python -m tools.fund_etf_backup restore --bundle var/fund-etf-backups/PAKET --destination var/fund-etf-recovered
```

Kurtarma yalnız yeni klasörde yapılır. Worker otomatik başlatılmaz, mevcut arşiv değiştirilmez. Kayıtları inceleyip yapılandırma ve dosya yollarını yeniden onaylamak gerekir. Günlük paket tam felaket kurtarma veya şifreli dış yedek yerine geçmez. CI ve gerçek Windows cihaz testi kabul koşuludur.

## Otomatik makro veri toplama

context_collection varsayılan boş. Her sağlayıcı için rights_confirmed=true ve free_access_confirmed=true açık onay gereklidir. FRED: provider=fred, series=FEDFUNDS (örnek), unit=percent, lookback_days=365, yerel FRED_API_KEY. EVDS3: provider=evds, series=TP.DK.USD.A (örnek), unit=TRY/USD, frequency=daily, yerel EVDS_API_KEY. Seri ve birim operatör tarafından doğrulanmalıdır. EVDS aylık/çeyreklik tarih biçimi bu sürümde desteklenmez. FRED güncel vintage, EVDS güncel gözlem alınır; gerçek ilk yayın günü olduğu varsayılmaz. İlk görülme UTC günü arşivde released olarak kullanılır; mevcut iki günlük güvenlik tamponu uygulanır. Değişmemiş değerler yeniden yazılmaz, aynı gün çelişkili revizyon bloke edilir. Bu yöntem tarihsel vintage arşivinin yerine geçmez.

KAP: provider=kap_export, file=<izinli yerel JSON>. Biçim {exported_at: ISO-8601 saat dilimli zaman, items: mevcut fund_etf_news.ingest şemasında KAP kayıtları}. 24 saatten eski dosya engellenir. KAP resmi REST veri yayını dağıtım sözleşmesi gerektirir; ücretsiz doğrudan otomatik KAP erişimi doğrulanmadı. Dışa aktarımın üretilmesi ayrı süreçtir; tam kapsama doğrulanmış değildir. İş başarısızsa mevcut araştırma döngüsü engellenir. API anahtarları Git'e yazılmaz; sağlayıcı hatalarında URL veya anahtar gösterilmez. httpx mevcut requirements.txt içinde bulunur. Canlı API çağrıları ve ücretsiz kullanım koşulları yerel kabul testinde doğrulanmalıdır.

Kaynaklar: https://fred.stlouisfed.org/docs/api/fred/series_observations.html ; https://evds3.tcmb.gov.tr/ ; https://www.kap.org.tr/tr/about/genel-bilgi .

## Tek komutlu Windows kurulumu

Geliştirme dalının veya onaylanmış entegrasyon sürümünün çalışma kopyasında PowerShell ile:

```powershell
& .\scripts\setup-fund-etf-windows.ps1
```

Kurulum yalnız var/fund-etf-venv altında Python 3.11/3.12 sanal ortamı oluşturur; mevcut .venv ve .venv-futures değiştirilmez. PyPI bağımlılıkları, pip check, model importları, İstanbul saat dilimi, Fon & ETF unit testleri ve varsayılan olarak Chromium masaüstü/mobil smoke testleri kontrol edilir. Tarayıcı dosyaları var/fund-etf-browsers altında tutulur. Mevcut var/fund-etf-config.json üzerine yazılmaz; yoksa güvenli örnek oluşturulur. -CheckOnly mevcut kurulumda bağımlılık yüklemeden testleri yeniden çalıştırır; -SkipBrowser tarayıcı kısmını atlar. -PythonExecutable ile uygun Python yolu seçilebilir. Başarısız adım kurulumu durdurur, yarım ortam otomatik silinmez. Ağ erişimi yalnız bağımlılık ve Chromium kurulumu için gerekir; canlı veri sağlayıcısı veya gerçek emir başlatılmaz.

Kurulumdan sonra, yalnız yerel veri/ürün koşulları ve ücretsiz erişim onaylanmışsa:

```powershell
& .\scripts\fund-etf-windows.ps1 -Mode Status
& .\scripts\fund-etf-windows.ps1 -Mode Once
```

Register ve Start ayrı operatör işlemleridir. Mevcut görev başka çalışma kopyasına aitse Start/Stop engellenir. Kurulum Git dallarını değiştirmez. Ana uygulama ayrı Cyberbot ortamından sunulmaya devam eder; araştırma worker'ı yeni izole ortamdan çalışır. Özel veritabanı yolları varsa API ortam değişkenlerini ayrıca ayarlayın. Gerçek Windows kurulumu, canlı API erişimi ve iPhone Safari kabul testi henüz doğrulanmadı.
