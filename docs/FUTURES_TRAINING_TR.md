# Futures eğitim verisi toplama V1

Yalnız BTCUSDT veya ETHUSDT, yerel PC üzerinde ön planda, salt okunur public
Binance istekleri. İşlem API'si, API anahtarı, otomatik görev kurulumu ve geçmiş
boşluk doldurma yoktur. Yeni SQLite dosyası diğer piyasa/AI hafıza kasalarından
ayrıdır. Varsayılan yol: var/paper-futures-training.sqlite3 (CYBERBOT_DB adına
bağlı); CYBERBOT_FUTURES_TRAINING_DB ile ayrı yol belirlenebilir.

## PowerShell (proje klasöründe)

```powershell
$env:CYBERBOT_BINANCE_OBSERVED_ENABLED="1"
$env:CYBERBOT_BINANCE_DATA_RIGHTS_CONFIRMED="1"
$env:CYBERBOT_FUTURES_TRAINING_ENABLED="1"
python -m cyberbot.futures_training --symbol BTCUSDT --cycles 240
```

Veri kullanım hakkı gerçekten doğrulandıysa ilgili değişkeni etkinleştirin.
Bir oturum en fazla 240 döngü çalıştırır. PC açık ve internet erişilebilir
olmalıdır. Sonraki oturumu bitişten sonra başlatın; otomatik zamanlanmış görev
henüz yoktur. Ayrı terminalde durum sorgulanabilir:

```powershell
python -m cyberbot.futures_training --symbol BTCUSDT --status
```

## Yerel eğitim dosyası

```powershell
python -m cyberbot.futures_training --symbol BTCUSDT --export | Set-Content -Encoding utf8 futures-btc.json
```

Windows PowerShell 5.1 UTF-8 BOM ekleyebilir; Python JSON okuyucu UTF-8 BOM'u
kabul eder. Export başarısızsa oluşan boş dosyayı eğitimde kullanmayın. Export
yalnız son kesintisiz 240–6000 dakika kaydını döndürür; hata stderr'e yazılır.
Birleşik AI hafızasının en az 30 çakışmayan test hedefi şartı için 240'tan daha
fazla ardışık gözlem gerekir.

## Özellik zamanları ve sınırlar

- UTC dakikanın :40–:44 aralığında başlatılır, bir sonraki dakika öncesinde
  tamamlanır. Dakika etiketi verinin kullanılabilirlik kesimidir; kesin o anki
  borsa işlem fiyatı değildir. Kaynak zamanları ve yerel alım zamanı saklanır.
- Beş GET: 1m ve 5m kapanmış 60 mum, bookTicker, premiumIndex, openInterest.
  Fiyat kaynak zamanları en fazla üç saniye farklı, son yirmi saniye içinde.
- Taker alış dengesi son kapanmış 5m mumun base volume ve taker buy base volume
  alanlarından hesaplanır. Emir defteri dengesi yalnız en iyi seviyedeki miktar
  dengesidir, tam defter değildir. Bu özellik tanımı başka veri yöntemleriyle
  karıştırılmamalıdır.
- Gecikmiş, eksik ve tekrarlanan veriler reddedilir; otomatik tekrar yok.
- Sembol başına en fazla 10080 kayıt saklanır. Export son kesintisiz dizidir;
  boşlukları doldurmaz. Kaynak bağımsız doğrulaması ve gerçek bağlantı testi
  henüz yapılmadı. Eğitim ve model terfisi otomatik başlamaz.
