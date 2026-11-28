# Fon & ETF — aktarım kontrol listesi

Dal: feature/free-fund-etf-research. Hedef: integration/cyberbot-master. Main/master ve diğer dallar değiştirilmemelidir. CI sonuçları commit SHA bazında GitHub Actions üzerinden doğrulanmadan birleştirme yapılmamalıdır.

## Ortak dosyalar

- cyberbot/api.py: yalnız fund_etf_router kaydı. Hedef dalda mevcut yönlendiricilere ek olarak taşınmalı; tüm dosya üzerine yazılmamalı.
- cyberbot/web/index.html: ana masaüstü/mobil modül menüsüne /fund-etf bağlantısı. Hedef panelin diğer navigasyon öğelerini koru.
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
