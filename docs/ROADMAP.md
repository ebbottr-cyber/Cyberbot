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

## Piyasa sermayesi ve kur
BIST 45.000 TRY; NASDAQ, XETRA, Solana ayrı 1.000 USD. Ana panel yeni piyasa defterlerini kullanır, eski ortak defter korunur. XETRA demo USD bazlıdır, gerçek EUR işlem adaptörü değildir. USD toplamı yalnız en fazla 5 dakika yaşındaki yerel USD/TRY girdisiyle hesaplanır, kaynak doğrulanmış sayılmaz. İşlem K/Z güncel kurla çevrilir; tarihsel kur getirisi ve birleşik tarihsel düşüş henüz hesaplanmaz. Stres kıyaslaması 45 varsayımsal sabit kur kullanır ve varsa güncel kur değerlemesini ayrıca verir. Fiyat indirme kapalıdır.

## Strateji dayanıklılığı
60 gözlem kayan eğitim bağlamı ve 20 gözlem örtüşmeyen ileri test; pencere yalnız eğitimde seçilir. Aynı pencereyle 2x ücret/kayma testi. İleri test net getirilerinin 5 gözlem bloklu, 1000 yol, 60 gözlem ufuklu sabit tohumlu bootstrap analizi. P05/50/95 getiri ve yerel sermaye, P95 düşüş, zarar yolu oranı. Deneysel 0–100 puan: tutarlılık 25, düşüş 25, maliyet 20, bootstrap risk 20, örneklem 10. En az 6 bölüm ve 20 işlem yoksa puan yok; referanslar sıralanmaz. Gerçek başarı olasılığı veya emir yetkisi değildir.

## Strateji turnuvası
Piyasa ve sembol bazında, son 60 gözlem keşiften tamamen ayrılır. Dayanıklılık adayında en az 65 puan ve varsa ikinci uygun adaya 5 puan fark; yalnız seçilen aday, keşifte sabitlenmiş pencereyle final testinde değerlendirilir. Finalde en az 5 kapanmış işlem, pozitif net ve iki kat maliyet getirisi, her iki düşüş en fazla %10. Başarısızsa şampiyon yok; finalist değişmez. Sentetik ve tarihsel kayıtlar ayrı, aynı veri SHA-256 ile tekilleştirilir; SQLite öğrenme dosyasında ayrı turnuva tablosu. Tek sembol şampiyonu piyasa geneli kanıtı değildir; otomatik terfi yok.

## Piyasa rejimi araştırması
Tek sembolde 20 geçmiş kapanış getirisi, ±%3 trend ve gözlem başına %2,5 standart sapma eşikleri; volatilite öncelikli. Etiket sonraki açılıştan önce bilinen kapanışlarla oluşturulur. Walk-forward strateji özsermaye değişimleri rejimlere betimsel olarak ayrılır, 40 gözlem altı yetersiz. Bitişik olmayan rejimlerden portföy eğrisi üretilmez. Sentetik veya yerel arşiv; otomatik strateji değiştirme/terfi yok. Eşikler deneysel ve kalibre edilmemiştir.

## Adaptif gölge araştırması
Her 20 gözlemli blok başlamadan rejim ve aday yalnız önceki kapanışlar/tamamlanmış bloklardan seçilir; geçmiş eğitimle pencere sabitlenir. Rejim başına 40 gözlem, geçmiş toplam 20 kapanış, ortalama net %0,02 ve çift maliyette pozitif, son 6 blok pozitif ve düşüş ≤%10. Uygun aday yoksa nakit. Tamamlanmış blok sonrası kanıt güncellenir; ana portföy değiştirilmez. Tarihsel gölge replay, canlı gölge veya otomatik strateji terfisi değildir. Karşılaştırmalar nakit, al-tut, sabit strateji ve 2x maliyet. Eşikler deneysel.

## Strateji hafızası ve karantina
Adaptif replay içinde yalnız tamamlanmış bloklardan karantina durumu güncellenir; iki ardışık aktif zararlı blok veya baz/2x maliyet düşüşü %10 üzeri ise karantina. Üç ardışık aktif, net ve 2x maliyette pozitif, düşüş sınırında yeni blok ile yeniden izleme; emir yetkisi yok. Adaptif API kanıtları öğrenme DB ayrı tablolarında piyasa/sembol/veri modu ve protokol bazında saklar. Yalnız önceki son bitişten sonra başlayan blok kabul edilir; tekrar/örtüşen dönem sayılmaz. Kalıcı karantina sonraki araştırma önerisini de filtreler, geçmiş replay'i geriye dönük değiştirmez. Canlı kanıt ve otomatik zamanlayıcı bağlantısı yok.

## Ortak araştırma döngüsü
Windows worker --full-research ile 15 dakika aralığında dört sentetik piyasa, veya CLI'da açıkça seçilmiş tek yerel arşiv sembolü. Teknik/kural tabanlı analiz, walk-forward, Monte Carlo/dayanıklılık, turnuva, rejim, adaptif/karantina ve temel tahmin kıyaslaması aynı veri girdisinde. Sürüm/piyasa/sembol/mod/fiyat/tarih parmak izi ile tamamlanmış deney tekrar hesaplanmaz; hatalı aşama yeniden denenebilir, kayıtlar tekilleştirilir. Öğrenme DB'de ayrı pipeline tablosu, sağlık panelinde özet. Yerel LLM/Chronos, canlı sağlayıcı, toplu fiyat indirme, gerçek ve paper emir çağrısı yok. Sentetik veri değişmedikçe yeni öğrenme oluşmaz. Fiziksel Windows zamanlayıcı kurulumu yapılmadı.

## Bağımsız Futures merkezi
ETRE v3 (ismailkaraabc/etre-trading-office, 532968b7) Hyperliquid perps ve Solana spot kopya araştırmasıdır; GPL-3.0 kodu taşınmadı. Cyberbot bağımsız USDT-M tarzı sentetik Futures hesabı: 1000 USDT, BTC/ETH örnek seri, LONG/SHORT, sabit 2x, en çok bir pozisyon, varsayımsal ücret/kayma/fonlama/bakım teminatı. Gerçek Binance mark fiyatı, fonlama, sembol evreni ve likidasyon doğrulanmadı; hiçbir ağ/emir/anahtar yok. Genel USD değerleme için ayrı USDT/USD girdisi gerekli. Futures araştırma ve otomatik pipeline henüz ayrı entegrasyon gerektirir.

## Futures araştırma bağlantısı
Ayrı LONG/SHORT tek gözlemli sentetik araştırma simülatörü, 1000 USDT ve 2x; maliyet/fonlama ve basit izole likidasyon modeli. Walk-forward keşif, Monte Carlo, son 60 gözlem final turnuvası, rejim/kural analizi, temel tahmin kıyası; iki Futures sembolü otomatik pipeline ve öğrenme DB kaydına bağlı. Opt-in yerel Chronos 2 aynı sentetik seriyle test edilebilir. Gerçek borsa/Chronos doğrulaması, adaptif Futures karantinası ve canlı veri yok.

## Futures adaptif hafıza
20 gözlemli nedensel replay, mevcut adaptif aday eşikleri ve ayrıca baz/2x maliyet likidasyonu karantinası. Strateji hafızası FUTURES ve sembol kapsamıyla öğrenme DB'de; aynı blok tekrar kanıt olmaz. Üç aktif olumlu, likidasyonsuz blok yeniden izleme. Sonuçlar Futures paneli ve ortak pipeline özeti. Sentetik veri dışında yeni kanıt yok; turnuvayla örtüşen veri bağımsız doğrulama değildir.

## Bot Gelişimi Merkezi
Obsidian salt okunur SQLite araştırma özeti, beş piyasa, sentetik/tarihsel filtre, son 10 sembol kaydı/piyasa ve son 30 deney; puan, gölge, rejim, turnuva, kalıcı karantina ve temel model ölçümleri. Güncel hafıza karantinası eski aday önerisini bloke eder. Kayıt sayısı bağımsız kanıt değildir; model yapılandırması gerçek çıkarım değildir. İşlem yetkisi yok.

## Kur entegrasyonu
İzinli ve açıkça etkinleştirilen Twelve Data exchange_rate adaptörü, yalnız USD/TRY ve USDT/USD. Her kaynak zamanı ayrı, 300 saniye yaş sınırı, 240 saniye sorgu aralığı, yerel kalıcı 720 kredi/gün; iki geçerli yanıtla atomik JSON. Ağ başarısızlığında önceki zaman damgası değişmez. API anahtarı ve gösterim hakkı operatöre ait; ücretsiz plan non-display kısıtı nedeniyle izin varsayılmaz. Varsayılan kapalı, hiçbir fiyat arşivi indirme yok. Mock testleri, gerçek sağlayıcı erişimi henüz doğrulanmadı.

## Bilgi ve haber merkezi
İlk sürüm: bağımsız Vault ZIP, Canvas/Bases, ajan beceri dosyası, ortak panel CSS ve manuel haber/takvim kayıtları. İleri araçlar ve RSS pilotu docs/KNOWLEDGE_NEWS_TR.md içinde; izin doğrulaması olmadan ağ erişimi yok.

## Genel denetim düzeltmeleri
Yapılandırılmış DB yolları ortak kontrol, symlink/hardlink çakışmaları ve EBBot arşivi koruması; önbellekli API girişinde tekrar kontrol. Futures sentetik stres (4 senaryo, beşinci hesap), bağımsız günlük/düşüş risk kontrolü, çift maliyet likidasyonu aday dışı, stres ekranı JS yeniden yazıldı. Gerçek cihaz/işlem doğrulaması değil. Yerel süreçlerin dosyaları eşzamanlı değiştirmesi güven sınırı dışıdır.

## Futures grafiği ve kurtarma pilotu
Futures kasa gözlemleri aynı işlem transaction'ında kaydedilir; eski defter ilk açıldığında yalnız mevcut gözlem eklenir. Ana panel ve Futures ekranında son 200 kayıt. Yeni kurtarma CLI yalnız ayrı klasöre doğrulanmış kopya çıkarır; aktif veritabanlarını değiştirmez. Manifest dosya adları, boyut, SHA-256 ve SQLite bütünlüğü kontrol edilir. Worker yedek kapsamı dışında, farklı DB'ler tek atomik anlık görüntü değildir. Fiziksel cihaz ve canlı borsa doğrulanmadı.

## Panel denetimi
13 HTML sayfasının inline JavaScript sözdizimi ve sabit DOM kimlikleri kaynak incelemesinde kontrol edildi. Ortak mobil CSS, çevrimdışı portföy/Futures temizliği, kapalı model/Solana düğmeleri ve bilgi hafızası yarış kontrolü. CI Chromium smoke testi: 1280,390,320 px ekranlarda 13 sayfa, API hatası, yatay taşma, kapalı düğmeler ve ana panel çevrimdışı geçişi. Tarayıcı yalnız yerel izole sunucuya erişir. Fiziksel iPhone/Safari doğrulaması değildir.
