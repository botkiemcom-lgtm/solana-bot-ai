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

    def analyze(self, df):
        """
        Nhận DataFrame nến, tính toán chỉ báo và trả về tín hiệu nếu có.
        """
        if df is None or len(df) < self.ema_long:
            return None

        # 1. Tính toán các chỉ báo
        df['ema_9'] = ta.trend.ema_indicator(df['close'], window=self.ema_short)
        df['ema_21'] = ta.trend.ema_indicator(df['close'], window=self.ema_mid)
        df['ema_50'] = ta.trend.ema_indicator(df['close'], window=self.ema_long)
        df['rsi'] = ta.momentum.rsi(df['close'], window=self.rsi_period)
        
        # ATR cho biến động giá (dùng cho SL/TP)
        atr_indicator = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=self.atr_period)
        df['atr'] = atr_indicator.average_true_range()

        # Lấy cây nến hiện tại (chưa đóng hoàn toàn) hoặc nến trước đó
        # Trong scalping, thường xem xét nến vừa đóng xong để có tín hiệu chuẩn xác
        last_closed_candle = df.iloc[-2]
        current_candle = df.iloc[-1]

        # 2. Logic phán đoán xu hướng và Entry (Ví dụ cơ bản)
        # TĂNG (LONG): EMA 9 > 21 > 50 và RSI < 30 (Quá bán nhưng chạm hỗ trợ EMA)
        # GIẢM (SHORT): EMA 9 < 21 < 50 và RSI > 70 (Quá mua nhưng chạm kháng cự EMA)
        
        signal = None
        ema_trend = "Không rõ ràng"

        # Xu hướng Tăng
        if last_closed_candle['ema_9'] > last_closed_candle['ema_21'] > last_closed_candle['ema_50']:
            ema_trend = "Tăng (Bullish)"
            # Điều kiện vào lệnh Long: Giá điều chỉnh về gần EMA 21 và RSI có dấu hiệu bật lên (oversold ở xu hướng tăng)
            if last_closed_candle['low'] <= last_closed_candle['ema_21'] and last_closed_candle['close'] > last_closed_candle['ema_21']:
                signal = "LONG"

        # Xu hướng Giảm
        elif last_closed_candle['ema_9'] < last_closed_candle['ema_21'] < last_closed_candle['ema_50']:
            ema_trend = "Giảm (Bearish)"
            # Điều kiện vào lệnh Short: Giá hồi lên gần EMA 21 và bị đạp xuống
            if last_closed_candle['high'] >= last_closed_candle['ema_21'] and last_closed_candle['close'] < last_closed_candle['ema_21']:
                signal = "SHORT"

        # 3. Tính toán TP và SL nếu có tín hiệu
        if signal:
            entry_price = current_candle['close']
            atr_value = last_closed_candle['atr']
            
            # SL đặt cách 2.5 lần ATR, TP đặt cách 3.0 lần ATR (Risk:Reward ~ 1:1.2)
            if signal == "LONG":
                sl = entry_price - (2.5 * atr_value)
                tp = entry_price + (3.0 * atr_value)
            else: # SHORT
                sl = entry_price + (1.5 * atr_value)
                tp = entry_price - (2.5 * atr_value)

            return {
                "signal": signal,
                "entry": round(entry_price, 4),
                "tp": round(tp, 4),
                "sl": round(sl, 4),
                "rsi": last_closed_candle['rsi'],
                "ema_trend": ema_trend
            }

        return None
