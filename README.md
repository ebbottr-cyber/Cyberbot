# Cyberbot — Obsidian

Bağımsız Türkçe piyasa araştırması ve yalnızca sanal işlem platformu. EBBot'un yalnız veri modülleri ve veri adaptörleri lisans bildirimleri korunarak kullanılmıştır; eski işlem motoru ve paneli taşınmamıştır.

## Sürüm 0.1
- FastAPI, SQLite, mobil uyumlu Türkçe web paneli.
- BIST, NASDAQ, XETRA ve Solana için sentetik örnek veriler.
- Uzun pozisyon sanal defteri: ücret, fiyat kayması, işlem riski, pozisyon limiti, günlük kayıp ve düşüş sınırı.
- Basit hareketli ortalama geçmiş veri deneyi.
- Gerçek emir, cüzdan imzalama, özel anahtar veya borsa işlem API'si yoktur.
- AI araştırma, laboratuvar, öğrenme, model ve PWA modüllerinin ilk sürümleri mevcuttur; gerçek veri/model ve cihaz doğrulaması ayrıca gereklidir.

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

## EBBot veri bağlantısı (yalnız veri)
`CYBERBOT_EBBOT_DB` değişkeni, kullanım hakkı olan ve `stock_daily` tablosu içeren mevcut SQLite dosyasının yoluna ayarlanır. Kaynak veritabanı salt okunur açılır, kopyalanmaz veya değiştirilmez. Beş dakikalık arşivin farklı şeması ayrıca doğrulanmalıdır. BIST/NASDAQ/XETRA etiketleri araştırma seçeneğidir; borsa üyeliği ve canlı fiyat doğrulanmaz.
`CYBERBOT_SOLANA_READ_ENABLED=1` ile isteğe bağlı salt okunur GeckoTerminal/DEX Screener taraması açılabilir. Varsayılan kapalıdır; manuel tarama dışında ağ isteği yoktur. Panel: /data. Gerçek gözlemler sentetik işlem motorundan ayrıdır. Veri hakları operatörce doğrulanmalıdır. Kaynak lisansları THIRD_PARTY_NOTICES.md içindedir.

## Trader Merkezi
`/traders`: açık Solana adresi için son kesinleşmiş işlem imzalarını salt okunur RPC ile gösterir. Ağ erişimi varsayılan kapalıdır. `CYBERBOT_SOLANA_READ_ENABLED=1` gereklidir. İmzalar takas, gerçekleşmiş getiri veya kopyalanabilirlik kanıtı değildir. Manuel gölge araştırması için `CYBERBOT_SHADOW_FILE` yerel JSON dosyası tanımlanabilir. Her satır: wallet,event,signal_at,entry_at,exit_at,entry_price,exit_price,fee_bps,slippage_bps; fiyat ve maliyet alanları ondalık metin, tarihler ISO-8601 zaman dilimli. Dosya yoksa sentetik demo. Otomatik takas sınıflandırması, Jupiter teklifleri, sürekli izleme ve zincirden P&L çıkarma henüz yoktur. ETRE yaklaşımından esinlenildi; GPL kaynak kodu taşınmadı.

## Toplu veri toplama
[EBBot veri toplama talimatları](docs/DATA_COLLECTION_TR.md). GitHub envanter işi fiyat arşivi yerine aday listesi ve sınırlı Solana gözlemi üretir.

## Model Merkezi
`/models` çevrimdışı tahmin kıyaslaması. İsteğe bağlı yerel Ollama bağlantısı: `CYBERBOT_LOCAL_LLM_ENABLED=1` ve `CYBERBOT_OLLAMA_MODEL` kurulu yerel modelin adı. Ollama ayrı kurulur; Cyberbot yalnız 127.0.0.1:11434 üzerinden sentetik rapor özeti gönderir, model indirmez. Yerel modelin kendi ayarları operatörün sorumluluğundadır. LLM yanıtı doğrulanmamış metindir; emir ve otomatik terfi yoktur. Chronos henüz bağlı değildir.

### İsteğe bağlı Chronos 2
Ayrı `requirements-chronos.txt` bağımlılık dosyası; standart Cyberbot kurulumuna dahil değildir. Önceden edinilmiş, güvenilir ve kullanım hakkı kontrol edilmiş yerel Chronos 2 ağırlık dizinini `CYBERBOT_CHRONOS_PATH` ile belirtin, `CYBERBOT_CHRONOS_ENABLED=1` ile etkinleştirin. Model Merkezi üzerinden manuel kıyaslama. Otomatik ağırlık ve piyasa verisi indirme yoktur. Referans: https://huggingface.co/amazon/chronos-2 ve https://github.com/amazon-science/chronos-forecasting. Gerçek çıkarım testi henüz yapılmadı.

## Obsidian PWA
Mobil manifest, Apple Touch ikonu ve ağ bağlantısı olmadığında yalnız uyarı gösteren service worker hazır. Safari üzerinden Paylaş → Ana Ekrana Ekle, ancak iPhone'un Cyberbot sunucusuna güvenli HTTPS erişimi yapılandırılmalıdır. Şu anda uygulama sadece localhost kabul eder; PC'nin LAN adresini açmak veya portu internete yönlendirmek çözüm değildir. API yanıtları ve işlem verileri önbelleğe alınmaz, çevrimdışı işlem kuyruğu yoktur. Gerçek iPhone testi ve güvenli uzaktan erişim henüz tamamlanmamıştır.

## Özel mobil erişim
[Windows / Tailscale Serve kurulum talimatları](docs/REMOTE_ACCESS_TR.md). Uzaktan erişim varsayılan kapalı; yalnız yetkili Tailscale kimliği ve tam HTTPS adresi kabul edilir. Gerçek cihaz kurulumu henüz yapılmadı.

Toplu tarihsel fiyat indirme kapatılmıştır; ağ indirme komutları da engellenmiştir. Eski artifact dosyaları kullanım hakkı doğrulanmadan kullanılmamalıdır.

## Windows kolay kurulum ve bakım
Cyberbot'un ayrı checkout klasöründe PowerShell: ` .\\scripts\\setup-windows.ps1 ` (Python 3.11/3.12 gerekir; bağımlılık kurar ve testleri çalıştırır). Ardından ` .\\scripts\\start-windows.ps1 ` ile yerel panel http://127.0.0.1:8765 . Bu başlatıcı dış sağlayıcıları ve uzaktan erişimi kapalı tutar, EBBot'a dokunmaz. Sunucu logları var/logs dizininde; erişim logu kapalıdır. Sağlık: /health veya `.venv\\Scripts\\python.exe -m tools.ops health`. Yedek: `.venv\\Scripts\\python.exe -m tools.ops backup` (yalnız Cyberbot SQLite dosyaları, var/backups; aynı veri dizininde çalıştırın). Yedekler ayrı zaman damgalı klasörlerde, bütünlük ve SHA-256 manifesti ile saklanır. Otomatik silme veya geri yükleme yapılmaz. Yedekler dosya bazında tutarlıdır, iki DB arasında ortak anlık görüntü garanti edilmez. Gerçek Windows PC kurulumu denenmedi.

## Araştırma zamanlayıcısı (isteğe bağlı)
Tek döngü: `python -m tools.worker`. Sürekli: `python -m tools.worker --loop --interval 900` (Ctrl+C durdurur). Windows: `scripts/worker-windows.ps1`. Varsayılan sentetik, aynı deney yeniden öğrenme olarak sayılmaz. İzinli yerel arşiv için açıkça `--market BIST --symbol THYAO.IS` ve CYBERBOT_EBBOT_DB gerekir. `--daily-backup` eklenirse UTC gününde en çok bir başarılı yerel yedek. Sistem Sağlığı sayfası son döngüyü gösterir; worker kayıtları var/worker.sqlite3 içinde en çok 1000 kayıt, mevcut yedek kapsamı dışında. Windows oturum açılışında çalıştırmak için ayrı ve isteğe bağlı `scripts/register-worker-windows.ps1 -Register`; görev otomatik başlatılmaz, mevcut görev üzerine yazılmaz. Görev adı Cyberbot-Research-Worker; Görev Zamanlayıcı'dan durdurulabilir. Gerçek PC kurulumu henüz yapılmadı.

## Sentetik stres testi
`python -m tools.stress --steps 240`: dört ayrı senaryo, mevcut paper motoru ve geçici SQLite defteri; ana portföy ve EBBot dosyalarına dokunulmaz. Obsidian Risk Merkezi altında `/stress`. Her senaryo tek varsayımsal UTC oturumudur; gerçek piyasa performansı değildir. Otomatik gerçek veya sanal portföy işlemi yoktur.

## Piyasa kasaları ve kur
Ana panel `/api/portfolio/status`: BIST 45000 TRY, NASDAQ/XETRA/Solana 1000 USD ayrı SQLite defterleri (`var/paper-markets/`). Eski `var/paper.sqlite3` ve eski API korunur, yeni kasalara aktarılmaz. XETRA sentetik USD araştırma hesabıdır, gerçek EUR dolumu değildir. USD/TRY için `CYBERBOT_FX_FILE` ile yerel JSON dosyasını belirtin: `{"usdtry":"45.00","observed_at":"2026-11-26T12:00:00Z","source":"example only"}`. Bu sadece biçim örneğidir, güncel kur değildir. Kullanım hakkı olan canlı besleme dosyayı güncellemeli; 300 saniyeden eski veya geçersiz girdide toplam hesaplanmaz. Otomatik kur sağlayıcısı henüz bağlı değil. Birleşik kur K/Z geçmişi henüz yok; native işlem K/Z güncel kurla çevrilir. Piyasa riskleri ayrı hesaplanır. Mevcut yeni piyasa dosyaları bakım yedeğine dahil edilir.

## Strateji dayanıklılığı
Strateji Laboratuvarı'nda manuel dayanıklılık deneyi: 1000 blok-bootstrap yolu, 60 gözlem ufku, maliyet duyarlılığı ve deneysel güvenilirlik puanı. BIST 45000 TRY, diğer sentetik piyasa hesapları 1000 USD; yalnız yerel bakiye tahmini, FX getiri modeli yok. Puanlar kalibre edilmiş olasılık değildir; yetersiz örneklem veya referans stratejiler puanlanmaz. Araştırma tam sermaye varsayımıyla yapılır, gerçek risk motoru performansı değildir. Yeni veri indirme ve otomatik terfi yok.

## Strateji turnuvası
Strateji Lab. altında piyasa/sembol bazlı keşif ve ayrılmış son 60 gözlem testi. En az 240 gözlem gerekir. BIST/NASDAQ/XETRA yerel arşiv veya dört piyasa için sentetik senaryo; gerçek Solana tarihsel arşivi bağlı değil. Araştırma şampiyonu yalnız deney kapsamındadır, ana motora geçirilmez. Turnuva sonuçları öğrenme SQLite dosyasında ayrı tabloda saklanır. Tekrarlanan veri yeni kayıt değildir; örtüşen veri bağımsız doğrulama sayılmaz.

## Piyasa rejimi
Strateji Laboratuvarı'nda turnuva piyasası için nedensel 20 gözlemli rejim etiketi ve ileri dönem net getiri gözlem ortalamaları. Volatilite yıllıklandırılmaz, eşikler sabit ve deneysel. Sonuç tek sembolü temsil eder, strateji seçme veya işlem yetkisi yok. Sentetik dört piyasa veya mevcut izinli yerel hisse arşivi; yeni veri indirilmez.

## Adaptif gölge araştırması
Strateji Lab. içindeki adaptif deney, 20 gözlemli bloklar için geçmiş kanıta dayalı araştırma adayı veya nakit seçer. Karar sonraki blokta test edilir; ana portföye emir yok. Sentetik veya izinli mevcut arşiv, 240–1000 gözlem. Geçmiş replay sonuçları canlı performans kanıtı değildir; otomatik zamanlayıcıya bağlı değildir.

## Strateji hafızası
Adaptif gölge araştırması sonucu, aynı öğrenme SQLite dosyasında ayrı strateji hafızası ve kanıt tablolarına kaydedilir. İki aktif zararlı blok veya %10 üzeri düşüş karantina; üç yeni olumlu aktif blok yeniden izleme. Örtüşen ve eski dönemler yeni kanıt değildir. Sentetik ve tarihsel hafıza ayrıdır. Karantina yalnız araştırma önerilerini filtreler, gerçek ve ana sanal emirleri yönetmez. Eşikler deneysel; canlı ileri test henüz yok.

## Ortak araştırma döngüsü
Windows araştırma başlatıcısı artık `--full-research` kullanır; CLI: `python -m tools.worker --full-research --loop --interval 900`. Dört sentetik piyasa için 7 araştırma aşaması; açıkça seçilen `--market` ve `--symbol` ile yalnız o yerel arşiv sembolü (240+ gözlem). Aynı tamamlanmış veri/parmak izi tekrar hesaplanmaz. Sonuçlar öğrenme DB'de, özetler Sistem Sağlığı ekranında. Kural tabanlı analiz ve temel tahmin kıyaslaması kullanılır; gerçek LLM/Chronos çalıştırılmaz. Ağ, ana sanal işlem defteri ve EBBot arşivine yazma yok. PC'de henüz başlatılmadı.

## Kripto Futures
Obsidian /futures: bağımsız 1000 USDT sentetik hesap, BTCUSDT/ETHUSDT, LONG/SHORT, 2x, izole teminat ve varsayımsal fonlama/likidasyon. Gerçek Binance API bağlantısı yok; ETRE Hyperliquid kaynak kodu kullanılmadı. Genel kasa için FX JSON içindeki usdtusd alanı (1 USDT başına USD, aynı zaman damgası) gereklidir. Futures henüz araştırma zamanlayıcısına bağlı değil. Toplu veri indirme kapalıdır.

## Futures araştırma bağlantısı
Futures merkezi BTC/ETH için bağımsız tek gözlem LONG/SHORT araştırması, walk-forward, Monte Carlo, son 60 gözlem turnuvası, kural tabanlı analiz/rejim ve temel tahmin kıyaslaması sunar. 1000 USDT, 2x izole, ayrı sentetik model; ana Futures defteri kullanılmaz. Tam otomatik araştırma döngüsü 4 mevcut piyasa + BTC/ETH için 2 Futures işi çalıştırır ve aynı girdiyi tekilleştirir. Chronos 2 isteğe bağlı yerel Futures sentetik testine bağlandı; gerçek model çalışması doğrulanmadı. Futures'a özgü adaptif karantina ve canlı veri henüz yok; yeni veri indirme yok.

Futures adaptif gölge araştırması: BTC/ETH için ayrı geçmiş blok kanıtı, rejime bağlı aday seçimi, kalıcı karantina ve sıfır likidasyonlu üç olumlu aktif blokla yeniden izleme. Bir likidasyon (baz veya maliyet stresi) karantina nedenidir. Sentetik araştırma döngüsüne bağlı; eski v1 kayıtları korunur. Gerçek/ana sanal emir ve otomatik terfi yok.

## Bot Gelişimi Merkezi
/development salt okunur ekranı, beş piyasanın kayıtlı ortak araştırma deneylerini veri modu ve sembol bazında gösterir. En yeni sembol kayıtları, strateji puanı, Monte Carlo zarar yolu, gölge performans, mevcut kalıcı karantina ve temel model MAE/yön ölçümleri. Kayıt yoksa boş durum; çalışma zamanı veya kârlılık doğrulanmış sayılmaz. Eski /learning manuel deney ekranı ayrı korunur.

## İsteğe bağlı kur adaptörü
Twelve Data exchange_rate, USD/TRY ve USDT/USD (iki ayrı kaynak zaman damgası). Varsayılan kapalı; kullanım ve kişisel panel gösterim hakkı doğrulanmadan etkinleştirmeyin. Yerel ortam: CYBERBOT_FX_PROVIDER_ENABLED=1, CYBERBOT_FX_RIGHTS_CONFIRMED=1, CYBERBOT_TWELVEDATA_KEY (gizli; commit etmeyin). Ayrı terminalde `python -m tools.fx --loop`, aynı iki etkinleştirme değişkeniyle paneli başlatın. Varsayılan var/fx-provider.json; mevcut CYBERBOT_FX_FILE önceliklidir. 240 saniye aralık, yerel kalıcı günlük 720 kredi sınırı (diğer uygulamaların tüketimi dahil değildir). Her iki kur geçerliyse atomik yayın; eksik/eski kurda toplam yok. Hafta sonu eski FX saklanmaz gibi gösterilmez. Ücretli abonelik yok, API anahtarı/erişim ve veri gösterim hakları doğrulanmadı. Kaynak: https://twelvedata.com/docs/ai/ai-data-assistant ve https://twelvedata.com/pricing .

## Bilgi ve haber merkezi
`/knowledge` salt okunur araştırma haritası ve Obsidian uyumlu ZIP dışa aktarımı; `/news` manuel haber ve takvim referansları. Ayrıntılar: [Bilgi ve haber planı](docs/KNOWLEDGE_NEWS_TR.md). Canlı haber akışı ve otomatik haber etkisi ölçümü henüz yok.

İsteğe bağlı FED/ECB RSS pilotu ve kural tabanlı haber araştırması eklendi. Varsayılan kapalı, kullanım izinleri yerel olarak onaylanmalıdır. Ayrıntılar docs/KNOWLEDGE_NEWS_TR.md.

Haber bilgi ağı `/api/news/graph`: kaynak, piyasa, kategori, strateji hipotezi ve operatör kanıt bağlantısı. Vault Haberler.canvas yalnız kayıt kapsamı özetini taşır; fiyat etkisi doğrulanmaz.

Haber olay penceresi araştırması: 5/15/60/1440 dk, yayın ve ilk kayıt zamanı ayrı; yalnız izinli yerel 1/5 dk kapanış dosyasıyla, eksik pencereler ölçülmez. Sentetik örnek ayrıdır. docs/KNOWLEDGE_NEWS_TR.md.

Haber performans hafızası: görünür, izinli yerel olay ölçümlerinden çakışma/tekrar denetimli betimsel istatistik; 20 olay altı sonuç yok. /news ve /api/news/memory. Tahmin eğitimi veya strateji terfisi değildir.

AI Haber Analiz Merkezi: 7 kural tabanlı rol ve isteğe bağlı, kısıtlı yerel Ollama kontrol listesi sıralaması. Haber yönü, güvenilirlik olasılığı veya işlem tavsiyesi üretmez. Varsayılan model kapalı.

Ana Obsidian panelinde haber, ekonomik takvim ve araştırma uyarı özeti; yerel API 60 saniyede okunur, gerçek veri akışı başlatılmaz. Bildirimler panel içidir.

Futures grafiği: son 200 kayıt, gerçek geçmiş uydurulmaz. Yedek kurtarma: `python -m tools.ops recover --source <yedek-klasörü> --output var/recovery` doğrulanmış yeni kopya üretir; aktif kasalar ve ayarlar değişmez. Worker dahil değildir; otomatik geçiş yok.

Canlı sanal test hazırlığı: `/api/readiness` ve Sistem Sağlığı ekranı beş piyasanın yerel durumunu salt okunur inceler; canlı fiyatla işlem başlatmaz. Mevcut kasalar sentetiktir.

Bağımsız yerel gözlem pilotu: `python -m tools.observed_pilot status`. Varsayılan kapalı. BIST/NASDAQ örnek sembolleri; izinli yerel bid/ask girdileri, sonraki gözlem sanal dolumu. Ayrı DB; otomatik giriş, canlı veri ve gerçek emir yok. Pilot yedeği henüz kapsam dışı.

XETRA SAP.DE gözlem pilotu: EUR hisse fiyatı / USD kasa, ayrı taze EUR/USD alış-satış girdisi ve açık kur kullanım izni. Yerel dosya; gerçek kur veya borsa bağlantısı yok.

Solana Meme gözlem pilotu: `python -m tools.solana_pilot status`, varsayılan kapalı. Tek mint/havuz, operatörün izinli fiyat/derinlik/güvenlik beyanı; gerçek swap veya güvenlik doğrulaması yok. docs/ROADMAP.md.

Futures gözlem pilotu: `python -m tools.futures_pilot status`, varsayılan kapalı. 2x izole model, ayrı mark/bid/ask, beyanlı derinlik, 8 saatlik varsayımsal fonlama ve eksik olay engeli; gerçek borsa takvimi/likidasyon doğrulanmadı.

Gözlem Performansı (/pilot): beş pilotun ayrı para birimlerinde kapanış K/Z, model ücretleri, fonlama ve güncel risk görünümü. Salt okunur; gerçek veri, kârlılık veya yürütme doğrulaması değildir.
