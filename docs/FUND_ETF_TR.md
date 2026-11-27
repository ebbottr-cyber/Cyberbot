# Fon ve ETF araştırması

İlk aşama: ayrı SQLite arşivine kullanıcı tarafından sağlanan CSV aktarımı. CSV başlıkları: symbol,date,close. Tarih ISO YYYY-MM-DD, fiyat pozitif ondalık. Kaynak ve para birimi zorunlu. Kaynaklar doğrulanmış sayılmaz; fiyatlar temettüye göre düzeltilmiş kabul edilmez.

Örnek: `python -m tools.fund_etf_import --database fund_research.sqlite3 --csv funds.csv --market TEFAS --source TEFAS --currency TRY`

Hedef kaynaklar: TEFAS, KAP, TCMB EVDS, Yahoo Finance, Stooq, FRED. Otomatik erişim ve lisans doğrulaması bekliyor. Ücretli abonelik veya otomatik ücretli geçiş yok. Canlı veri, AI puanlama, backtest, portföy ve panel bağlantıları henüz uygulanmadı. Gerçek emir yok. Mevcut işlem motorundan bağımsız.
