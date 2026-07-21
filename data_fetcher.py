import ccxt
import pandas as pd
import os
from dotenv import load_dotenv

# Tải biến môi trường
load_dotenv()

class BinanceFetcher:
    def __init__(self):
        config = {'enableRateLimit': True}
        # Lưu lại tên sàn đang lấy được dữ liệu để báo cáo
        self.last_successful_exchange = "Đang tìm kiếm..."
        
        # Thứ tự ưu tiên: Binance (sàn chính) -> BinanceUS (Cùng hệ thống, giá cực sát) -> OKX -> MEXC -> Bybit
        self.exchanges = [
            ccxt.binance(config),
            ccxt.binanceus(config),
            ccxt.okx(config),
            ccxt.mexc(config),
            ccxt.bybit(config)
        ]

    def fetch_ohlcv(self, symbol="SOL/USDT", timeframe="5m", limit=100):
        """
        Lấy dữ liệu nến (OHLCV) từ Binance Futures.
        Trả về DataFrame pandas.
        """
        # Thử lần lượt các sàn, nếu sàn này lỗi thì nhảy sang sàn khác
        for exchange in self.exchanges:
            try:
                # Xử lý format symbol tùy theo từng sàn
                if exchange.id == 'binance':
                    exchange.options['defaultType'] = 'future'
                    fetch_symbol = symbol.replace(':USDT', '') # Dùng SOL/USDT
                elif exchange.id == 'binanceus':
                    # BinanceUS chỉ có Spot, nhưng giá bám sát 99.99% Binance Futures
                    exchange.options['defaultType'] = 'spot'
                    fetch_symbol = symbol.replace(':USDT', '') # Dùng SOL/USDT
                else:
                    fetch_symbol = symbol if ":" in symbol else f"{symbol}:USDT" # Format chuẩn ccxt: SOL/USDT:USDT
                    
                ohlcv = exchange.fetch_ohlcv(fetch_symbol, timeframe, limit=limit)
                
                if ohlcv and len(ohlcv) > 0:
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = df[col].astype(float)
                        
                    # YÊU CẦU ĐẶC BIỆT: Nếu dùng Bybit, cộng thêm 0.05 vào giá để đồng bộ với Binance
                    if exchange.id == 'bybit':
                        for col in ['open', 'high', 'low', 'close']:
                            df[col] = df[col] + 0.05
                            
                    # Cập nhật tên sàn đang dùng
                    self.last_successful_exchange = exchange.id.upper()
                    return df
            except Exception as e:
                print(f"⚠️ Sàn {exchange.id} từ chối kết nối: {e}")
                continue # Tiếp tục thử sàn tiếp theo
                
        # Nếu tất cả các sàn đều lỗi
        print("❌ Tất cả các sàn đều chặn API/IP.")
        return None
