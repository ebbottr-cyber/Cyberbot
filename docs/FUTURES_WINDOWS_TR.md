# Futures Windows kurulum ve baslatma

Proje klasorunde PowerShell acin. Varsayilan komut yalniz onizleme yapar.

```powershell
.\scripts\futures-windows.ps1
.\scripts\futures-windows.ps1 -Mode Prepare
```

Prepare ayri .venv-futures ortamini kurar, temel ve AI bagimliliklarini
yukler, pip check calistirir. Temiz Git HEAD'in gecici kopyasinda tum unit
testleri calistirir; CYBERBOT ortam degiskenleri test surecinden ayrilir.
Basari isareti tam commit'e baglidir. Yeni commit sonrasinda tekrar Prepare.
Gercek veri, emir, Windows gorevi veya otomatik baslatma yoktur.
Python 3.11/3.12 ve Git gerekir.

Veri kullanim haklari gercekten dogrulandiysa:

```powershell
.\scripts\futures-windows.ps1 -Mode Probe -ConfirmDataRights
.\scripts\futures-windows.ps1 -Mode Collect -Cycles 1200 -ConfirmDataRights
.\scripts\futures-windows.ps1 -Mode Status
```

Probe yalniz public Binance kotasyonunu kontrol eder, kasa yazmaz.
Collect yerel veri toplar ve yeterli kesintisiz veriyle AI arastirmasi
yapar. 1200 dakika yaklasik 20 saattir; PC uykuya gecerse veya dakika
kacarsa eksik veri doldurulmaz. 1440 dongu maksimumdur. Ctrl+C ile
durdurulabilir. Gemini otomatik kullanilmaz; API anahtari gerekmez.

PaperObserve ayri moddur; mevcut pilot/ingress izinleri, kaynak ve ayri
-ConfirmPaperObservation gerekir. Mevcut manuel sanal istekleri
isleyebilir. Yeni emir istegi olusturmaz. Gercek emir ve otomatik sanal
giris kapali. Mevcut kasa, kullanici verileri ve zamanlanmis gorevler
silinmez. Canli dogrulama ve otomatik sanal AI girisi sonraki asamalardir.

Script oturumluk degiskenleri sonunda geri yukler; kalici sistem ayari
degistirmez. PC'deki mevcut Git degisikliklerini otomatik birlestirmez,
silmez veya resetlemez. Test basarisi canli baglanti kaniti degildir.
