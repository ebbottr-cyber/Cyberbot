# Futures LightGBM V1 — çevrimdışı araştırma

Bu modül yalnız BTCUSDT veya ETHUSDT için tek seferlik yerel araştırmadır.
Standart Cyberbot kurulumu değişmez. Model kaydetmez, ağ isteği göndermez,
pilot defterine veya gerçek emir sistemine yazmaz.

## İsteğe bağlı kurulum

Python 3.11/3.12 ortamında:

```sh
pip install -r requirements-futures-ai.txt
```

PowerShell örneği:

```powershell
$env:CYBERBOT_FUTURES_LIGHTGBM_ENABLED="1"
python -m cyberbot.futures_lightgbm --symbol BTCUSDT --input .\var\futures-observations.json
```

## Girdi sözleşmesi

Dosya, tek sembol için 240–6000 ardışık UTC dakika kaydından oluşan JSON listesidir.
Her kayıt şu alanları içermelidir. Aşağıdaki satır yalnız biçim örneğidir, piyasa verisi değildir.

```json
{
  "at": "2026-01-01T12:00:00+00:00",
  "symbol": "BTCUSDT",
  "source": "binance-usdm-public",
  "mid": "100",
  "spread_bps": "1",
  "funding_rate": "0.0001",
  "mark_index_basis_pct": "0.01",
  "open_interest": "500",
  "book_imbalance": "0.2",
  "taker_imbalance": "0.1",
  "atr_1m_pct": "0.2",
  "atr_5m_pct": "0.5"
}
```

Tüm özellikler kayıt anında gerçekten elde edilebilir olmalıdır. Özellikle
tamamlanmamış 5 dakikalık taker verisi veya sonradan düzeltilmiş gelecek bilgi
kullanılmamalıdır. Yalnız aynı kaynaktan ve aynı sözleşmeden gelen veriler
birleştirilmelidir. Kaynak etiketi ve zaman damgası tek başına veri kökeni kanıtı
değildir. V1 henüz otomatik veri toplamaz veya dışa aktarmaz. Eksik dakikalar
doldurulmaz; uygun dosya yoksa eğitim yapılmamalıdır.

## Değerlendirme

- 11 özellik: 1/5/20 dakika getiri, spread, funding, basis, 5 dakika açık
  pozisyon değişimi, emir defteri ve taker dengesi, 1/5 dakika ATR.
- Hedef: sonraki 5 dakikanın orta fiyat getirisi. İşlem getirisi değildir.
- Sabit zaman sıralı yaklaşık %70 eğitim / %30 test; eğitim hedefi ilk test
  özellik zamanına ulaşan 5 örnek ayrılır. Karıştırma veya test ile ayar yok.
- CPU, tek iş parçacığı, 64 ağaç, maksimum derinlik 4.
- MAE ve deneysel ±%0,4 eşikli UP/DOWN/HOLD doğruluğu; sıfır getiri ve
  önceki 5 dakika momentum referansları. Eşik, gerçek maliyet garantisi değildir.
- Beş dakikalık sonuçlar örtüşür; bağımsız örnek veya güven aralığı sayılmaz.
- Model seçimi/terfisi, canlı çıkarım, otomatik sanal işlem ve kârlılık doğrulaması yok.

Test:
```sh
python -m unittest discover -s tests -p "test_futures_lightgbm.py" -v
```
Gerçek LightGBM deneme testi yalnız isteğe bağlı bağımlılık kuruluysa çalışır.
