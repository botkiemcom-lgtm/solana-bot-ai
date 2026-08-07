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
        Logic Bắt Sóng Lớn (Swing Trading) trên khung 15m.
        """
        if df_15m is None or len(df_15m) < 50 or df_btc_15m is None or len(df_btc_15m) < 50:
            return None

        # Đồng bộ thời gian để join
        df = df_15m.copy()
        df_btc = df_btc_15m.copy()

        # Tính toán chỉ báo SOL
        df['ema_21'] = ta.trend.ema_indicator(df['close'], window=self.ema_mid)
        df['ema_50'] = ta.trend.ema_indicator(df['close'], window=self.ema_long)
        df['rsi'] = ta.momentum.rsi(df['close'], window=self.rsi_period)
        
        atr_indicator = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=self.atr_period)
        df['atr'] = atr_indicator.average_true_range()
        df['adx'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)

        # Tính toán chỉ báo BTC
        df_btc['btc_ema_50'] = ta.trend.ema_indicator(df_btc['close'], window=50)

        # Gộp dữ liệu
        df = df.join(df_btc[['btc_ema_50']], how='left').dropna()
        if len(df) < 3: return None

        last_closed_candle = df.iloc[-2]
        prev_candle = df.iloc[-3]
        
        signal = None
        ema_trend = ""
        
        # 1. Bộ lọc La Bàn (Xu hướng tổng thể 30m)
        btc_uptrend = last_closed_candle['close_btc'] > last_closed_candle['btc_ema_50'] if 'close_btc' in df.columns else df_btc.loc[last_closed_candle.name]['close'] > last_closed_candle['btc_ema_50']
        btc_downtrend = last_closed_candle['close_btc'] < last_closed_candle['btc_ema_50'] if 'close_btc' in df.columns else df_btc.loc[last_closed_candle.name]['close'] < last_closed_candle['btc_ema_50']

        rsi_val = last_closed_candle['rsi']
        adx_val = last_closed_candle['adx']
        ema_50 = last_closed_candle['ema_50']
        prev_ema_50 = prev_candle['ema_50']
        
        # 2. ĐIỀU KIỆN CŨ: Cross-over EMA 50
        crossover_up = last_closed_candle['close'] > ema_50 and prev_candle['close'] <= prev_ema_50
        crossover_down = last_closed_candle['close'] < ema_50 and prev_candle['close'] >= prev_ema_50
        
        # KIỂM TRA BỘ LỌC SIDEWAY (ADX)
        if not pd.isna(adx_val) and adx_val < 15:
            self.last_insight = f"Thị trường đang đi ngang (ADX: {adx_val:.1f} < 15), Hủy lệnh để tránh Whipsaw!"
            return None
        
        # 3. MÀNG LỌC NẾN SIÊU GỌN (Body > 65%)
        candle_body = abs(last_closed_candle['close'] - last_closed_candle['open'])
        candle_range = last_closed_candle['high'] - last_closed_candle['low']
        is_strong_candle = False
        if candle_range > 0:
            is_strong_candle = (candle_body / candle_range) > 0.65
            
        is_green = last_closed_candle['close'] > last_closed_candle['open']
        is_red = last_closed_candle['close'] < last_closed_candle['open']

        # KẾT HỢP
        if btc_uptrend and crossover_up:
            if is_strong_candle and is_green:
                signal = "LONG"
                ema_trend = "BULLISH BREAKOUT: Nến Xanh cực mạnh đâm thủng EMA 50, La bàn BTC thuận chiều!"
            else:
                self.last_insight = "Phá vỡ EMA 50 lên nhưng Nến lực yếu (Doji/Whipsaw), Hủy lệnh!"
                return None
                
        elif btc_downtrend and crossover_down:
            if is_strong_candle and is_red:
                signal = "SHORT"
                ema_trend = "BEARISH BREAKOUT: Nến Đỏ xả mạnh đâm thủng EMA 50, La bàn BTC thuận chiều!"
            else:
                self.last_insight = "Phá vỡ EMA 50 xuống nhưng Nến lực yếu (Doji/Whipsaw), Hủy lệnh!"
                return None
        else:
            self.last_insight = f"Đang theo dõi chặt chẽ (RSI: {rsi_val:.1f})"
            return None
            
        self.last_insight = ema_trend

        # 4. Giá vào lệnh 1 Lệnh (Giá Market đóng nến)
        entry_price = last_closed_candle['close']
        atr_val = last_closed_candle['atr']
        
        # Gọi Hệ Thống AI Vệ Sĩ 2 Lớp để đánh giá Breakout
        ai_verdict = self.ask_ai_risk_manager(df, signal)
        
        is_rejected = False
        reject_reason = ""
        rejected_by = ""
        gemini_failed = ai_verdict.get("gemini_failed", False)
        
        # Mức rủi ro theo ML
        confidence = ai_verdict.get("confidence", 0)
        risk_level = "Rủi ro cao"
        risk_amount = 10.0
        
        if confidence >= 70 and adx_val >= 35:
            risk_level = 'Cực kỳ ngon'
            risk_amount = 15.0
        elif confidence >= 55 and adx_val >= 25:
            risk_level = 'Trung bình'
            risk_amount = 10.0
        else:
            risk_level = 'Rủi ro cao'
            risk_amount = 10.0
            
        sl_dist = 2.0 * atr_val
        
        if signal == "LONG":
            sl = entry_price - sl_dist
            tp1 = entry_price + sl_dist * 1.5 
            tp2 = entry_price + sl_dist * 3.0 
        else:
            sl = entry_price + sl_dist
            tp1 = entry_price - sl_dist * 1.5 
            tp2 = entry_price - sl_dist * 3.0 
            
        sl_pct = abs(entry_price - sl) / entry_price
        pos_usd = risk_amount / sl_pct if sl_pct > 0 else 0
        margin = pos_usd / 10 # 10x leverage
        
        if not ai_verdict.get('approved', False):
            # Bị AI gạch kèo
            reject_reason = ai_verdict.get('reason', 'Rủi ro cao')
            rejected_by = ai_verdict.get('rejected_by', 'Hệ Thống')
            self.last_insight = f"❌ {rejected_by} TỪ CHỐI: {reject_reason}"
            is_rejected = True
        else:
            # Nếu AI duyệt
            if gemini_failed:
                ema_trend = f"{ema_trend}\n⚠️ {ai_verdict.get('reason')}"
            else:
                ema_trend = f"{ema_trend}\n✅ CẢ 2 LỚP VỆ SĨ (ML & GEMINI) ĐỀU DUYỆT: {ai_verdict.get('reason', 'Đủ an toàn để giao dịch.')}"
            self.last_insight = ema_trend

        return {
            "signal": signal,
            "entry": f"{round(entry_price, 4)}",
            "tp1": f"{round(tp1, 4)}",
            "tp2": f"{round(tp2, 4)}",
            "margin": f"{round(margin, 2)}",
            "risk_level": risk_level,
            "sl": round(sl, 4),
            "rsi": round(rsi_val, 1),
            "ema_trend": ema_trend,
            "ai_rejected": is_rejected,
            "reject_reason": reject_reason,
            "rejected_by": rejected_by,
            "gemini_failed": gemini_failed
        }

    def monitor_trade(self, df_5m, df_15m, df_1h, df_btc_15m, active_trade):
        """
        Tạm thời tắt AI cảnh báo thoát sớm vì chúng ta đã dùng Trailing Stop của sàn Binance.
        Hàm này giữ nguyên cấu trúc để main.py không bị lỗi.
        """
        return None

    def ask_ai_risk_manager(self, df, current_signal):
        import os
        import pandas as pd
        import joblib
        import json
        import google.generativeai as genai
        
        # === LỚP BẢO VỆ 1: MACHINE LEARNING (XGBoost/Random Forest) ===
        try:
            model_path = 'market_regime_model_swing_15m.pkl'
            confidence = 0
            if os.path.exists(model_path):
                clf = joblib.load(model_path)
                
                # Tính toán Features cho nến hiện tại
                ema_21_slope = (df['ema_21'].iloc[-1] - df['ema_21'].iloc[-6]) / df['ema_21'].iloc[-6] * 100
                ema_50_slope = (df['ema_50'].iloc[-1] - df['ema_50'].iloc[-6]) / df['ema_50'].iloc[-6] * 100
                
                # Độ dốc 20 nến
                ema_21_slope_20 = (df['ema_21'].iloc[-1] - df['ema_21'].iloc[-21]) / df['ema_21'].iloc[-21] * 100
                ema_50_slope_20 = (df['ema_50'].iloc[-1] - df['ema_50'].iloc[-21]) / df['ema_50'].iloc[-21] * 100
                
                ema_dist = (df['ema_21'].iloc[-1] - df['ema_50'].iloc[-1]) / df['ema_50'].iloc[-1] * 100
                
                import ta
                bb = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
                bb_width = (bb.bollinger_hband().iloc[-1] - bb.bollinger_lband().iloc[-1]) / df['close'].iloc[-1] * 100
                atr_norm = df['atr'].iloc[-1] / df['close'].iloc[-1] * 100
                
                vol_ma20 = df['volume'].rolling(20).mean().iloc[-1]
                vol_ratio = df['volume'].iloc[-1] / vol_ma20 if vol_ma20 > 0 else 1.0
                rsi_val = df['rsi'].iloc[-1]
                adx_val = df['adx'].iloc[-1]
                
                X_new = pd.DataFrame([[ema_21_slope, ema_50_slope, ema_21_slope_20, ema_50_slope_20, ema_dist, bb_width, atr_norm, vol_ratio, rsi_val, adx_val]], 
                                     columns=['ema_21_slope', 'ema_50_slope', 'ema_21_slope_20', 'ema_50_slope_20', 'ema_dist', 'bb_width', 'atr_norm', 'vol_ratio', 'rsi', 'adx'])
                                     
                pred = clf.predict(X_new)[0]
                probs = clf.predict_proba(X_new)[0]
                confidence = probs[pred] * 100
                
                if pred == 0:
                    return {"approved": False, "rejected_by": "Vệ Sĩ Toán Học (ML)", "reason": "Biến động Sideway/Nhiễu loạn, không có xu hướng rõ ràng."}
                elif pred == 1 and current_signal == "SHORT":
                    return {"approved": False, "rejected_by": "Vệ Sĩ Toán Học (ML)", "reason": "Thị trường đang Uptrend, đánh SHORT ngược xu hướng rất nguy hiểm!"}
                elif pred == 2 and current_signal == "LONG":
                    return {"approved": False, "rejected_by": "Vệ Sĩ Toán Học (ML)", "reason": "Thị trường đang Downtrend, đánh LONG ngược xu hướng rất nguy hiểm!"}
        except Exception as e:
            print(f"Lỗi AI Machine Learning (Risk Manager): {e}")
            # Nếu ML lỗi thì vẫn đi tiếp tới Gemini
            
        # === LỚP BẢO VỆ 2: GEMINI LLM (Đọc nến) ===
        try:
            genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
            model = genai.GenerativeModel('gemini-flash-latest')
            
            recent_df = df.tail(20).copy()
            data_str = "Dữ liệu 20 nến 15m gần nhất (Mở, Cao, Thấp, Đóng, Volume, RSI, EMA50, ATR):\n"
            for index, row in recent_df.iterrows():
                rsi_v = row['rsi'] if 'rsi' in row and not pd.isna(row['rsi']) else 50.0
                ema_v = row['ema_50'] if 'ema_50' in row and not pd.isna(row['ema_50']) else row['close']
                atr_v = row['atr'] if 'atr' in row and not pd.isna(row['atr']) else 0.0
                data_str += f"- Close: {row['close']:.2f}, Vol: {row['volume']:.2f}, RSI: {rsi_v:.1f}, EMA50: {ema_v:.2f}, ATR: {atr_v:.2f}\n"
                
            prompt = f"""
            Đóng vai một Chuyên gia Quản trị Rủi ro (Risk Manager) khắt khe cho giao dịch Crypto.
            Hệ thống kỹ thuật vừa phát hiện tín hiệu: {current_signal} (Dự định Swing Trading giữ lệnh 12-24h).
            
            Dựa vào 20 cây nến gần nhất dưới đây, hãy đánh giá cấu trúc giá, động lượng (Momentum) và biến động (ATR, Vol).
            Thị trường đang có xu hướng (Trend) rõ ràng để gồng lãi 12-24 tiếng, hay đang nén đi ngang (Sideway Choppy)?
            Tín hiệu Breakout này có đáng tin cậy không, hay chỉ là bẫy Whipsaw quét Stoploss?
            
            BẮT BUỘC trả về ĐÚNG định dạng JSON như sau, không kèm bất kỳ văn bản nào khác:
            {{"approved": true_or_false, "reason": "Lý do ngắn gọn bằng tiếng Việt"}}
            
            {data_str}
            """
            
            response = model.generate_content(prompt)
            res_text = response.text.replace("```json", "").replace("```", "").strip()
            res_json = json.loads(res_text)
            
            if not res_json.get('approved', False):
                return {"approved": False, "rejected_by": "Vệ Sĩ Ngôn Ngữ (Gemini AI)", "reason": res_json.get('reason', 'Rủi ro cao'), "confidence": confidence}
            else:
                return {"approved": True, "reason": res_json.get('reason', 'Đủ an toàn để giao dịch'), "confidence": confidence}
                
        except Exception as e:
            print(f"Lỗi gọi Gemini API (Risk Manager): {e}")
            # TỰ ĐỘNG SINH TỒN: Vì ML đã duyệt ở trên rồi, nên nếu Gemini chết, ta vẫn cho phép giao dịch nhưng báo cờ gemini_failed
            return {
                "approved": True, 
                "reason": "Vệ sĩ Gemini mất kết nối, kèo được duyệt độc lập bởi Vệ sĩ ML.",
                "gemini_failed": True,
                "confidence": confidence,
                "error_detail": str(e)
            }
