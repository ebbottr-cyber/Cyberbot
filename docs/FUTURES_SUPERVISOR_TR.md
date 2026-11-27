# Futures Autonomous Supervisor V1

Tek ön plan süreci; en fazla 1440 UTC dakika. Windows'ta Prepare sonrası:

```powershell
.\scripts\futures-windows.ps1 -Mode Supervise -Cycles 1440 -ConfirmDataRights
```

Varsayılan yalnız veri ve AI araştırmasıdır. İleri tahmin günlüğü otomatik
çalışır. İlk 1200 kesintisiz kayıt ve gerekli ileri sonuçlar birikmeden
otomatik emir yoktur. Her 30. oturum dakikasında (uygun veri ve düz kasa
varsa) çevrimdışı araştırma denenir. Gemini çağrılmaz.

Sanal gözlem eklemek için mevcut pilot/ingress izinlerini ayrı yapılandırın
ve -ConfirmPaperObservation ekleyin. Otomatik giriş için ayrıca
-ConfirmAutoPaper ve mevcut teknik konsensüs/dinamik risk izinleri gerekir.
Sadece aynı oturumdaki yeni kaydedilmiş tahmin ve ardışık taze sanal
gözlemler ile giriş değerlendirilir. Yeni emir varsayılan kapalıdır.

Dakika kesiminde veri kaydı, :04 gözlem, tahmin, :19 otomatik karar,
:30 ve mümkünse :55 gözlem, :40 eğitim verisi toplama. Geç kalan slot
atlanır; geçmişe dönük tamamlama yoktur. Ağ/CPU gecikmeleri sebebiyle
gözlem sıklığı garanti değildir. Yeni otomatik girişte 30 saniye üstü
kotasyon boşluğu iptal sebebidir. Tek supervisor için OS kilidi bulunur;
diğer araçların aynı kasaya yazmasını engellemez. Başka collector/pilot
döngüsü paralel çalıştırılmamalıdır.

Ctrl+C oturumu durdurur; açık pozisyonu kapatmaz. Oturum bitmeden açık
sanal pozisyonu kontrol edin. Sürekli gözlem durduğunda stop da durur.
Kalıcı Windows görevi, otomatik yeniden başlatma ve gerçek emir yoktur.
Canlı çalışma ve süreklilik PC üzerinde doğrulanmalıdır.
