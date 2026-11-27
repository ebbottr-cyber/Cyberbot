# Futures ileri tahmin hafızası V1

Ayrı yerel SQLite dosyasına (CYBERBOT_FUTURES_FORWARD_DB) beş dakikalık
örtüşmeyen tahmin hedefleri kaydedilir. Son 1200 kesintisiz gözlem gerekir.
Tahmin en son dakika kesiminden en fazla 30 saniye sonra kaydedilebilir.
LightGBM ve River yanında sıfır ve geçmiş 5dk momentum referansı saklanır.
HOLD dahil tüm yönler değerlendirilir; risk filtresiyle örnek seçilmez.

```powershell
$env:CYBERBOT_FUTURES_FORWARD_MEMORY_ENABLED="1"
python -m cyberbot.futures_forward_memory --symbol BTCUSDT --tick
python -m cyberbot.futures_forward_memory --symbol BTCUSDT
```

Mevcut veri toplama ve iki AI model izni de gereklidir. Tick yalnız bir kez
çalışır; düzenli çağrı otomatik zamanlayıcı gerektirmez ancak bu sürüm onu
kurmaz. Yeni gözlemler ayrı collector tarafından kaydedilmelidir. Tick,
sonucu gelmiş tahminleri çözer ve zamanı uygunsa yeni tahmin kaydeder.
Sonuç için altı kesin dakika gözlemi gerekir. Hedefin kaydı beklenir,
iki dakikalık tolerans sonrasında eksik sonuç kalıcı missing olarak işaretlenir.
Geçmişe dönük tahmin ve eksik sonuç doldurma yoktur. Son 2016 tahmin üzerinden
MAE, yön doğruluğu, eksik sonuç ve kapsam raporlanır. Yerel saat ve veri
tabanı güvenilirliği varsayılır; harici zaman kanıtı yoktur.
Gerçekleşen emir, getiri, likidasyon veya otomatik model terfisi yoktur.
