# Futures Performance Analytics V1

Windows'ta Prepare sonrası:
```powershell
.\scripts\futures-windows.ps1 -Mode Performance -Symbol BTCUSDT
```

Rapor salt okunurdur. Gözlenen FUTURES sanal kasa olaylarını baştan
canlandırır ve bakiye, pozisyon, işlem/fonlama/likidasyon sayaçları ile
mutabakat yapar. Eksik veya uyumsuz geçmişte ölçüm reddedilir; 250000
olay sınırında kesilmiş geçmişten sahte sonuç üretilmez.

Kapanmış işlem net PnL, kazanan/kaybeden/başabaş, başarı oranı, profit
factor, ortalama sonuç, giriş ve tahsil edilen modellenmiş çıkış komisyonu,
net fonlama, likidasyon sayısı ve son 20 kapanış raporlanır. Manuel/AI ve
LONG/SHORT ayrı gruplardır; tekil model/stratejiye kâr atfedilmez.
Kayıp yoksa profit factor, işlem yoksa başarı oranı null. Net PnL komisyon
ve fonlama etkisini zaten içerir; ikinci kez düşülmez. Likidasyonda model
izole marjı kaybeder, ayrıca çıkış komisyonu tahsil etmez.

Gerçekleşmiş bakiye eğrisi düşüşü ve örneklenmiş sanal özsermaye düşüşü
farklı ölçümlerdir. Yetersiz çıkış derinliği olan gözlemler atlanır ve
sayıları raporlanır. Kesintisiz drawdown değildir; kayıp gözlemler daha
büyük düşüşleri gizleyebilir. Açık pozisyonun güncel değeri eski kotasyon,
bekleyen fonlama veya derinlik eksikliğinde null. Borsada gerçekleşmiş
işlem veya kârlılık kanıtı değildir. Sağlık raporu ayrı çalışır; PWA ve
DexTerm değiştirilmez.
