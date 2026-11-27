# Obsidian — özel Tailscale erişimi

Varsayılan yerel mod korunur. Bu seçenek PC üzerinde uygulanacaktır; GitHub'dan cihaz ayarları değiştirilmez. Tailscale Serve özel HTTPS ters proxy kullanır, Funnel kullanılmaz. Fiziksel cihaz testi henüz yapılmamıştır.

## Hazırlık
- PC ve iPhone aynı yetkili Tailscale ağında olmalı; Tailscale ACL/grant kurallarını yalnız gerekli kullanıcı/cihazlara sınırlayın.
- Tailscale yönetim panelinden PC'nin tam MagicDNS adını ve yetkili hesabın tam giriş adını doğrulayın. Örnekleri gerçek değerle değiştirin; bu değerleri GitHub'a kaydetmeyin.
- Önce `tailscale serve status` ve `tailscale funnel status` kontrol edin. Mevcut Serve/Funnel yapılandırmalarını değiştirmeyin. Cyberbot için 8443 HTTPS portu boş olmalı; uygulama 127.0.0.1:8765 üzerinde çalışır.
- HTTPS sertifika adlarının kamuya açık sertifika şeffaflık kayıtlarında bulunabileceğini unutmayın; hassas makine isimleri kullanmayın.

## Windows PowerShell
Cyberbot dizininde mevcut venv ile aşağıdaki komutları çalıştırın. İlk olarak salt okunur mobil erişim kullanın.

```powershell
$env:CYBERBOT_TAILSCALE_ENABLED = "1"
$env:CYBERBOT_TAILSCALE_HOST = "pc.example.ts.net"
$env:CYBERBOT_TAILSCALE_LOGIN = "owner@example.com"
$env:CYBERBOT_TAILSCALE_WRITE = "0"
.\.venv\Scripts\python.exe -m uvicorn cyberbot.api:app --host 127.0.0.1 --port 8765 --no-proxy-headers
```

Ayrı PowerShell penceresinde, yalnız 8443 boş ve özel Serve yetkisi doğrulandıysa:

```powershell
tailscale serve --bg --https=8443 http://127.0.0.1:8765
tailscale serve status
```

Safari'de Serve çıktısındaki gerçek HTTPS adresini açın. Yetkili Tailscale kimliği gerekir. Ana Ekrana Ekle ile PWA oluşturun. PC ve uygulama açık kalmalıdır. Salt okunur modda yeni sanal işlem ve model çalıştırma istekleri reddedilir.

İsteğe bağlı olarak yalnız doğrulama tamamlandıktan sonra `CYBERBOT_TAILSCALE_WRITE=1` ile uygulamayı yeniden başlatın. Gerçek emir desteği yoktur.

Kapatmak için sadece bu özel dinleyiciyi kaldırın: `tailscale serve --https=8443 off`. Uvicorn'u Ctrl+C ile kapatın. Mevcut diğer Serve yapılandırmalarına dokunmayın.

## Güvenlik varsayımları
Loopback erişimi ve `--no-proxy-headers` zorunludur. Uygulama Tailscale'in eklediği kullanıcı kimliğini ve tam host adını doğrular, izinli yazmalarda HTTPS Origin ve özel başlık ister. Yerel makinedeki güvenilmeyen süreçler bu güven sınırının dışındadır. Funnel kimlik başlığı sağlamaz ve erişim reddedilir. Başka proxy, port yönlendirme veya 0.0.0.0 kullanmayın. API verileri önbelleğe alınmaz. Tailscale CLI/kimlik entegrasyonu gerçek cihazda henüz denenmemiştir.

Resmî belgeler: https://tailscale.com/docs/features/tailscale-serve ve https://tailscale.com/docs/reference/tailscale-cli/serve

Mevcut 443/8443 yönlendirmeleri kullanılıyorsa 8444 alternatifi: önceden boş olduğunu Serve/Funnel ve TCP dinleyici kontrolleriyle doğrulayın. Sunucu ortamında `CYBERBOT_TAILSCALE_PORT=8444` ayarlayın ve yalnız `tailscale serve --bg --https=8444 http://127.0.0.1:8765` kullanın. Erişim adresi `https://<MagicDNS>:8444`; kapatma `tailscale serve --https=8444 off`. Diğer yönlendirmeler korunur.
