# Futures son entegrasyon denetimi ve PC kabul planı

GitHub CI offline testlerdir. PC'de kurulum, Binance erişimi, sürekli
kotasyon, kaynak zamanları, disk ve CPU süreleri henüz doğrulanmadı.
Gerçek emir veya gerçek hesap erişimi yoktur.

1. Temiz checkout; eski süreçleri aynı kasa üzerinde çalıştırmayın.
   Git pull/reset otomatik yapılmaz. Prepare tam HEAD için test işareti
   üretir; kaynak klasörlerindeki takip edilmeyen dosyalar incelenmeden
   başlatma yapılmaz.
2. Prepare, SafetyProbe (veri hakları gerçekten doğrulanırsa), Health.
3. İlk 15 dakikalık araştırma watchdog denemesi: emir ve sanal kasa
   gözlemi kapalı. Dakika kayıtlarını ve missed/rejected olaylarını
   inceleyin. Başarısızsa süre uzatmayın.
4. Sağlıklı sonuçtan sonra en fazla 4320 dakikalık (72 saat) araştırma
   oturumu. İlk 1200 kesintisiz dakika 20 saat; üç iyi 6 saatlik pencere
   en az 18 saat daha, pencere hizası ve ek kanıt şartları süreyi
   uzatabilir. 24 saat önceki sınır yetersizdi. Collect 1440 ile sınırlı.
   PC uyku/kapanma ve veri boşlukları eğitimi geciktirebilir.
5. Performans, StrategyGate, Health raporları. Otomatik giriş için
   ayrı onay, mevcut pilot/ingress izinleri ve tüm kanıt/risk kapıları
   gerekir. Pending AI girişinde ileri kanıt ve strateji uygunluğu
   tekrar okunur, hata halinde normal gözlem girişi iptal eder.
   Cross-DB atomiklik yok; PC canlı testi ve güvenlik kabulü gereklidir.

```powershell
.\scripts\futures-windows.ps1 -Mode Prepare
.\scripts\futures-windows.ps1 -Mode SafetyProbe -ConfirmDataRights
.\scripts\futures-windows.ps1 -Mode Watchdog -Cycles 15 -ConfirmDataRights
.\scripts\futures-windows.ps1 -Mode Health
```

İlk denemede ConfirmPaperObservation ve ConfirmAutoPaper kullanılmaz.
İleri tahmin ve strateji kapıları deneysel, kârlılık garantisi değildir.
Gözlem kesintisi stop/çıkışı engelleyebilir. 72 saatlik mod bir
zamanlayıcı veya 7/24 kesintisiz hizmet değildir. PWA, DexTerm ve Borsa
stratejileri değiştirilmedi.
