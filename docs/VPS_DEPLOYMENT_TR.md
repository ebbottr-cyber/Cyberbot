# Obsidian — özel Linux VPS dağıtımı

Bu paket Ubuntu/Debian tarzı systemd sunucu için hazırlanmıştır. Gerçek sunucu üzerinde kurulmamıştır. Önce GitHub testleri tamamlanmış ve onaylanmış sürümü seçin. VPS, iPhone ve Tailscale hesabı operatör tarafından sağlanır. Bu yapılandırma paneli sürekli çalıştırır; araştırma worker'ını veya canlı işlem başlatmaz.

## 1. Ayrı servis hesabı ve kod

Yeni sunucuda mevcut `/opt/cyberbot`, `/etc/cyberbot`, `/var/lib/cyberbot`, 8765 TCP ve 8443 Tailscale Serve yapılandırması varsa üzerine yazmayın. Önce yedek ve mevcut servis kontrolü yapın. Python 3.11/3.12, venv, git, systemd ve Tailscale gerekir. GitHub özel repo erişimini kullanıcı yetkisiyle sağlayın; token'ı dosyaya veya komut geçmişine yazmayın.

Seçilen test edilmiş commit'i ayrı geçici checkout'ta alın. Yeni ve boş bir kurulumda:
```sh
sudo useradd --system --user-group --home-dir /var/lib/cyberbot --shell /usr/sbin/nologin cyberbot
sudo install -d -m 0755 /opt/cyberbot
sudo cp -a cyberbot tools requirements.txt deploy /opt/cyberbot/
sudo python3 -m venv /opt/cyberbot/.venv
sudo /opt/cyberbot/.venv/bin/python -m pip install -r /opt/cyberbot/requirements.txt
sudo chown -R root:root /opt/cyberbot
sudo chmod -R go-w /opt/cyberbot
sudo install -d -m 0700 /etc/cyberbot
sudo install -m 0600 deploy/linux/obsidian.env.example /etc/cyberbot/obsidian.env
sudoedit /etc/cyberbot/obsidian.env
```
Bu komutlar repo kökünden ve yalnız yeni kurulumda uygulanır. MagicDNS adı ve izinli tam Tailscale giriş adını yerel dosyada değiştirin. Yer tutucularla servis başlamaz. Piyasa sağlayıcıları ve uzaktan yazma kapalı tutulur.

## 2. Sürekli özel panel
```sh
sudo install -m 0644 deploy/linux/cyberbot-obsidian.service /etc/systemd/system/cyberbot-obsidian.service
sudo systemd-analyze verify /etc/systemd/system/cyberbot-obsidian.service
sudo systemctl daemon-reload
sudo systemctl enable --now cyberbot-obsidian.service
sudo systemctl status cyberbot-obsidian.service
sudo journalctl -u cyberbot-obsidian.service -n 50 --no-pager
ss -ltn
```
Uvicorn yalnız 127.0.0.1:8765 dinler. systemd servisi ayrı kullanıcı, salt okunur kod ve kalıcı veri dizini kullanır; başarısızlıkta yeniden başlatır. IPAddressDeny/Allow cgroup/BPF desteğine bağlı ek korumadır; etkinliğini gerçek sunucuda doğrulayın. Güvenilmeyen yerel kullanıcılar aynı sunucuda bulunmamalıdır. Bu servis içinde ağdan veri toplama ve gerçek emir yoktur.

## 3. Yetkili Tailscale HTTPS

Tailscale ACL/grant kuralları ile yalnız gerekli hesabı ve cihazları yetkilendirin. Yönetim panelinde HTTPS sertifikaları ve MagicDNS'i etkinleştirin. Sertifika adı kamu CT kayıtlarında görünebilir. Önce:
```sh
tailscale serve status
tailscale funnel status
```
Yalnız 8443 boş ve Funnel kapalı ise:
```sh
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8765
tailscale serve status
```
Funnel, genel port yönlendirme, 0.0.0.0 veya başka kimlik doğrulamasız proxy kullanmayın. Diğer servisleri değiştirmeyin.

## 4. Gerçek cihaz kabul testi
- Yetkili iPhone Tailscale ağına bağlıyken Serve çıktısındaki gerçek HTTPS adresini Safari'de açın; Ana Ekrana Ekle.
- Yetkisiz tailnet hesabı ve bağlantısız telefon erişememeli. Yerel kimliksiz HTTP isteği 403 dönmeli.
- Manifest, service worker, Veri Merkezi, Bot Gelişimi, Portföy, Uyarı Merkezi çalışmalı.
- Salt okunur modda yazma isteği 403 olmalı; gerçek emir ve dış ağ çağrısı yapılmamalı.
- Telefon bağlantısı kesildiğinde uyarı görünmeli; bağlantı geri gelince yeniden yüklenmeli.
- VPS yeniden başlatıldığında hizmet ve özel HTTPS erişimi tekrar kontrol edilmeli.

Bu kontroller tamamlanmadan yayın hazır sayılmaz. Panel açıldığında mevcut sentetik defter başlangıç kayıtları oluşabilir; bunun gerçek işlem olmadığını unutmayın.

## 5. Veri ve bakım
Yetkili arşiv ve kapsam raporlarını /var/lib/cyberbot/inputs altında servis hesabının okuyabildiği ayrı dosyalar olarak hazırlayın. Yerel env dosyasındaki CYBERBOT_NASDAQ_5M_REPORT ve CYBERBOT_BIST_XETRA_5M_REPORT yollarını tanımlayın. Arşiv lisansı ve dosya bütünlüğü ayrı doğrulanır. Yedekleme için servis hesabıyla uygulamanın kendi bakım aracını kullanın; canlı DB dosyalarını doğrudan kopyalamayın. Güncelleme önce ayrı test edilmiş sürüm, yedek, kontrollü servis durdurma/yeniden başlatma gerektirir.

Kapatmak için sadece Cyberbot'a ait 8443 Serve dinleyicisini kaldırın ve `sudo systemctl disable --now cyberbot-obsidian.service` çalıştırın. Diğer servisler ve veri dosyaları korunur.
