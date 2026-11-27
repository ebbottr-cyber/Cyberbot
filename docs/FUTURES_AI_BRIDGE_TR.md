# Futures AI sinyal köprüsü V1

Yalnız gölge araştırma kararı. Son 1200 kesintisiz dakika üzerinden LightGBM
sabit eğitim bölümü ve River tamamlanmış geçmiş hedeflerle yeniden oluşturulur.
Model ağırlığı saklanmaz. En son özellik en fazla 90 saniye eski olmalıdır.
İki modelin ±%0,4 deneysel eşikte aynı yönü göstermesi gerekir.

Son iki örtüşmeyen, 48 saat içinde tamamlanmış AI hafıza dönemi her iki basit
referansı geçmeli, drift veya karantina bulunmamalıdır. Bunlar canlı bağımsız
kanıt değildir. Teknik konsensüs ve dinamik risk önerisinin yönü aynı olmalı,
risk kotasyonu en fazla 30 saniye eski ve özellik orta fiyatından en fazla
%0,2 farklı olmalıdır. Acil giriş freni son aşamada tekrar okunur.
Bu eşikler deneysel olup işlem yetkisi vermez.

Mevcut Futures, Binance, veri toplama, model, AI hafıza, teknik konsensüs ve
dinamik risk izinleri ayrıca etkin olmalıdır. Ek izin:
CYBERBOT_FUTURES_AI_BRIDGE_ENABLED=1.

```powershell
python -m cyberbot.futures_ai_bridge --symbol BTCUSDT
```

Sonuç yalnız HOLD veya shadow_candidate araştırma etiketidir.
actual_action her zaman HOLD; gerçek ve sanal emir yok, veritabanı yazımı yok,
Gemini çağrısı yok. Adayın zaman sınırı raporlanır. Canlı ileri tahmin günlüğü
ve atomik risk/işlem bağlantısı henüz yoktur. Gerçek piyasa testi gerekli.
