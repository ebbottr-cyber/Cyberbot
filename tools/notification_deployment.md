# Cyberbot PWA — kurulum kontrol listesi

- Geliştirme dalındaki çevrimdışı testler başarılı olmadan ana dala birleştirme yapma.
- Windows hazırlığı: notification_manage.ps1 -Action Install.
- API sürecinde CYBERBOT_NOTIFICATION_PANEL_ENABLED=1 ayarla ve mevcut API başlatma yöntemini kullan.
- Yerel erişimde Tailscale kapalı kalabilir. Tailscale etkin olduğunda erişim yalnız yapılandırılmış HTTPS alan adı ve kullanıcı üzerinden sağlanır.
- CYBERBOT_TAILSCALE_ENABLED, CYBERBOT_TAILSCALE_HOST, CYBERBOT_TAILSCALE_LOGIN ve CYBERBOT_TAILSCALE_PORT mevcut erişim korumasına aittir.
- CYBERBOT_TAILSCALE_WRITE varsayılan olarak kapalı kalmalı. Sadece bildirim aboneliği için genel yazma yetkisini açma.
- CYBERBOT_NOTIFICATION_NEWS_BRIDGE=1 yalnız worker ortamında mevcut onaylı RSS kayıtlarını aktarır; RSS indirme işlemi başlatmaz.
- VAPID anahtarları isteğe bağlıdır. CYBERBOT_VAPID_PUBLIC_KEY API ortamında, CYBERBOT_VAPID_PRIVATE_KEY_FILE ve CYBERBOT_VAPID_SUBJECT gönderici ortamında tanımlanır. Özel anahtarı Git'e koyma.
- Varsayılan Windows görevi --push kullanmaz. Telefon teslimatı ayrıca doğrulanmalıdır.
- notification_manage.ps1 -Action Doctor yerel sağlık kontrolü yapar. Tailscale-only modunda yerel HTTP reddedilebilir.
- Mobil bildirim yönetimi için API ortamında CYBERBOT_TAILSCALE_NOTIFICATION_WRITE=1 ve CYBERBOT_NOTIFICATION_PANEL_ENABLED=1 kullanılabilir. CYBERBOT_TAILSCALE_WRITE=0 kalmalıdır. Bu izin yalnız bildirim ayarları, okundu işaretleme ve abonelik uçlarına uygulanır; canlı doğrulama gereklidir.
- Gerçek emir, işlem motoru ve piyasa verisi yapılandırmaları bu kurulumun kapsamı dışındadır.
