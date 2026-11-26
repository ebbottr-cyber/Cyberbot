# Cyberbot — Obsidian

Bağımsız Türkçe piyasa araştırması ve yalnızca sanal işlem platformu. EBBot'un yalnız veri modülleri ve veri adaptörleri lisans bildirimleri korunarak kullanılmıştır; eski işlem motoru ve paneli taşınmamıştır.

## Sürüm 0.1
- FastAPI, SQLite, mobil uyumlu Türkçe web paneli.
- BIST, NASDAQ, XETRA ve Solana için sentetik örnek veriler.
- Uzun pozisyon sanal defteri: ücret, fiyat kayması, işlem riski, pozisyon limiti, günlük kayıp ve düşüş sınırı.
- Basit hareketli ortalama geçmiş veri deneyi.
- Gerçek emir, cüzdan imzalama, özel anahtar veya borsa işlem API'si yoktur.
- AI araştırma, laboratuvar, öğrenme, model ve PWA modüllerinin ilk sürümleri mevcuttur; gerçek veri/model ve cihaz doğrulaması ayrıca gereklidir.

## Yerel çalıştırma (Python 3.11/3.12)
```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn cyberbot.api:app --host 127.0.0.1 --port 8000
```
Panel: http://127.0.0.1:8000

Test: `python -m unittest discover -s tests -v`.
Veri dosyası: `var/paper.sqlite3` (CYBERBOT_DB ile değiştirilebilir).
Uygulama yalnız yerel istemciler için tasarlanmıştır. İnternete açmayın; uzaktan erişim için ayrı kimlik doğrulama, TLS ve güvenlik incelemesi gerekir.
Tüm fiyatlar **sentetik ve USD cinsindendir**; gerçek piyasa performansı değildir.

## EBBot veri bağlantısı (yalnız veri)
`CYBERBOT_EBBOT_DB` değişkeni, kullanım hakkı olan ve `stock_daily` tablosu içeren mevcut SQLite dosyasının yoluna ayarlanır. Kaynak veritabanı salt okunur açılır, kopyalanmaz veya değiştirilmez. Beş dakikalık arşivin farklı şeması ayrıca doğrulanmalıdır. BIST/NASDAQ/XETRA etiketleri araştırma seçeneğidir; borsa üyeliği ve canlı fiyat doğrulanmaz.
`CYBERBOT_SOLANA_READ_ENABLED=1` ile isteğe bağlı salt okunur GeckoTerminal/DEX Screener taraması açılabilir. Varsayılan kapalıdır; manuel tarama dışında ağ isteği yoktur. Panel: /data. Gerçek gözlemler sentetik işlem motorundan ayrıdır. Veri hakları operatörce doğrulanmalıdır. Kaynak lisansları THIRD_PARTY_NOTICES.md içindedir.

## Trader Merkezi
`/traders`: açık Solana adresi için son kesinleşmiş işlem imzalarını salt okunur RPC ile gösterir. Ağ erişimi varsayılan kapalıdır. `CYBERBOT_SOLANA_READ_ENABLED=1` gereklidir. İmzalar takas, gerçekleşmiş getiri veya kopyalanabilirlik kanıtı değildir. Manuel gölge araştırması için `CYBERBOT_SHADOW_FILE` yerel JSON dosyası tanımlanabilir. Her satır: wallet,event,signal_at,entry_at,exit_at,entry_price,exit_price,fee_bps,slippage_bps; fiyat ve maliyet alanları ondalık metin, tarihler ISO-8601 zaman dilimli. Dosya yoksa sentetik demo. Otomatik takas sınıflandırması, Jupiter teklifleri, sürekli izleme ve zincirden P&L çıkarma henüz yoktur. ETRE yaklaşımından esinlenildi; GPL kaynak kodu taşınmadı.

## Toplu veri toplama
[EBBot veri toplama talimatları](docs/DATA_COLLECTION_TR.md). GitHub envanter işi fiyat arşivi yerine aday listesi ve sınırlı Solana gözlemi üretir.

## Model Merkezi
`/models` çevrimdışı tahmin kıyaslaması. İsteğe bağlı yerel Ollama bağlantısı: `CYBERBOT_LOCAL_LLM_ENABLED=1` ve `CYBERBOT_OLLAMA_MODEL` kurulu yerel modelin adı. Ollama ayrı kurulur; Cyberbot yalnız 127.0.0.1:11434 üzerinden sentetik rapor özeti gönderir, model indirmez. Yerel modelin kendi ayarları operatörün sorumluluğundadır. LLM yanıtı doğrulanmamış metindir; emir ve otomatik terfi yoktur. Chronos henüz bağlı değildir.

### İsteğe bağlı Chronos 2
Ayrı `requirements-chronos.txt` bağımlılık dosyası; standart Cyberbot kurulumuna dahil değildir. Önceden edinilmiş, güvenilir ve kullanım hakkı kontrol edilmiş yerel Chronos 2 ağırlık dizinini `CYBERBOT_CHRONOS_PATH` ile belirtin, `CYBERBOT_CHRONOS_ENABLED=1` ile etkinleştirin. Model Merkezi üzerinden manuel kıyaslama. Otomatik ağırlık ve piyasa verisi indirme yoktur. Referans: https://huggingface.co/amazon/chronos-2 ve https://github.com/amazon-science/chronos-forecasting. Gerçek çıkarım testi henüz yapılmadı.

## Obsidian PWA
Mobil manifest, Apple Touch ikonu ve ağ bağlantısı olmadığında yalnız uyarı gösteren service worker hazır. Safari üzerinden Paylaş → Ana Ekrana Ekle, ancak iPhone'un Cyberbot sunucusuna güvenli HTTPS erişimi yapılandırılmalıdır. Şu anda uygulama sadece localhost kabul eder; PC'nin LAN adresini açmak veya portu internete yönlendirmek çözüm değildir. API yanıtları ve işlem verileri önbelleğe alınmaz, çevrimdışı işlem kuyruğu yoktur. Gerçek iPhone testi ve güvenli uzaktan erişim henüz tamamlanmamıştır.

## Özel mobil erişim
[Windows / Tailscale Serve kurulum talimatları](docs/REMOTE_ACCESS_TR.md). Uzaktan erişim varsayılan kapalı; yalnız yetkili Tailscale kimliği ve tam HTTPS adresi kabul edilir. Gerçek cihaz kurulumu henüz yapılmadı.

Toplu tarihsel fiyat indirme kapatılmıştır; ağ indirme komutları da engellenmiştir. Eski artifact dosyaları kullanım hakkı doğrulanmadan kullanılmamalıdır.

## Windows kolay kurulum ve bakım
Cyberbot'un ayrı checkout klasöründe PowerShell: ` .\\scripts\\setup-windows.ps1 ` (Python 3.11/3.12 gerekir; bağımlılık kurar ve testleri çalıştırır). Ardından ` .\\scripts\\start-windows.ps1 ` ile yerel panel http://127.0.0.1:8765 . Bu başlatıcı dış sağlayıcıları ve uzaktan erişimi kapalı tutar, EBBot'a dokunmaz. Sunucu logları var/logs dizininde; erişim logu kapalıdır. Sağlık: /health veya `.venv\\Scripts\\python.exe -m tools.ops health`. Yedek: `.venv\\Scripts\\python.exe -m tools.ops backup` (yalnız Cyberbot SQLite dosyaları, var/backups; aynı veri dizininde çalıştırın). Yedekler ayrı zaman damgalı klasörlerde, bütünlük ve SHA-256 manifesti ile saklanır. Otomatik silme veya geri yükleme yapılmaz. Yedekler dosya bazında tutarlıdır, iki DB arasında ortak anlık görüntü garanti edilmez. Gerçek Windows PC kurulumu denenmedi.

## Araştırma zamanlayıcısı (isteğe bağlı)
Tek döngü: `python -m tools.worker`. Sürekli: `python -m tools.worker --loop --interval 900` (Ctrl+C durdurur). Windows: `scripts/worker-windows.ps1`. Varsayılan sentetik, aynı deney yeniden öğrenme olarak sayılmaz. İzinli yerel arşiv için açıkça `--market BIST --symbol THYAO.IS` ve CYBERBOT_EBBOT_DB gerekir. `--daily-backup` eklenirse UTC gününde en çok bir başarılı yerel yedek. Sistem Sağlığı sayfası son döngüyü gösterir; worker kayıtları var/worker.sqlite3 içinde en çok 1000 kayıt, mevcut yedek kapsamı dışında. Windows oturum açılışında çalıştırmak için ayrı ve isteğe bağlı `scripts/register-worker-windows.ps1 -Register`; görev otomatik başlatılmaz, mevcut görev üzerine yazılmaz. Görev adı Cyberbot-Research-Worker; Görev Zamanlayıcı'dan durdurulabilir. Gerçek PC kurulumu henüz yapılmadı.

## Sentetik stres testi
`python -m tools.stress --steps 240`: dört ayrı senaryo, mevcut paper motoru ve geçici SQLite defteri; ana portföy ve EBBot dosyalarına dokunulmaz. Obsidian Risk Merkezi altında `/stress`. Her senaryo tek varsayımsal UTC oturumudur; gerçek piyasa performansı değildir. Otomatik gerçek veya sanal portföy işlemi yoktur.
