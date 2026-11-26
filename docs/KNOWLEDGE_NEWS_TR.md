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
