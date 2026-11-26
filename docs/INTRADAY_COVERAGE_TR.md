# Obsidian 5 dakikalık arşiv kapsamı

Veri Merkezi (/data), mevcut günlük özetinden ayrı olarak BIST 803, NASDAQ 3400 ve Xetra 1749 adayının 5m kapsamını gösterir. Bunlar dondurulmuş Cyberbot envanter hedefleridir; borsa üyeliği doğrulanmış tüm şirketler değildir.

- NASDAQ GitHub Actions run 45897632539: nasdaq-5m-final-coverage/summary.json
- BIST/Xetra run 45899469414: bist-xetra-final-coverage/summary.json

Raporlar mevcut olduğunda operatör bunları yetkili yerel dizine çıkarır; CYBERBOT_NASDAQ_5M_REPORT ve CYBERBOT_BIST_XETRA_5M_REPORT değişkenleri ilgili JSON dosya yollarına ayarlanır. Arayüzde Raporları yenile düğmesi ile yeniden okunur. Rapor yoksa veya tutarsızsa sayı bilinmiyor olarak gösterilir. Panel GitHub'a bağlanmaz, token almaz, fiyat dosyası indirmez ve arşiv dosyalarının bütünlüğünü bağımsız doğrulamaz. Bu rapor özeti canlı indirme durumunu temsil etmez. Veri sağlayıcı kullanım hakları ve gerçek işlem motoru bağlantısı ayrıca değerlendirilmelidir.
