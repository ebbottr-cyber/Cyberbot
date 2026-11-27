# Futures adaptif strateji araştırması V1

LightGBM, River, iki modelin aynı yönde oy verdiği kural ve geçmiş 5 dakikalık
momentum adayları karşılaştırılır. Nakit (HOLD) varsayılan referanstır.

- Yerel 240–6000 ardışık gözlem; 70/30 zaman sıralı bölme ve 5 dakikalık hedef
  sızıntısına karşı eğitim örneği ayrımı.
- LightGBM sabit; River yalnız karar zamanından önce tamamlanmış hedeflerle
  güncellenir.
- Karardan bir dakika sonra örneklenmiş orta fiyat giriş referansı, beşinci
  dakikada çıkış referansı. Altı dakikalık adımlarla çakışmayan örnekler.
- Spread, model komisyonu ve fiyat kayması düşülür; iki kat maliyet senaryosu
  ayrıca değerlendirilir. Varsayılan 8 saatlik fonlama sınırını geçen
  örnekler ve 20 bps üzeri giriş/çıkış spread'i dışlanır. Bu dışlama
  gerçekleşebilir işlem garantisi değildir.
- Her tamamlanmış 10 örnekli bloktan sonra araştırma puanları güncellenir.
  En az üç tamamlanmış blok, 10 işlem ve pozitif baz/stres toplamı olmadan
  aday seçilmez. Eşit puan durumunda nakit seçilir.
- İki zayıf aktif blok karantina, üç olumlu aktif blok toparlanma sağlar.
  Kalıcı AI hafızasındaki karantina veya yetersiz model geçmişi yalnız
  bir sonraki adayı filtreler; geçmiş replay kararlarına uygulanmaz.
  Hafıza aynı veriyi içerebilir, bağımsız kanıt sayılmaz.

## Yerel kullanım

İsteğe bağlı AI bağımlılıkları kurulduktan ve gerçek gözlemler elde edildikten
sonra (PowerShell):

```powershell
$env:CYBERBOT_FUTURES_STRATEGY_OPTIMIZER_ENABLED="1"
$env:CYBERBOT_FUTURES_LIGHTGBM_ENABLED="1"
$env:CYBERBOT_FUTURES_RIVER_ENABLED="1"
$env:CYBERBOT_FUTURES_AI_MEMORY_ENABLED="1"
python -m cyberbot.futures_strategy_optimizer --symbol BTCUSDT --input futures-btc.json
```

240 kayıt yalnız girdi alt sınırıdır; bu miktar aday seçmek için yetersiz
kalabilir. Son tamamlanmamış blok değerlendirmeye alınmaz.
Getiriler sabit nominal büyüklükteki örneklerin basit toplamıdır; bileşik
kasa getirisi değildir. Pozisyon boyutu, stop, intraperiyod likidasyon ve
gerçek borsa dolumu modellenmez. Gerçek risk motoru değişmez. Bu modül
araştırma sonucunu raporlar; emir, otomatik strateji terfisi ve model ağırlığı
kaydı yoktur. Eşikler deneysel, gerçek veri ve kârlılık doğrulanmamıştır.
