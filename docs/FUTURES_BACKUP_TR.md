# Futures yedekleme ve durum kurtarma V1

Önce tüm Futures supervisor/watchdog ve diğer veri yazıcılarını durdurun.
Açık sanal pozisyonları kontrol edin. Veri yedekleme hakları doğrulanmışsa:

```powershell
.\scripts\futures-windows.ps1 -Mode Backup -BackupRoot 'D:\CyberbotBackups' -ConfirmBackupRights -ConfirmOffline
```

Pilot verisi varsa mevcut CYBERBOT_PILOT_BACKUP_RIGHTS_CONFIRMED=1 izni
ayrıca gerekir. Eğitim, AI hafıza, ileri tahmin, teşhis ve yalnız FUTURES
sanal kasa kayıtları alınır. BIST/SOLANA ve ortak CONTROL geçmişi dahil
edilmez. SQLite kopyaları tek tek bütünlük kontrolünden geçer. Manifest
SHA-256 özetlerini, boyutları, atlanan dosyaları içerir. Her dosya en
fazla 512 MiB. Kopyalar farklı veritabanlarının tek atomik anlık görüntüsü
değildir; işbirliği yapan süreçler kilitlenir, diğerlerini operatör durdurur.
Yedekler şifrelenmez; yerel erişim ve disk alanı operatör sorumluluğundadır.

```powershell
.\scripts\futures-windows.ps1 -Mode VerifyBackup -BackupDirectory 'D:\CyberbotBackups\futures-backup-...'
.\scripts\futures-windows.ps1 -Mode StageRecovery -BackupDirectory 'D:\CyberbotBackups\futures-backup-...' -BackupRoot 'D:\CyberbotRecovery' -ConfirmBackupRights
```

VerifyBackup salt okunur dosya listesi, hash, şema ve bütünlük kontrolüdür.
Hash dijital imza değildir; yalnız güvenilen yerel yedekleri kullanın.
StageRecovery yeni benzersiz klasörde kopyaları hazırlar, bekleyen LONG/SHORT
girişlerini iptal eder ve kopya kasada kalıcı giriş freni oluşturur.
Açık pozisyon ve bekleyen CLOSE korunur. Kaynak yedek veya aktif kasa
değişmez. Dosyalar otomatik aktif edilmez; fonlama, fiyat, zaman ve pozisyon
mutabakatı gerekir. Yeni giriş izinleri manuel güvenlik kontrolü olmadan
açılmamalıdır. Model ağırlıkları yedeklenmez (mevcut sistem saklamıyor).
Otomatik yedek zamanlayıcısı, bulut yükleme ve gerçek emir yoktur.
