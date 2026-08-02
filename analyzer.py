import pandas as pd
import ta
import numpy as np

class StrategyAnalyzer:
    def __init__(self, ema_short=9, ema_mid=21, ema_long=50, rsi_period=14, atr_period=14):
        self.ema_short = ema_short
        self.ema_mid = ema_mid
        self.ema_long = ema_long
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.last_insight = "Chưa có dữ liệu phân tích"

    def analyze(self, df_5m, df_30m, df_1h, df_btc_30m):
        """
        Logic Bắt Đáy Pullback trên khung 30m.
        """
        if df_30m is None or len(df_30m) < 50 or df_btc_30m is None or len(df_btc_30m) < 50:
            return None

        # Đồng bộ thời gian để join
        df = df_30m.copy()
        df_btc = df_btc_30m.copy()

        # Tính toán chỉ báo SOL
        df['ema_21'] = ta.trend.ema_indicator(df['close'], window=self.ema_mid)
        df['ema_50'] = ta.trend.ema_indicator(df['close'], window=self.ema_long)
        df['rsi'] = ta.momentum.rsi(df['close'], window=self.rsi_period)
        
        atr_indicator = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=self.atr_period)
        df['atr'] = atr_indicator.average_true_range()

        # Tính toán chỉ báo BTC
        df_btc['btc_ema_50'] = ta.trend.ema_indicator(df_btc['close'], window=50)

        # Gộp dữ liệu
        df = df.join(df_btc[['btc_ema_50']], how='left').dropna()
        if len(df) < 2: return None

        last_closed_candle = df.iloc[-2]
        
        signal = None
        ema_trend = ""
        
        # 1. Bộ lọc La Bàn (Xu hướng tổng thể 30m)
        uptrend = last_closed_candle['close'] > last_closed_candle['ema_50'] and last_closed_candle['btc_ema_50'] > 0 and df_btc.loc[last_closed_candle.name]['close'] > last_closed_candle['btc_ema_50']
        downtrend = last_closed_candle['close'] < last_closed_candle['ema_50'] and last_closed_candle['btc_ema_50'] > 0 and df_btc.loc[last_closed_candle.name]['close'] < last_closed_candle['btc_ema_50']

        rsi_val = last_closed_candle['rsi']

        # 2. Điểm bóp cò (Pullback chạm EMA 21)
        if uptrend and last_closed_candle['low'] <= last_closed_candle['ema_21'] and rsi_val < 60:
            signal = "LONG"
            ema_trend = "Cả BTC và SOL đều đang Uptrend đẹp, RSI nhúng rát, dốc toàn lực vớt hàng giá rẻ!"
        elif downtrend and last_closed_candle['high'] >= last_closed_candle['ema_21'] and rsi_val > 40:
            signal = "SHORT"
            ema_trend = "Cả BTC và SOL đều đang Downtrend mạnh, giá hồi lên kháng cự, chuẩn bị đập xuống!"
        else:
            self.last_insight = f"Đang theo dõi chặt chẽ (RSI: {rsi_val:.1f})"
            return None
            
        self.last_insight = ema_trend

        # 3. Tính toán Khối lượng và Stoploss (V4 + Hard SL 10 USD)
        entry_price = last_closed_candle['close'] # Limit ngay giá đóng cửa của cây nến vừa xong
        
        # AI chia vốn linh hoạt
        if (signal == "LONG" and rsi_val < 40) or (signal == "SHORT" and rsi_val > 60):
            margin = 200.0
            margin_desc = "200 USD (Kèo siêu đẹp - Đánh Full Vốn)"
        else:
            margin = 100.0
            margin_desc = "100 USD (Kèo rủi ro vừa - Đánh Nửa Vốn)"
            
        pos_usd = margin * 10 # Leverage 10x
        
        # Tính khoảng cách SL % sao cho nếu dính SL thì mất ĐÚNG 10 USD
        sl_pct = 10.0 / pos_usd
        
        if signal == "LONG":
            sl = entry_price * (1 - sl_pct)
        else:
            sl = entry_price * (1 + sl_pct)
            
        # 4. Tính toán Trailing Stop
        risk_distance = abs(entry_price - sl)
        # Activation = 1.5R
        activation_price = entry_price + (risk_distance * 1.5) if signal == "LONG" else entry_price - (risk_distance * 1.5)
        # Callback Rate = Kế thừa % khoảng cách SL (sl_pct * 100)
        callback_rate = round(sl_pct * 100, 2)

        return {
            "signal": signal,
            "entry": round(entry_price, 4),
            "margin_desc": margin_desc,
            "pos_usd": pos_usd,
            "sl": round(sl, 4),
            "activation_price": round(activation_price, 4),
            "callback_rate": callback_rate,
            "rsi": round(rsi_val, 1),
            "ema_trend": ema_trend
        }

    def monitor_trade(self, df_5m, df_30m, df_1h, df_btc_30m, active_trade):
        """
        Tạm thời tắt AI cảnh báo thoát sớm vì chúng ta đã dùng Trailing Stop của sàn Binance.
        Hàm này giữ nguyên cấu trúc để main.py không bị lỗi.
        """
        return None
