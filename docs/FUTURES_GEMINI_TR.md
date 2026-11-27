# Futures Gemini V1

Gemini, yerel LightGBM ve River raporlarının sayısal ölçümlerini denetler.
İki modelin değerlendirme dönemleri henüz aynı değildir; kazanan seçilmez.
Gemini yalnız izinli araştırma kontrol kodları döndürür. Türkçe metin yerel
şablonlardan oluşturulur. Emir, model terfisi, araç çağrısı, ham veri ve
kasa bilgisi paylaşımı yoktur.

## İsteğe bağlı kullanım

Mevcut httpx bağımlılığı yeterlidir. Google AI Studio'da erişilebilen,
JSON şemalı çıktı destekleyen model adı ve API anahtarı operatörce belirlenir.
Model veya ücretsiz kota varsayılmaz. Anahtarı GitHub'a, rapora veya komut
geçmişine yazmayın. Güvenli yerel ortam değişkeni olarak sağlayın.

- CYBERBOT_FUTURES_GEMINI_ENABLED=1
- CYBERBOT_GEMINI_METRICS_SHARING_CONFIRMED=1
- CYBERBOT_GEMINI_MODEL (açık model adı)
- CYBERBOT_GEMINI_API_KEY (gizli API anahtarı)

Her manuel çağrıda en fazla bir HTTPS POST ve 512 çıktı tokeni istenir.
Otomatik tekrar, zamanlayıcı veya kalıcı kota sayacı yoktur. Sağlayıcı
ücretleri ve veri işleme şartları ayrıca kontrol edilmelidir.

```sh
python -m cyberbot.futures_gemini --lightgbm-report lightgbm.json --river-report river.json
```

Raporlar mevcut iki yerel araştırma modülünün JSON çıktılarıdır; uydurma
raporlarla canlı performans iddiasında bulunulmaz. Model seçimi ve karar
yetkisi kapalıdır. Gerçek API bağlantısı henüz doğrulanmadı.

API: https://ai.google.dev/gemini-api/docs/structured-output
