# Futures Watchdog & Auto Recovery V1

Prepare sonrası Windows ön plan oturumu:

```powershell
.\scripts\futures-windows.ps1 -Mode Watchdog -Cycles 4320 -ConfirmDataRights
```

Ayrı izinle sanal gözlem için -ConfirmPaperObservation kullanılabilir.
Mevcut pilot/ingress izinleri ayrıca gereklidir. İlk çocukta otomatik
sanal giriş ancak ayrıca -ConfirmAutoPaper ve mevcut tüm AI/risk izinleri
ile mümkündür. Varsayılan araştırma modudur.

- Supervisor aşama olaylarının 150 saniye kesilmesi, anormal çocuk çıkışı
  veya aynı kritik aşamada üç ardışık hata/kaçırılan slot toparlanmayı tetikler.
- Yalnız kendi çocuk sürecini sonlandırır; başka botlara, sistem servisine
  veya ortak kalıcı kill switch kaydına müdahale etmez.
- En fazla üç yeniden başlatma: 15, 30, 60 saniye bekleme. Oturum süresi
  en fazla 72 saattir; başarılı bitişte yeniden başlamaz.
- Her toparlanma çocuğunda otomatik giriş kapalıdır. Ortam giriş freni
  açıktır; mevcut pozisyonların gözlemi ve çıkışı sürdürülebilir, fakat
  giriş izni kendiliğinden geri gelmez. Yeniden otomatik moda geçiş ayrı
  operatör başlatması ve güvenlik kontrolü gerektirir.
- PC kapanırsa, ağ yoksa veya kotasyon alınamazsa stop/çıkış garanti
  değildir. Ctrl+C açık pozisyonu kapatmaz. Sürekli çalışma doğrulanmamıştır.
- Watchdog ve supervisor ayrı OS kilitleri kullanır. Diğer araçları aynı
  kasa üzerinde paralel çalıştırmayın. Kalıcı Windows görevi kurulmaz.
- Çocuk stderr'i saklanmaz; yalnız sınırlı yapılandırılmış aşama raporları
  terminale yazılır. Canlı bağlantı ve gerçek piyasa testi henüz yapılmadı.
