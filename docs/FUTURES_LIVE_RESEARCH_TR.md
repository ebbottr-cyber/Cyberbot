# Futures canlı veri ve sanal test hazırlığı V1

Yerel PC üzerinde sınırlı veri toplama ve çevrimdışı AI araştırması tek komut
altında birleştirilir. Gerçek emir, otomatik sanal giriş ve otomatik model
terfisi yoktur. Mevcut sanal işlem defteri değiştirilmez.

## Kurulum ve araştırma (PowerShell)

Proje kökünde, mevcut Python ortamında:

```powershell
pip install -r requirements-futures-ai.txt
$env:CYBERBOT_BINANCE_OBSERVED_ENABLED="1"
$env:CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED="1"
$env:CYBERBOT_FUTURES_LIVE_RESEARCH_ENABLED="1"
$env:CYBERBOT_FUTURES_TRAINING_ENABLED="1"
$env:CYBERBOT_FUTURES_AI_CONSENSUS_ENABLED="1"
$env:CYBERBOT_FUTURES_LIGHTGBM_ENABLED="1"
$env:CYBERBOT_FUTURES_RIVER_ENABLED="1"
$env:CYBERBOT_FUTURES_AI_MEMORY_ENABLED="1"
$env:CYBERBOT_FUTURES_STRATEGY_OPTIMIZER_ENABLED="1"
python -m cyberbot.futures_live_research --symbol BTCUSDT --collect-cycles 240
```

Veri kullanım hakkı doğrulanmadan ilgili izin etkinleştirilmemelidir.
Her oturum en fazla 240 dakika döngüsü çalıştırır; otomatik tekrar başlatma
ve Windows görevi yoktur. Ayrı oturumlar arasında kesinti olursa eğitim
verisindeki boşluklar doldurulmaz.

```powershell
python -m cyberbot.futures_live_research --symbol BTCUSDT --status
python -m cyberbot.futures_live_research --symbol BTCUSDT --evaluate
```

Ortak değerlendirme için son 1200 kesintisiz dakika (yaklaşık 20 saat)
gereklidir. Son veri en fazla iki dakika eski olmalıdır. Yeni test aralığı
önceki kalıcı kanıtla örtüşürse değerlendirme bekler. LightGBM ve River
ortak dönemde ölçülür; strateji optimizasyonu aynı gözlemleri kullandığından
bağımsız kanıt sayılmaz. Önceki hafıza aday seçimini sınırlar, yeni karantina
sonucu adayı veto edebilir. Model ağırlıkları saklanmaz. Gemini yalnız
--include-gemini ve ayrı API/paylaşım izinleri ile yeni kaydedilen raporu
inceleyebilir. Kota ve ücretler doğrulanmamıştır.

## Mevcut sanal kasa gözlemi

Ayrı açık izin ve mevcut pilot/ingress/Binance izinleriyle:

```powershell
$env:CYBERBOT_FUTURES_LIVE_PAPER_OBSERVE_ENABLED="1"
$env:CYBERBOT_FUTURES_PILOT_SYMBOL="BTCUSDT"
python -m cyberbot.futures_live_research --symbol BTCUSDT --paper-observe
```

Bu tek gözlem mevcut bekleyen manuel sanal istekleri işleyebilir, mevcut
stop/likidasyon mekanizmalarını tetikleyebilir. Yeni emir isteği oluşturmaz.
İsteğe bağlı --include-risk ayrıca mevcut dinamik risk ve teknik sinyal
araştırma izinlerini ister; yalnız araştırma önerisi verir. AI stratejisi
ile bu öneri henüz otomatik sanal emir üretmez. Sürekli sanal gözlem için
mevcut pilot döngüsü ayrıca yönetilmelidir.

Gerçek sağlayıcı bağlantısı, model çalışma zamanı ve uçtan uca test henüz
doğrulanmamıştır. Önce PC kurulum ve test denetimi, ardından veri birikimi
ve manuel sanal gözlem. Canlı ileri test veya kârlılık kanıtı yoktur.
