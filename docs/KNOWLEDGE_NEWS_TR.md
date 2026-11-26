# Bilgi hafızası ve haber araştırması
Vault: /knowledge ve /api/knowledge/vault.zip; bağımsız Markdown, .base ve JSON Canvas 1.0 anlık görüntüsü. Gerçek Obsidian uygulaması veya eklentileri kurulmaz. Minimal esintili ortak CSS yalnız yeni ekranlarda; Pulse renkleri korunur. Ajan becerisi .agents/skills/cyberbot-knowledge/SKILL.md özgün talimat dosyasıdır; otomatik ajan çalışmaz.

Haber Merkezi: /news. KAP, TCMB, SEC, FED, ECB, Binance, Solana ve GDELT bağlantı kataloğu; manuel özgün etiket, URL, olay zamanı, piyasa, kategori, takvim/haber ayrımı ve yinelenen referans kontrolü. Kaynaklar otomatik sorgulanmaz, makale içeriği toplanmaz. Duygu analizi ve fiyat etkisi hesaplanmaz. Haber kaydı araştırma DB'sinde ayrı tabloda; işlem motoruna bağlanmaz.

## Sonraki bağımsız değerlendirmeler
- Feedparser (BSD-2-Clause): izinli RSS kaynakları; önce her kaynağın kullanım hakları, sınırları ve güncelliği.
- GDELT: bağlantı ve olay meta verisi; yayıncı içeriği lisansı ayrıca incelenir.
- NetworkX (BSD-3-Clause): haber-şirket-strateji ilişkileri; yalnız doğrulanmış eşleşmeler.
- GraphRAG (MIT): büyük bilgi arşivi ve yerel model bütçesi gerektirdiğinde.
- DuckDB (MIT): SQLite yeterli olmazsa salt okunur analiz.
- Lightweight Charts (Apache-2.0): kaynak bildirimi ve TradingView atıf koşullarıyla grafik pilotu.
- OpenBB V5: sürüme özgü lisans ve veri sağlayıcı koşulları ayrıca doğrulanarak; V4 AGPL taşınmaz.
- Ekonomik olay etkisi: yayın zamanı / ilk gözlem zamanı ayrımı, 5/15/60 dakika ve 24 saat fiyat reaksiyonu, izinli veri ve takvim eşleştirmesi; henüz ölçüm yok.
- Sentiment: model ve ağırlık lisansı ayrıca kontrol edilir; FinBERT şimdilik dışarıda.
Bu aday bağımlılıkların hiçbiri kurulmadı; kaynak kodları taşınmadı.

## RSS pilotu
FED resmi para politikası RSS (https://www.federalreserve.gov/feeds/feeds.htm) ve ECB resmi basın RSS (https://www.ecb.europa.eu/home/html/rss.en.html). FED genel kamu malı kuralı üçüncü taraf istisnaları içerir; ECB kaynak belirtme/doğru aktarım ve diğer koşullara tabidir. Kaynak başlığı, URL, yayın zamanı, ilk kayıt zamanı ve özgün kural kategorisi dışında içerik yok. Makale, açıklama, görsel veya PDF çekilmez. Kaynak koşulları operatör tarafından doğrulanmadan etkinleştirilmez. CYBERBOT_NEWS_ENABLED=1 ve CYBERBOT_NEWS_APPROVED=fed,ecb yerel olarak açıkça ayarlanabilir. python -m tools.news_feed --loop isteğe bağlı; 15 dakika/sorgu, en çok 40 öğe ve 1 MiB yanıt, 30 gün RSS kayıt süresi, yalnız sabit HTTPS kaynakları, yönlendirme yok. Manuel kayıtlar ayrı tutulur. Varsayılan kapalı; gerçek RSS yanıtı test edilmedi, testler sentetik XML kullanır. Etiketleme anahtar sözcüklerle yapılır, yapay zekâ duygu/etki değerlendirmesi değildir. Feedparser bağımlılığı eklenmedi; sınırlı RSS 2.0 stdlib ayrıştırıcısı kullanıldı.

## Haber bilgi ağı
Kaynak → haber → kayıt kapsamı/kategori; kategori → strateji bağlantıları yalnız sürümlü araştırma hipotezidir. Operatör açık kanıt URL'siyle varlık kodu eşleştirebilir; şirket kimliği ve piyasa etkisi doğrulanmış sayılmaz. Son 100 görünür haber ve en fazla 200 ilgili eşleşme, salt okunur ağ; kapalı RSS kayıtları dışarıda. Vault Haberler.canvas yalnız piyasa kapsam sayıları içerir, yayıncı başlıkları ve kanıt URL'leri dışa aktarılmaz. NetworkX henüz gerekmedi; bağımsız düğüm/kenar yapısı. Otomatik şirket eşleştirme, AI duygu modeli ve fiyat tepkisi ölçümü henüz yok.

## Olay penceresi araştırması
1/5 dakika UTC kapanış zamanlı yerel JSON, yalnız açık izin beyanı (CYBERBOT_NEWS_PRICE_RIGHTS_CONFIRMED=1) ve görünür haber/operatör varlık eşleşmesi ile. CLI: python -m tools.news_impact --file <yerel-json> --record <manual:... veya rss:...> --market BIST --symbol THYAO.IS. JSON alanları: market, symbol, source, timestamp_convention=bar_close, interval_minutes=1 veya 5, prices=[{closed_at: ISO8601 saat dilimli zaman, close: pozitif fiyat}]. Yayın ve ilk kayıt zamanına göre 5/15/60/1440 dakika; kesin önceki grid kapanışı ve ufukta/sonrasında ilk grid kapanışı; tüm ara kapanışlar gerekli. Seans boşluğu olan pencerede ölçüm yok; gerçek takvimle seans eşleştirme sonraki adım. Gelecek fiyat reddedilir, henüz dolmayan ufuk bekler. Kayıtlar kaynak ve zamanlarla ayrıdır, ham fiyat kaydedilmez. /api/news/impact ayrı sentetik örnek ve izinli yerel doğrulanmamış kayıtlar. Nedensellik, işlem getirisi, model eğitimi veya canlı fiyat doğrulaması yok. Ağ ve toplu indirme yok.

## Haber performans hafızası
Salt okunur /api/news/memory ve Haber Merkezi tablosu. Yalnız izin beyanlı yerel event-window-1 ölçümleri ve görünür haberler; demo dahil değil. Varlık, fiyat kaynağı, 1/5 dk çözünürlük, yayın/ilk kayıt ve ufuk ayrı. Aynı URL'nin aynı ölçümleri tekilleştirilir; çelişkili tekrarlar ve aynı zamanlı farklı URL'ler elenir. Kategori ayrımı öncesi örtüşen pencereler aynı kapsamda elenir; en erken biten pencere tutulur. En az 20 olayla ortalama, medyan, olaylar arası standart sapma, ortalama mutlak tepki ve yön oranları. Bu eşik anlamlılık/bağımsızlık kanıtı değil; gruplar toplanmaz. En çok 100 görünür haber ve 1000 rapor; sınır aşımında hesap yok. Yeni ağ veya ham fiyat kaydı, emir, tahmin ya da otomatik terfi yok.
