# Futures canlı bağlantı ve sanal kasa güvenlik denetimi

Windows'ta önce Prepare çalıştırılmalıdır. SafetyStatus yerel SQLite
bütünlüğünü, güncel kotasyonu, fonlama bekleyişini, acil giriş frenini ve
modellenen kalan risk bütçesini salt okunur raporlar. SafetyProbe iki public
kotasyon örneği alır (en çok altı GET); zaman ilerlemesi ve mevcut 8 saatlik
fonlama takvimi kabulü kontrol edilir. Gerçek fonlama tahsilatı, borsa dolumu
ve bağlantı sürekliliği kanıtlanmaz.

```powershell
.\scripts\futures-windows.ps1 -Mode SafetyStatus
.\scripts\futures-windows.ps1 -Mode SafetyProbe -ConfirmDataRights
```

Veri kullanım haklarını önce doğrulayın. Bu modlar yeni emir oluşturmaz
ve sanal kasaya yazmaz. SafetyStatus için mevcut pilot izinleri ve kaynak
ayarları açıkça raporlanır, kendiliğinden açılmaz. Açık pozisyon veya
bekleyen manuel istek varsa yeni giriş hazırlığı durur. Giriş freni
mevcut pozisyonu kapatmaz; stop ve çıkış işlemleri için gözlem sürmelidir.

Manuel Futures sanal girişte miktar, %0,5 modellenen risk ile birlikte
günlük %3 ve zirveden %10 kayıp sınırlarına kalan alanla kısıtlanır.
Bu bir gerçekleşen azami zarar garantisi değildir; fiyat boşlukları,
spread, fonlama ve çıkış derinliği nedeniyle zarar daha büyük olabilir.
Dinamik risk önerisi ayrı araştırma modudur.

PaperObserve tek gözlemdir. Sürekli gözlem veya AI otomatik sanal giriş
başlatmaz. Aynı kasa üzerinde eşzamanlı gözlem döngüleri çalıştırmayın.
Gerçek emir yetkisi yoktur.
