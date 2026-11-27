# Futures otomatik SANAL giriş V1

Varsayılan kapalı. Tek seferlik python -m cyberbot.futures_auto_paper --symbol BTCUSDT
komutu mevcut sanal kasayı public kotasyonla gözlemler; şartlar uygunsa yalnız
yerel bekleyen sanal istek oluşturur. Sonraki açıkça otomatik moddaki public
gözlem isteği işleyebilir. Normal gözlem otomatik bekleyen girişi iptal eder.
Mevcut açık pozisyonların çıkışları normal gözlemle de işlenebilir.

CYBERBOT_FUTURES_AUTO_PAPER_ENABLED=1 ve CYBERBOT_FUTURES_AUTO_PAPER_CONFIRMED=1
ayrı izinleri, mevcut pilot, ingress, Binance veri hakları, AI köprü, ileri
tahmin, model, veri toplama, AI hafıza, teknik konsensüs ve dinamik risk
izinleri gereklidir. Gerçek emir API'si, API anahtarı, otomatik görev yoktur.
Bu sürüm otomatik sürekli döngü kurmaz.

Son 48 saatte en az 100 sonuçlanmış örtüşmeyen ileri tahmin, %95 sonuç
kapsamı, iki modelin her iki MAE referansını geçmesi, her modelde en az 10
yönlü tahmin ve yönlü örneklerde en az %50 doğruluk gerekir. Geçmiş AI
hafıza karantinası, iki model yönü, teknik ve dinamik risk ayrıca kontrol
edilir. Deneysel eşikler kârlılık kanıtı değildir.

Günde en çok üç otomatik istek (iptaller dahil); tahmin tekrar kullanılamaz.
Sanal giriş isteği en fazla 20 saniye veya adayın daha kısa kalan süresi
kadar geçerlidir. Yeni kotasyonda %0,2 orta fiyat farkı, kalan günlük ve
zirve kayıp bütçesi, öneri miktarı, marjin, derinlik ve stres maliyetleri
yeniden kontrol edilir. Öneri kaldıraç ve stop/target yüzdeleri uygulanır.
Beş dakika sonunda çıkış isteği gözlemle oluşturulur ve sonraki uygun
gözlemde modellenir; zamanında çıkış veya azami zarar garanti değildir.
Süreç kapalıysa stop ve çıkış çalışmaz. Acil fren yeni girişi engeller,
pozisyonu kendiliğinden kapatmaz. Yerel zaman/veri güvenilirliği varsayılır.

Önce yerel testler ve ileri tahmin verisi birikimi. Canlı sanal çalıştırma
doğrulanmadan otomatik giriş izinlerini açmayın.
