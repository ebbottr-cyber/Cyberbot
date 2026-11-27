# Futures Strategy Promotion & Demotion V1

Salt okunur Windows raporu: .\scripts\futures-windows.ps1 -Mode StrategyGate

Son sekiz tamamlanmış sabit UTC 6 saatlik pencere (48 saat) yeniden
hesaplanır. LightGBM, River, ikisinin yön uyumu ve momentum karşılaştırılır.
Sadece önceden kaydedilmiş, pencere sonundan önce sonuçlanmış, kaynak
fiyatıyla eşleşen ve örtüşmeyen tahminler değerlendirilir. Gözlenmeyen
slotlar kapsamdan düşer, sahte tahmin oluşturulmaz.

Her pencerede en az 60 sonuç, %90 kapsam ve strateji başına 10 modellenmiş
işlem gerekir. Hem normal hem çift maliyet senaryosu pozitifse iyi;
yeterli veri olup koşul sağlanmazsa zayıf. İki ardışık zayıf pencere
karantina; üç ardışık iyi pencere araştırma uygunluğu. Yetersiz veri
uygunluğu kaldırır, karantinayı kendi başına kaldırmaz. Pencereler
kayan geçmişten tekrar hesaplanır; 48 saat dışında kalıcı karantina
geçmişi yoktur, yeniden uygunluk için üç iyi pencere şarttır.

Yalnız agreement mevcut otomatik SANAL giriş yoluna ek veto verebilir.
Diğer kurallar araştırmadır. Mevcut ileri kanıt, AI hafıza, teknik risk,
izinler, acil fren ve diğer sınırlar aynen geçerlidir. Gate hem giriş
kararından önce hem mevcut kasa işlemindeki kanıt tekrarında okunur.
Yüksek çıkış spread'i artık işlem örneğini silmez; maliyete yansır.
Pozitif olmayan modellenmiş fiyat raporu reddeder. Fonlama sınırını
geçen örnekler ve giriş spread'i >20 bps örnekleri proxy dışıdır.

Proxy sonraki dakika giriş ve hedef dakikası çıkışını kullanır;
gerçek emir veya dinamik stop/likidasyon modeli değildir. Eşikler
deneyseldir. Gerçek işlem terfisi yoktur. CPU/SQLite gecikmeleri
canlı karar süresini aşabilir; bu durumda mevcut tazelik kapıları
girişi reddeder.
