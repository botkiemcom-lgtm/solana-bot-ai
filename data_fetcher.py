import ccxt
import pandas as pd
import os
from dotenv import load_dotenv

# Tải biến môi trường
load_dotenv()

class BinanceFetcher:
    def __init__(self):
        config = {'enableRateLimit': True}
        # Cấu hình danh sách các sàn để dự phòng (Fallback) nếu 1 sàn chặn IP
        self.exchanges = [
            ccxt.binance(config),
            ccxt.bybit(config),
            ccxt.okx(config),
            ccxt.mexc(config)
        ]

    def fetch_ohlcv(self, symbol="SOL/USDT", timeframe="5m", limit=100):
        """
        Lấy dữ liệu nến (OHLCV) từ Binance Futures.
        Trả về DataFrame pandas.
        """
        # Thử lần lượt các sàn, nếu sàn này lỗi thì nhảy sang sàn khác
        for exchange in self.exchanges:
            try:
                # Với Binance, cần set mặc định là future để lấy nến chính xác
                if exchange.id == 'binance':
                    exchange.options['defaultType'] = 'future'
                    fetch_symbol = symbol.replace(':USDT', '') # Dùng SOL/USDT
                else:
                    fetch_symbol = symbol if ":" in symbol else f"{symbol}:USDT" # Format chuẩn ccxt: SOL/USDT:USDT
                    
                ohlcv = exchange.fetch_ohlcv(fetch_symbol, timeframe, limit=limit)
                
                if ohlcv and len(ohlcv) > 0:
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = df[col].astype(float)
                    return df
            except Exception as e:
                print(f"⚠️ Sàn {exchange.id} từ chối kết nối: {e}")
                continue # Tiếp tục thử sàn tiếp theo
                
        # Nếu tất cả các sàn đều lỗi
        print("❌ Tất cả các sàn đều chặn API/IP.")
        return None
