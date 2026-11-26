# Kaynak bildirimleri

EBBot / daily_stock_analysis — MIT, Copyright (c) 2026 ZhuLinsen.

- `cyberbot/providers/solana_meme.py`: EBBot `data_provider/solana_meme.py`, özgün blob `2a2e10de32142688311364c2ec933d5f2e7a9c98`; doğrudan taşındı.
- `cyberbot/providers/equity.py`: EBBot `src/services/market_ml_ohlcv.py` içindeki salt-okunur `stock_daily` sorgusu ve OHLCV doğrulaması uyarlanmıştır (blob 2e77cc236416f3563289e2ee1ec22d6c2003f0e9).
- Lisans: `licenses/EBBOT-MIT.txt`.
- EBBot paneli, AI motoru veya diğer Daily Stock Analysis bileşenleri taşınmamıştır.

- `vendor/ebbot/four_market_universe_builder.py`: EBBot kaynak kodu, blob `3bdc3cd6a24ecedf548811cbb926851f2dc4ec96`.
- `vendor/ebbot/seed.csv`: EBBot başlangıç hisse adayları, blob `1a71811012b86ac9f7637751c5fb17c61cc300fb`.

- `tools/cloud_daily.py`: EBBot Yahoo gruplu veri indirme yaklaşımının bağımsız uyarlaması; `data_provider/yfinance_fetcher.py` kaynak referansı. Eski motorun tamamı veya paneli taşınmadı.

Bilgi merkezi: kepano/kepano-obsidian, obsidianmd/obsidian-skills ve kepano/obsidian-minimal (MIT) tasarım referansları; kod, tema veya vault kopyalanmadı. JSON Canvas 1.0 açık formatı bağımsız üretildi (https://github.com/obsidianmd/jsoncanvas). Dış araçlar yalnız geliştirme planında.
