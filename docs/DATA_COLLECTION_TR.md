# EBBot aracılığıyla veri toplama

GitHub Actions envanter işi BIST, NASDAQ ve Xetra resmî aday listelerini EBBot koduyla yeniler; Solana için tek seferlik herkese açık havuz/profil gözlemi yapar. Başarısız kaynaklar raporlanır; seed liste tam kapsam değildir. Fiyat arşivi GitHub'a yüklenmez. Artifact 7 gün saklanır.

Yerel toplu fiyat toplama aracı mevcut EBBot Python ortamını ve Yahoo batch motorunu kullanır. Kaynak arşiv ve önbelleğe yazmaz. Ayrı Cyberbot SQLite dosyası üretir, aynı tarih aralığındaki tam serileri yeniden indirmez, eksik sembolleri 10'lu gruplarla tamamlar. Kaynak ve kurumsal işlem uyumu bağımsız doğrulanmaz; sonuç araştırma amaçlıdır. Varsayılan son 365 takvim günü, günlük OHLCV; `--start` ve `--end` ile değiştirilir. Borsa takviminde eksiksiz görünen sembol dahi lisans veya borsa üyeliği kanıtı değildir. Yeni kotasyon ve askıya alınmış hisselerde takvim eksikliği beklenebilir.

Örnek (Windows, Cyberbot depo kökünden):
```powershell
$eb = "$HOME\EBBot-CanliTest"
& "$eb\.venv\Scripts\python.exe" -m tools.refresh_universe
& "$eb\.venv\Scripts\python.exe" .\tools\collect_ebbot_daily.py --ebbot-root "$eb" --universe .\var\inventory\universe.csv --output .\var\ebbot-daily.sqlite3
```
Mevcut `stock_daily` SQLite dosyasını `--archive`, mevcut EBBot Yahoo cache dosyasını `--cache` ile belirtin. Sağlayıcı otomatik araştırma ve yerel saklama koşullarını teyit ettikten sonra `--allow-network` ekleyin. Bu seçenek yoksa ağdan fiyat indirilmez. Sonuç `ebbot-daily.coverage.json`. Sonra `CYBERBOT_EBBOT_DB` değişkenini üretilen SQLite dosyasına ayarlayın. Beş dakikalık farklı şema bu araçla desteklenmez. Solana geçmişinin tamamı tek snapshot ile elde edilemez.

EBBot dosyaları, işlem emirleri, özel anahtarlar, canlı hesaplar ve ayarları değiştirilmez.

## GitHub üzerinden günlük fiyat pilotu ve tam liste
Actions → EBBot yontemi - gunluk fiyat arsivi → Run workflow. Sağlayıcının otomatik erişim, saklama ve GitHub artifact kullanım hakkı doğrulandıysa rights_confirmed seçilir; aksi halde fiyat işi çalışmaz. Varsayılan 15 hisse pilotudur. full seçeneği tüm adayları 12 parçaya ayırır; aynı anda tek parça çalışır. Tarih ve envanter run ID değiştirilebilir. İlk envanter run 45860991983, artifact 7 gün saklanır. Fiyat çıktıları özel repo Actions artifact olarak 7 gün saklanır; yerel yedek alınmalıdır. Aynı tarih ve aynı envanterle resume_run girildiğinde bulunan fiyat serileri yeniden çekilmez; hiç veri dönmeyen hisseler tekrar denenir. Kısmi serinin eksik seansları bu sürümde otomatik tamamlanmaz; seans kontrolü için yerel EBBot aracı gerekir. Yahoo fiyatları düzeltilmiş geçmiş araştırma verisidir, canlı fiyat değildir. Çıktılar parça başına daily.sqlite3 ve coverage.json. CYBERBOT_EBBOT_DB ve CYBERBOT_COVERAGE_REPORT ile tek yerel parça panele bağlanabilir; çok parçanın birleştirilmesi sonraki adımdır. Tam kapsam, lisans ve borsa kimliği doğrulanmış sayılmaz.
