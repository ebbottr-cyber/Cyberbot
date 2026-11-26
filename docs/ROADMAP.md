# Yol haritası

- Aşama 1: bağımsız Türkçe Obsidian, sentetik işlem defteri, çevrimdışı CI.
- Aşama 2: salt okunur piyasa sağlayıcı sözleşmesi; veri zaman damgası, gecikme, lisans, önbellek, kota ve hata kayıtları. BIST, NASDAQ, XETRA ve Solana ayrı doğrulanır.
- Aşama 3: ETRE'den esinlenen bağımsız cüzdan analizi, token güvenliği ve teklif tabanlı sanal dolum; GPL kodu kopyalanmaz, imzalama ve gerçek emir yoktur.
- Aşama 4: bağımsız çoklu AI ajanı; TradingAgents araştırma yaklaşımı, kaynaklı Türkçe rapor, boğa/ayı senaryoları, işlem yetkisi yok.
- Aşama 5: Vibe-Trading yaklaşımıyla bağımsız araştırma laboratuvarı; walk-forward, holdout, veri sızıntısı testleri, komisyon, slippage ve performans karşılaştırması.
- Aşama 6: PWA, kullanıcı doğrulama, güvenli uzaktan erişim, sürekli veri toplama ve uzun süreli paper doğrulaması.

Başka depolara dokunulmaz. Gerçek alım-satım hiçbir aşamada hedef değildir. Demo verisi ve gerçek gözlem verisi ayrı tutulur. Başarı veya getiri garantisi verilmez.

## AI analiz merkezi başlangıcı
TradingAgents yaklaşımından esinlenen bağımsız araştırma rolleri eklendi. İlk sürüm kural tabanlıdır; LLM sağlayıcısı, finansal tablo/haber/makro veri bağlantıları ve gerçek çoklu ajan tartışması henüz yoktur. Sentetik ve yerel tarihsel veri ayrıdır. Toplu fiyat indirme durduruldu; AI hiçbir emir yetkisine sahip değildir.

## Strateji laboratuvarı ilk sürüm
Vibe-Trading araştırma yaklaşımından esinlenilmiş bağımsız beş strateji karşılaştırması. %70 eğitim bölümü, %30 ileri dönem; pencere yalnız eğitimde seçilir; kapanış sinyali sonraki açılışta uygulanır. Ücret/kayma, azami düşüş, kapanan işlem ve kazanma oranı. Sentetik demo ve yerel arşiv; hiçbir fiyat indirme veya emir yok. Tam walk-forward, Monte Carlo, çoklu varlık portföyü ve otomatik terfi henüz yoktur.

## Öğrenme merkezi ilk sürüm
60 gözlemli kayan eğitim bağlamı (20 ısınma + 40 ölçüm), ardından 20 gözlemli örtüşmeyen ileri test. Beş sabit pencere adayı yalnız eğitimde karşılaştırılır. Deneyler SQLite üzerinde sürüm, veri modu ve veri özetiyle tekilleştirilir. Sentetik ve doğrulanmamış tarihsel sonuçlar ayrı tutulur. Parametre taraması gerçek ML eğitimi değildir; arka plan zamanlayıcısı, LLM ve otomatik terfi yoktur. Ana işlem motoru değiştirilmez. Toplu fiyat indirme kapalıdır.

## Model merkezi ilk sürüm
Yerel Ollama için sabit loopback bağlantısı, isteğe bağlı ve varsayılan kapalı; yalnız sentetik rapor özeti, araç/emir yok. Tahmin araştırmasında sıfır getiri ve kayan ortalama referanslarına karşı 60 gözlemli kayan AR(1) modeli, ileri test MAE/yön doğruluğu. Chronos, diğer derin modeller ve gerçek LLM bağlantı testi henüz yok; otomatik terfi yok.

## Chronos 2 araştırma adaptörü
İsteğe bağlı yerel CPU modeli, yalnız operatörün sağladığı safetensors dizini; otomatik model indirme yok. Ortak 60 getiri bağlamı ve 8–32 ileri testte AR(1), kayan ortalama, sıfır getiri ve Chronos 2 karşılaştırılır; çapraz seri öğrenmesi kapalı. P10/P50/P90, aralık kapsaması, MAE ve yön doğruluğu. CI sahte modelle sözleşme testleri yapar; gerçek ağırlıklarla çıkarım doğrulanmamıştır. Modelin gerçek veya sanal işlem yetkisi yoktur.

## PWA ilk sürüm
Manifest, özgün PNG ikonları, iOS ana ekran bağlantısı, güvenli bağlamda service worker ve bağlantı kesilince yalnız statik uyarı. İşlem verileri, API yanıtları veya istekler çevrimdışı saklanmaz; arka plan senkronizasyonu yok. Loopback erişim sınırı korunur. Fiziksel iPhone testi ve kimlik doğrulamalı HTTPS uzaktan erişim henüz yoktur.

## Obsidian referans tasarımı
Mobil ana panel kullanıcı görselindeki 2 sütunlu dört özet kartı, turkuaz performans grafiği ve modül kutuları ile yeniden düzenlendi. Grafik yalnız yeni kayıt edilen sanal portföy gözlemlerini gösterir (son 200); 7 günlük geçmiş uydurulmaz. Mevcut veritabanı korunur ve ilk yeni kayıtla başlar. Günlük K/Z UTC gün başlangıcı referanslı, maksimum düşüş yeni kayıtların gözlenen maksimumudur. Masaüstü dört sütun; PWA ve erişim sınırları korunur. Fiziksel cihaz görsel testi yapılmadı.

## Özel uzaktan erişim
Varsayılan loopback korunur; isteğe bağlı Tailscale Serve modu, tam HTTPS host/port ve kullanıcı kimliği doğrulaması, salt okunur varsayılan, yazma için açık onay ve Origin kontrolü. Fiziksel PC/iPhone kurulumu henüz yoktur. Funnel ve genel internet erişimi kullanılmaz.

## Bütünleşik doğrulama
Windows/Linux ve Python 3.11/3.12 CI matrisinde panel rotaları, PWA, izole sentetik işlem defteri, salt okunur arşiv, AI/strateji/model deneyleri, deney kalıcılığı ve kapalı ağ sağlayıcıları birlikte sınanır. Fiziksel cihaz, gerçek model ağırlıkları ve lisanslı piyasa verisi doğrulanmış değildir. Eski toplu indirme çalışmasını durdurmak için aynı concurrency grubuna iptal işi eklenmiştir.

## Yerel operasyonlar
Windows kurulum ve ön planda başlatma betikleri, uygulama sağlık paneli, SQLite çevrimiçi yedek API'si ile yerel tutarlı dosya kopyaları, SHA-256 manifesti ve bütünlük kontrolü. EBBot verisi dahil edilmez. İstek erişim logu kapalı, sunucu logu yerel var/logs. Otomatik zamanlama, geri yükleme ve gerçek PC kurulumu henüz yoktur.

## Yerel araştırma zamanlayıcısı
Ayrı, açıkça başlatılan 15 dakika varsayılan döngü; sağlık kontrolü, sentetik veya açıkça seçilmiş salt okunur arşiv araştırması, tekilleştirilen deney ve son 1000 döngü kaydı. İsteğe bağlı günlük yerel yedek. SQLite ile eşzamanlı döngü engeli. Windows oturum açılış görevi yalnız operatörün -Register komutuyla oluşturulur; fiziksel cihazda denenmedi. Gerçek işlem, paper emir, model indirme ve piyasa ağı yok. Son döngü kaydı canlı süreç kanıtı değildir.

## Uzun sentetik risk simülasyonu
Gerçek paper motoru ayrı geçici SQLite ve bağımsız enstrüman evreni ile 240 gözlemli dört senaryoda sınanır. Sabit tek varsayımsal UTC oturumu ile günlük kayıp koruması zorlanır; gerçek 240 gün değildir. Nakit, pozisyon, tekrar işlem ve muhasebe kontrolleri; gözlenen düşüş ve engellenen girişler. Fiyat boşluğu kaybı stop limitini aşabilir. CI genişletilmiş test çalıştırır. Gerçek kârlılık, likidite ve günlük reset davranışı doğrulanmaz.
