# Mobil PWA kabul testleri

Durum: gerçek cihazlarda henüz doğrulanmadı. Chromium CI, iOS Safari veya Android cihaz testi yerine geçmez.

## Kurulum
- iOS 16.4+ Safari: Paylaş > Ana Ekrana Ekle; uygulamayı simgesinden aç.
- Android Chrome: desteklenen kurulum menüsünden yükle.
- Güvenilir HTTPS, doğru manifest, ikonlar ve standalone görünümü kontrol et.
- Yetkisiz cihazın panel ve API erişiminin reddedildiğini doğrula.

## Bildirim
- İzin yalnızca kullanıcı etkileşimiyle istenir; reddedilirse tekrar zorlanmaz.
- Desteklenen kurulu PWA'da abonelik ve test bildirimi doğrulanır.
- Kilit ekranında hassas bakiye, emir veya kimlik bilgisi gösterilmemeli.
- İzin iptali ve abonelik kaldırma doğrulanır.

## Dayanıklılık
- Uçak modu, Wi-Fi/mobil veri geçişi, ekran kilidi ve arka plandan dönüş.
- Eski finansal veriler güncel gibi gösterilmemeli; çevrimdışı emir tekrarı olmamalı.
- Bağlantı dönüşünde güncel sunucu verileri okunmalı.
- Yeni sürüm bildirimi ve manuel yenileme kontrol edilmeli.
- 320, 375, 390 ve 430 CSS piksel genişliklerinde taşma kontrolü.

Her senaryo için cihaz, OS, tarayıcı, commit, tarih, beklenen ve gerçek sonuç kaydedilir. Başarısız veya yapılmamış test başarılı sayılmaz. Canlı emir kullanılmaz.
