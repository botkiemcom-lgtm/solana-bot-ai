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
                
        self.last_insight = "Chưa có dữ liệu phân tích"

    def analyze(self, df_5m, df_15m, df_30m, df_1h):
        """
        Nhận DataFrame nến 15m để săn Thiên Nga Đen.
        """
        if df_15m is None or len(df_15m) < self.ema_long:
            return None

        df = df_15m.copy()

        # 1. Các chỉ báo giá trên M15
        df['ema_9'] = ta.trend.ema_indicator(df['close'], window=self.ema_short)
        df['ema_21'] = ta.trend.ema_indicator(df['close'], window=self.ema_mid)
        df['ema_50'] = ta.trend.ema_indicator(df['close'], window=self.ema_long)
        df['rsi'] = ta.momentum.rsi(df['close'], window=self.rsi_period)
        
        # Động lượng Dòng tiền (OBV)
        df['obv'] = ta.volume.on_balance_volume(df['close'], df['volume'])
        df['obv_diff'] = df['obv'].diff()

        # ATR cho biến động giá (dùng cho SL và Trailing)
        atr_indicator = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=self.atr_period)
        df['atr'] = atr_indicator.average_true_range()

        # Lấy các cây nến
        last_closed_candle = df.iloc[-2]
        current_candle = df.iloc[-1]
        prev_candle = df.iloc[-3]

        # 2. Logic Trend & Dòng tiền
        signal = None
        ema_trend = "Không rõ ràng"

        trend_bullish = last_closed_candle['ema_9'] > last_closed_candle['ema_21'] > last_closed_candle['ema_50']
        trend_bearish = last_closed_candle['ema_9'] < last_closed_candle['ema_21'] < last_closed_candle['ema_50']
        
        obv_increasing = last_closed_candle['obv'] > prev_candle['obv']
        obv_decreasing = last_closed_candle['obv'] < prev_candle['obv']
        
        buffer = last_closed_candle['close'] * 0.0005

        # Điều kiện LONG: Trend Tăng + OBV Tăng + Pullback chạm EMA21
        if trend_bullish:
            if last_closed_candle['low'] <= last_closed_candle['ema_21'] + buffer and obv_increasing:
                self.last_insight = "Tín hiệu siêu đẹp! Khung M15 đang nén lò xo bứt phá!"
                signal = "LONG"
                ema_trend = "Tăng (M15)"
            else:
                self.last_insight = "Khung M15 Tăng, đang chờ Pullback hoặc tín hiệu dòng tiền."
                
        # Điều kiện SHORT: Trend Giảm + OBV Giảm + Pullback chạm EMA21
        elif trend_bearish:
            if last_closed_candle['high'] >= last_closed_candle['ema_21'] - buffer and obv_decreasing:
                self.last_insight = "Tín hiệu siêu đẹp! Khung M15 đang nén lò xo sập hầm!"
                signal = "SHORT"
                ema_trend = "Giảm (M15)"
            else:
                self.last_insight = "Khung M15 Giảm, đang chờ Pullback hoặc tín hiệu dòng tiền."
        else:
            self.last_insight = "Thị trường M15 Sideway, không có trend rõ ràng."
                    
        # --- BỘ LỌC AI (V4.0) ---
        if signal and self.model is not None:
            # (Phần này tạm thời bỏ qua tính toán rườm rà nếu không xài AI, nhưng cứ để lại nếu có model)
            pass

        # 3. Tính toán SL và Trailing Stop nếu có tín hiệu
        if signal:
            entry_price = current_candle['close']
            atr_value = last_closed_candle['atr']
            
            # SL đặt cách 2.0 lần ATR
            # Giá Kích Hoạt Trailing cách 2.0 lần ATR (Khóa lãi)
            # Tỷ Lệ Dời (Callback) cách 2.5 lần ATR
            callback_percent = round(((2.5 * atr_value) / entry_price) * 100, 1)
            
            if signal == "LONG":
                sl = entry_price - (2.0 * atr_value)
                activation_price = entry_price + (2.0 * atr_value)
            else: # SHORT
                sl = entry_price + (2.0 * atr_value)
                activation_price = entry_price - (2.0 * atr_value)

            return {
                "signal": signal,
                "entry": round(entry_price, 4),
                "sl": round(sl, 4),
                "activation_price": round(activation_price, 4),
                "callback_rate": callback_percent,
                "rsi": last_closed_candle['rsi'],
                "ema_trend": ema_trend
            }

        return None

    def monitor_trade(self, df_5m, df_15m, df_30m, df_1h, active_trade):
        """
        Theo dõi lệnh đang gồng để cảnh báo thoát sớm nếu AI thấy thị trường đảo chiều
        """
        if df_5m is None or len(df_5m) < self.ema_long or df_1h is None or len(df_1h) < 50 or df_15m is None or df_30m is None:
            return None

        # Tính EMA 5m
        df = df_5m.copy()
        df['ema_9'] = ta.trend.ema_indicator(df['close'], window=self.ema_short)
        df['ema_21'] = ta.trend.ema_indicator(df['close'], window=self.ema_mid)
        df['ema_50'] = ta.trend.ema_indicator(df['close'], window=self.ema_long)
        df['rsi'] = ta.momentum.rsi(df['close'], window=self.rsi_period)
        df['obv'] = ta.volume.on_balance_volume(df['close'], df['volume'])
        df['obv_diff'] = df['obv'].diff()
        
        macd = ta.trend.MACD(df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        
        atr_indicator = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=self.atr_period)
        df['atr'] = atr_indicator.average_true_range()
        
        adx_indicator = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
        df['adx'] = adx_indicator.adx()
        
        bb_indicator = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
        df['bb_upper'] = bb_indicator.bollinger_hband()
        df['bb_lower'] = bb_indicator.bollinger_lband()

        last_closed_candle = df.iloc[-2]
        
        # Đồng thuận khung lớn
        df_15m['ema_21'] = ta.trend.ema_indicator(df_15m['close'], window=21)
        df_15m['ema_50'] = ta.trend.ema_indicator(df_15m['close'], window=50)
        trend_15m_bullish = df_15m.iloc[-2]['ema_21'] > df_15m.iloc[-2]['ema_50']
        
        df_30m['ema_21'] = ta.trend.ema_indicator(df_30m['close'], window=21)
        df_30m['ema_50'] = ta.trend.ema_indicator(df_30m['close'], window=50)
        trend_30m_bullish = df_30m.iloc[-2]['ema_21'] > df_30m.iloc[-2]['ema_50']
        
        df_1h['ema_21'] = ta.trend.ema_indicator(df_1h['close'], window=21)
        df_1h['ema_50'] = ta.trend.ema_indicator(df_1h['close'], window=50)
        trend_1h_bullish = df_1h.iloc[-2]['ema_21'] > df_1h.iloc[-2]['ema_50']

        warning = None
        trade_type = active_trade.get("type")
        
        if self.model is not None:
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
                1 if trend_30m_bullish else 0,
                1 if trend_1h_bullish else 0
            ]
            feature_df = pd.DataFrame([feature], columns=['rsi', 'macd', 'macd_sig', 'atr_rel', 'dist_ema21', 'dist_emas', 'obv_rel', 'adx', 'bb_pos', 'trend_15m', 'trend_1h', 'trend_4h'])
            win_prob = self.model.predict_proba(feature_df)[0][1]
            
            # Phân tích Cảnh Báo (Đã fix lỗi hiểu nhầm win_prob của AI)
            is_bullish_trend = trend_15m_bullish and trend_30m_bullish and trend_1h_bullish
            is_bearish_trend = not trend_15m_bullish and not trend_30m_bullish and not trend_1h_bullish
            
            if trade_type == "LONG":
                # Kịch bản 1: Xu hướng đã ĐẢO CHIỀU sang Short và tỷ lệ thắng của Short đang cao
                if is_bearish_trend and win_prob > 0.60:
                    warning = f"⚠️ **CẢNH BÁO KHẨN CẤP TỪ AI (Lệnh LONG)**\n\nThị trường đã hoàn toàn ĐẢO CHIỀU sang xu hướng Giảm. Xác suất phe Short ăn tiền lúc này lên tới {win_prob*100:.1f}%. \n\n👉 **HÃY CẮT LỖ SỚM ĐỂ BẢO TOÀN VỐN!**"
                # Kịch bản 2: Vẫn là xu hướng Long nhưng AI đánh giá tỷ lệ thắng quá thấp (cạn lực)
                elif is_bullish_trend and win_prob < 0.30:
                    warning = f"⚠️ **CẢNH BÁO TỪ AI (Lệnh LONG)**\n\nXác suất thắng của phe Long vừa sụt giảm thê thảm xuống chỉ còn {win_prob*100:.1f}%. Lực đẩy đã cạn. \n\n👉 **CÂN NHẮC CHỐT LỜI HOẶC THOÁT HÀNG SỚM!**"
            
            elif trade_type == "SHORT":
                # Kịch bản 1: Xu hướng đã ĐẢO CHIỀU sang Long và tỷ lệ thắng của Long đang cao
                if is_bullish_trend and win_prob > 0.60:
                    warning = f"⚠️ **CẢNH BÁO KHẨN CẤP TỪ AI (Lệnh SHORT)**\n\nThị trường đã hoàn toàn ĐẢO CHIỀU sang xu hướng Tăng. Xác suất phe Long ăn tiền lúc này lên tới {win_prob*100:.1f}%. \n\n👉 **HÃY CẮT LỖ SỚM ĐỂ BẢO TOÀN VỐN!**"
                # Kịch bản 2: Vẫn là xu hướng Short nhưng AI đánh giá tỷ lệ thắng quá thấp (cạn lực xả)
                elif is_bearish_trend and win_prob < 0.30:
                    warning = f"⚠️ **CẢNH BÁO TỪ AI (Lệnh SHORT)**\n\nXác suất thắng của phe Short vừa sụt giảm thê thảm xuống chỉ còn {win_prob*100:.1f}%. Lực xả đã yếu dần. \n\n👉 **CÂN NHẮC CHỐT LỜI HOẶC THOÁT HÀNG SỚM!**"

        return warning
