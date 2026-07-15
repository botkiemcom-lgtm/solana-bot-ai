import ccxt
import pandas as pd
import os
from dotenv import load_dotenv

# Tải biến môi trường
load_dotenv()

class BinanceFetcher:
    def __init__(self):
        api_key = os.getenv('BINANCE_API_KEY')
        secret = os.getenv('BINANCE_API_SECRET')
        
        # Bỏ qua nếu người dùng chưa điền API thật (chỉ dùng key mẫu)
        if api_key == "dien_api_key_cua_ban_vao_day" or not api_key:
            api_key = None
            secret = None

        config = {
            'enableRateLimit': True
        }
        
        # Chỉ truyền API key nếu có key thật
        if api_key and secret:
            config['apiKey'] = api_key
            config['secret'] = secret
            
        # Khởi tạo ccxt okx
        self.exchange = ccxt.okx(config)

    def fetch_ohlcv(self, symbol="SOL/USDT", timeframe="5m", limit=100):
        """
        Lấy dữ liệu nến (OHLCV) từ Binance Futures.
        Trả về DataFrame pandas.
        """
        try:
            # Gọi API lấy dữ liệu nến
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            # Chuyển đổi sang Pandas DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Chuyển đổi timestamp sang dạng datetime dễ đọc
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Đảm bảo các cột giá trị là số thực (float)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
                
            return df
            
        except Exception as e:
            print(f"Lỗi khi lấy dữ liệu Binance: {e}")
            return None
