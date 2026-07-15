import pandas as pd
import ta
import numpy as np
import joblib
import os
class StrategyAnalyzer:
    def __init__(self, ema_short=9, ema_mid=21, ema_long=50, rsi_period=14, atr_period=14):
        self.ema_short = ema_short
        self.ema_mid = ema_mid
        self.ema_long = ema_long
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        
        # Load não AI nếu có
        self.model = None
        if os.path.exists('xgb_model.pkl'):
            try:
                self.model = joblib.load('xgb_model.pkl')
            except Exception as e:
                print(f"Lỗi load AI: {e}")

    def analyze(self, df_5m, df_15m, df_1h, df_4h):
        """
        Nhận DataFrame nến 5m, 15m, 1H và 4H, tính toán chỉ báo Đa khung thời gian.
        """
        if df_5m is None or len(df_5m) < self.ema_long or df_1h is None or len(df_1h) < 50 or df_15m is None or df_4h is None:
            return None

        # --- 1. TÍNH TOÁN KHUNG 15M, 1H, 4H ---
        df_15m['ema_21'] = ta.trend.ema_indicator(df_15m['close'], window=21)
        df_15m['ema_50'] = ta.trend.ema_indicator(df_15m['close'], window=50)
        trend_15m_bullish = df_15m.iloc[-2]['ema_21'] > df_15m.iloc[-2]['ema_50']
        
        df_1h['ema_21'] = ta.trend.ema_indicator(df_1h['close'], window=21)
        df_1h['ema_50'] = ta.trend.ema_indicator(df_1h['close'], window=50)
        trend_1h_bullish = df_1h.iloc[-2]['ema_21'] > df_1h.iloc[-2]['ema_50']
        
        df_4h['ema_21'] = ta.trend.ema_indicator(df_4h['close'], window=21)
        df_4h['ema_50'] = ta.trend.ema_indicator(df_4h['close'], window=50)
        trend_4h_bullish = df_4h.iloc[-2]['ema_21'] > df_4h.iloc[-2]['ema_50']

        # Đồng thuận khung lớn (15m, 1h, 4h)
        mtf_bullish = trend_15m_bullish and trend_1h_bullish and trend_4h_bullish
        mtf_bearish = not trend_15m_bullish and not trend_1h_bullish and not trend_4h_bullish

        # --- 2. TÍNH TOÁN KHUNG 5M ---
        df = df_5m.copy()

        # 2.1 Các chỉ báo giá
        df['ema_9'] = ta.trend.ema_indicator(df['close'], window=self.ema_short)
        df['ema_21'] = ta.trend.ema_indicator(df['close'], window=self.ema_mid)
        df['ema_50'] = ta.trend.ema_indicator(df['close'], window=self.ema_long)
        df['rsi'] = ta.momentum.rsi(df['close'], window=self.rsi_period)
        # 2.2 Động lượng Dòng tiền (OBV) & MACD
        df['obv'] = ta.volume.on_balance_volume(df['close'], df['volume'])
        df['obv_diff'] = df['obv'].diff()

        macd = ta.trend.MACD(df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()

        
        # 2.3 ADX & Bollinger Bands
        adx_indicator = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
        df['adx'] = adx_indicator.adx()
        
        bb_indicator = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
        df['bb_upper'] = bb_indicator.bollinger_hband()
        df['bb_lower'] = bb_indicator.bollinger_lband()
        
        # ATR cho biến động giá (dùng cho SL/TP)
        atr_indicator = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=self.atr_period)
        df['atr'] = atr_indicator.average_true_range()

        # Lấy cây nến hiện tại (chưa đóng hoàn toàn) hoặc nến trước đó
        # Trong scalping, thường xem xét nến vừa đóng xong để có tín hiệu chuẩn xác
        last_closed_candle = df.iloc[-2]
        current_candle = df.iloc[-1]
        prev_candle = df.iloc[-3] # Lấy nến trước đó nữa để so sánh OBV

        # 3. Logic Đa khung thời gian & Dòng tiền (V2.0)
        signal = None
        ema_trend = "Không rõ ràng"

        # Xu hướng 5m
        trend_5m_bullish = last_closed_candle['ema_9'] > last_closed_candle['ema_21'] > last_closed_candle['ema_50']
        trend_5m_bearish = last_closed_candle['ema_9'] < last_closed_candle['ema_21'] < last_closed_candle['ema_50']
        
        # Động lượng OBV
        obv_increasing = last_closed_candle['obv'] > prev_candle['obv']
        obv_decreasing = last_closed_candle['obv'] < prev_candle['obv']

        # Điều kiện LONG: Đồng thuận MTF + 5m Tăng + OBV Tăng
        if mtf_bullish and trend_5m_bullish:
            ema_trend = "Tăng (Đồng thuận 5m,15m,1h,4h)"
            if last_closed_candle['low'] <= last_closed_candle['ema_21'] and last_closed_candle['close'] > last_closed_candle['ema_21']:
                if obv_increasing:
                    signal = "LONG"

        # Điều kiện SHORT: Đồng thuận MTF + 5m Giảm + OBV Giảm
        elif mtf_bearish and trend_5m_bearish:
            ema_trend = "Giảm (Đồng thuận 5m,15m,1h,4h)"
            if last_closed_candle['high'] >= last_closed_candle['ema_21'] and last_closed_candle['close'] < last_closed_candle['ema_21']:
                if obv_decreasing:
                    signal = "SHORT"
                    
        # --- BỘ LỌC AI (V4.0) ---
        if signal and self.model is not None:
            bb_range = last_closed_candle['bb_upper'] - last_closed_candle['bb_lower']
            bb_pos = (last_closed_candle['close'] - last_closed_candle['bb_lower']) / bb_range if bb_range != 0 else 0
            
            feature = [
                last_closed_candle['rsi'],
                last_closed_candle['macd'],
                last_closed_candle['macd_signal'],
                last_closed_candle['atr'] / last_closed_candle['close'],
                (last_closed_candle['close'] - last_closed_candle['ema_21']) / last_closed_candle['ema_21'],
                (last_closed_candle['ema_21'] - last_closed_candle['ema_50']) / last_closed_candle['ema_50'],
                last_closed_candle['obv_diff'] / last_closed_candle['volume'] if last_closed_candle['volume'] != 0 else 0,
                last_closed_candle['adx'],
                bb_pos,
                1 if trend_15m_bullish else 0,
                1 if trend_1h_bullish else 0,
                1 if trend_4h_bullish else 0
            ]
            feature_df = pd.DataFrame([feature], columns=['rsi', 'macd', 'macd_sig', 'atr_rel', 'dist_ema21', 'dist_emas', 'obv_rel', 'adx', 'bb_pos', 'trend_15m', 'trend_1h', 'trend_4h'])
            win_prob = self.model.predict_proba(feature_df)[0][1] # Xác suất Win (Class 1)
            
            ema_trend += f" | AI_Win_Prob: {win_prob*100:.1f}%"
            
            # Khắt khe: Nếu AI đánh giá tỷ lệ Win dưới 50% -> Hủy bỏ lệnh không báo lên Telegram!
            if win_prob < 0.50:
                print(f"🤖 AI Lọc Bỏ Lệnh: Xác suất Win chỉ {win_prob*100:.1f}%")
                signal = None

        # 3. Tính toán TP và SL nếu có tín hiệu
        if signal:
            entry_price = current_candle['close']
            atr_value = last_closed_candle['atr']
            
            # SL đặt cách 2.0 lần ATR, TP đặt cách 3.0 lần ATR (Risk:Reward ~ 1:1.5)
            if signal == "LONG":
                sl = entry_price - (2.0 * atr_value)
                tp = entry_price + (3.0 * atr_value)
            else: # SHORT
                sl = entry_price + (2.0 * atr_value)
                tp = entry_price - (3.0 * atr_value)

            return {
                "signal": signal,
                "entry": round(entry_price, 4),
                "tp": round(tp, 4),
                "sl": round(sl, 4),
                "rsi": last_closed_candle['rsi'],
                "ema_trend": ema_trend
            }

        return None
