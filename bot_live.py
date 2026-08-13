# ==========================================
# FILE DUY NHẤT: bot_live.py
# V7.1 - SCORE ENGINE / NO BTC FILTER / GEMINI OPTIONAL / 1-MIN LOOP
# ==========================================
import os
import sys
import time
import json
import logging
import datetime
import threading
import re
from logging.handlers import RotatingFileHandler
from http.server import BaseHTTPRequestHandler, HTTPServer

import ccxt
import pandas as pd
import numpy as np
import ta
import joblib
import requests
import schedule
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 1. CONFIG
# ==========================================
class Config:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    PORT = int(os.getenv("PORT", "8080"))

    chat_ids_str = os.getenv("TELEGRAM_CHAT_ID", "")
    TELEGRAM_CHAT_IDS = [x.strip() for x in chat_ids_str.split(",") if x.strip()]

    CALLMEBOT_BOSS_USER = os.getenv("CALLMEBOT_BOSS_USER", "@huyduong112233")
    CALLMEBOT_DEV_USER = os.getenv("CALLMEBOT_DEV_USER", "@LiiO61")
    DEV_CHAT_ID = os.getenv("DEV_CHAT_ID", "1763816685")

    # Score thresholds:
    # WATCH = cảnh báo setup đang hình thành
    # CONFIRMED = đủ mạnh để gửi kèo chính thức
    WATCH_SCORE = 55
    CONFIRMED_SCORE = 72

    # Gemini chỉ là Vệ Sĩ bổ sung.
    # Nếu Gemini chết -> Strategy + ML vẫn được phép phát tín hiệu.
    GEMINI_ENABLED = bool(GEMINI_API_KEY)

    # Scheduler: quét sau mốc phút 00 khoảng 2 giây để nến mới có thời gian đóng.
    SCHEDULE_SECOND = 2

    # Mapping mặc định của model cũ. Có thể override bằng .env nếu model được train
    # với thứ tự label khác. Không tự đoán mapping mới.
    ML_SIDEWAY_LABEL = int(os.getenv("ML_SIDEWAY_LABEL", "0"))
    ML_BULLISH_LABEL = int(os.getenv("ML_BULLISH_LABEL", "1"))
    ML_BEARISH_LABEL = int(os.getenv("ML_BEARISH_LABEL", "2"))

    SYSTEM_STATUS = {
        "status": "🟡 Đang khởi động...",
        "last_check": "Chưa có",
        "last_error": "Không có",
        "last_signal": "Chưa có",
        "market_insight": "Chưa có dữ liệu",
    }

    ACTIVE_USERS = {}
    status_lock = threading.Lock()
    users_lock = threading.Lock()

    @classmethod
    def init_users(cls):
        with cls.users_lock:
            for cid in cls.TELEGRAM_CHAT_IDS:
                cls.ACTIVE_USERS.setdefault(
                    str(cid),
                    {"in_position": False, "type": None}
                )


# ==========================================
# 2. LOGGER
# ==========================================
def setup_logger(name="BotTrade"):
    log = logging.getLogger(name)
    if log.hasHandlers():
        return log

    log.setLevel(logging.INFO)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)

    log_file = os.path.join(os.path.dirname(__file__), "bot.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )
    console.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    log.addHandler(console)
    log.addHandler(file_handler)
    return log


logger = setup_logger()


# ==========================================
# 3. DATA FETCHER
# ==========================================
class BinanceFetcher:
    def __init__(self):
        config = {"enableRateLimit": True}
        self.last_successful_exchange = "Đang tìm kiếm..."
        self.exchanges = [
            ccxt.binance(config),
            ccxt.binanceus(config),
            ccxt.okx(config),
            ccxt.mexc(config),
            ccxt.bybit(config),
        ]

    def fetch_ohlcv(self, symbol="SOL/USDT:USDT", timeframe="15m", limit=150):
        # Ưu tiên sàn đã thành công ở lần trước.
        if self.last_successful_exchange != "Đang tìm kiếm...":
            for i, ex in enumerate(self.exchanges):
                if ex.id.upper() == self.last_successful_exchange:
                    self.exchanges.insert(0, self.exchanges.pop(i))
                    break

        for exchange in self.exchanges:
            try:
                if exchange.id == "binance":
                    exchange.options["defaultType"] = "future"
                    fetch_symbol = symbol
                elif exchange.id == "binanceus":
                    exchange.options["defaultType"] = "spot"
                    fetch_symbol = symbol.replace(":USDT", "")
                else:
                    fetch_symbol = symbol if ":" in symbol else f"{symbol}:USDT"

                ohlcv = exchange.fetch_ohlcv(
                    fetch_symbol,
                    timeframe,
                    limit=limit
                )
                if not ohlcv:
                    continue

                df = pd.DataFrame(
                    ohlcv,
                    columns=[
                        "timestamp", "open", "high",
                        "low", "close", "volume"
                    ],
                )
                if df.empty:
                    continue

                df["timestamp"] = pd.to_datetime(
                    df["timestamp"], unit="ms", utc=False
                )
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

                df = df.dropna().reset_index(drop=True)
                if len(df) < 60:
                    continue

                # KHÔNG chỉnh +0.05 hoặc bất kỳ giá trị giả nào.
                self.last_successful_exchange = exchange.id.upper()
                return df

            except Exception as e:
                logger.warning(
                    f"Chuyển trạm: {exchange.id} lỗi API: {str(e)[:180]}"
                )

        logger.error("Tất cả sàn đều không lấy được dữ liệu.")
        return None


# ==========================================
# 4. STRATEGY ENGINE
#    - Không còn BTC filter
#    - EMA9/21/50
#    - RSI6/12/24
#    - ADX
#    - ATR
#    - Volume
#    - Market Structure
#    - Breakout / Retest
#    - Score 0-100
# ==========================================
class StrategyAnalyzer:
    def __init__(
        self,
        ema_fast=9,
        ema_mid=21,
        ema_long=50,
        atr_period=14,
    ):
        self.ema_fast = ema_fast
        self.ema_mid = ema_mid
        self.ema_long = ema_long
        self.atr_period = atr_period

        self.last_closed_evaluated = None
        self.last_watch_candle = None
        self.last_watch_direction = None
        self.last_insight = "Chưa có dữ liệu"
        self.last_watch = None

    # ---------- Indicators ----------
    def prepare(self, raw_df):
        df = raw_df.copy()

        df["ema_9"] = ta.trend.ema_indicator(
            df["close"], window=self.ema_fast
        )
        df["ema_21"] = ta.trend.ema_indicator(
            df["close"], window=self.ema_mid
        )
        df["ema_50"] = ta.trend.ema_indicator(
            df["close"], window=self.ema_long
        )

        df["rsi_6"] = ta.momentum.rsi(df["close"], window=6)
        df["rsi_12"] = ta.momentum.rsi(df["close"], window=12)
        df["rsi_24"] = ta.momentum.rsi(df["close"], window=24)

        df["atr"] = ta.volatility.AverageTrueRange(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=self.atr_period,
        ).average_true_range()

        df["adx"] = ta.trend.adx(
            df["high"],
            df["low"],
            df["close"],
            window=14,
        )

        macd = ta.trend.MACD(df["close"])
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_hist"] = macd.macd_diff()

        df["vol_ma20"] = df["volume"].rolling(20).mean()
        df["vol_ratio"] = (
            df["volume"] / df["vol_ma20"].replace(0, np.nan)
        )

        df["ema21_slope"] = (
            (df["ema_21"] - df["ema_21"].shift(3))
            / df["ema_21"].shift(3).replace(0, np.nan)
            * 100
        )

        df["ema50_slope"] = (
            (df["ema_50"] - df["ema_50"].shift(5))
            / df["ema_50"].shift(5).replace(0, np.nan)
            * 100
        )

        # Recent swing points.
        df["recent_high_8"] = df["high"].rolling(8).max().shift(1)
        df["recent_low_8"] = df["low"].rolling(8).min().shift(1)
        df["recent_high_20"] = df["high"].rolling(20).max().shift(1)
        df["recent_low_20"] = df["low"].rolling(20).min().shift(1)

        return df.dropna().copy()

    # ---------- Structure ----------
    def structure(self, df, idx):
        if idx < 12:
            return "NEUTRAL"

        cur = df.iloc[idx]
        prev = df.iloc[idx - 6:idx]

        recent_high = prev["high"].max()
        recent_low = prev["low"].min()

        older = df.iloc[max(0, idx - 12):idx - 6]
        if older.empty:
            return "NEUTRAL"

        old_high = older["high"].max()
        old_low = older["low"].min()

        if cur["close"] > recent_high and recent_low >= old_low:
            return "BULLISH_BREAKOUT"

        if cur["close"] < recent_low and recent_high <= old_high:
            return "BEARISH_BREAKOUT"

        if recent_high > old_high and recent_low > old_low:
            return "HH_HL"

        if recent_high < old_high and recent_low < old_low:
            return "LH_LL"

        if recent_low > old_low:
            return "HL"

        if recent_high < old_high:
            return "LH"

        return "NEUTRAL"

    # ---------- Score ----------
    def calculate_score(self, df, idx, direction):
        r = df.iloc[idx]
        score = 0
        reasons = []

        # 1) EMA alignment: 20 points
        if direction == "LONG":
            if r["ema_9"] > r["ema_21"]:
                score += 7
                reasons.append("EMA9>EMA21")
            if r["ema_21"] > r["ema_50"]:
                score += 8
                reasons.append("EMA21>EMA50")
            if r["close"] > r["ema_21"]:
                score += 5
                reasons.append("Giá>EMA21")
        else:
            if r["ema_9"] < r["ema_21"]:
                score += 7
                reasons.append("EMA9<EMA21")
            if r["ema_21"] < r["ema_50"]:
                score += 8
                reasons.append("EMA21<EMA50")
            if r["close"] < r["ema_21"]:
                score += 5
                reasons.append("Giá<EMA21")

        # 2) EMA slope: 10 points
        if direction == "LONG":
            if r["ema21_slope"] > 0:
                score += 6
                reasons.append("EMA21 dốc lên")
            if r["ema50_slope"] >= 0:
                score += 4
                reasons.append("EMA50 không dốc xuống")
        else:
            if r["ema21_slope"] < 0:
                score += 6
                reasons.append("EMA21 dốc xuống")
            if r["ema50_slope"] <= 0:
                score += 4
                reasons.append("EMA50 không dốc lên")

        # 3) RSI: 15 points
        if direction == "LONG":
            if r["rsi_12"] > 50:
                score += 7
                reasons.append("RSI12>50")
            if 52 <= r["rsi_24"] <= 68:
                score += 4
                reasons.append("RSI24 khỏe")
            if r["rsi_6"] > 55:
                score += 4
                reasons.append("RSI6 momentum")
        else:
            if r["rsi_12"] < 50:
                score += 7
                reasons.append("RSI12<50")
            if 32 <= r["rsi_24"] <= 48:
                score += 4
                reasons.append("RSI24 yếu")
            if r["rsi_6"] < 45:
                score += 4
                reasons.append("RSI6 momentum")

        # 4) ADX: 10 points
        if r["adx"] >= 20:
            score += 5
            reasons.append(f"ADX {r['adx']:.1f}")
        if r["adx"] >= 25:
            score += 5
            reasons.append("ADX trend mạnh")

        # 5) Volume: 10 points
        if r["vol_ratio"] >= 1.2:
            score += 5
            reasons.append(f"Volume {r['vol_ratio']:.1f}x")
        if r["vol_ratio"] >= 1.8:
            score += 5
            reasons.append("Volume spike")

        # 6) MACD: 5 points
        if direction == "LONG" and r["macd"] > r["macd_signal"]:
            score += 5
            reasons.append("MACD bullish")
        elif direction == "SHORT" and r["macd"] < r["macd_signal"]:
            score += 5
            reasons.append("MACD bearish")

        # 7) Structure: 20 points
        structure = self.structure(df, idx)
        if direction == "LONG":
            if structure == "BULLISH_BREAKOUT":
                score += 20
                reasons.append("Breakout bullish")
            elif structure == "HH_HL":
                score += 16
                reasons.append("HH/HL")
            elif structure == "HL":
                score += 10
                reasons.append("Higher Low")
        else:
            if structure == "BEARISH_BREAKOUT":
                score += 20
                reasons.append("Breakout bearish")
            elif structure == "LH_LL":
                score += 16
                reasons.append("LH/LL")
            elif structure == "LH":
                score += 10
                reasons.append("Lower High")

        # 8) Candle quality: 10 points
        candle_range = r["high"] - r["low"]
        body_ratio = (
            abs(r["close"] - r["open"]) / candle_range
            if candle_range > 0 else 0
        )

        if direction == "LONG" and r["close"] > r["open"] and body_ratio >= 0.45:
            score += 10
            reasons.append("Nến xanh có lực")
        elif direction == "SHORT" and r["close"] < r["open"] and body_ratio >= 0.45:
            score += 10
            reasons.append("Nến đỏ có lực")

        return min(int(score), 100), structure, reasons

    # ---------- Detect setup ----------
    def detect_direction(self, df, idx):
        r = df.iloc[idx]

        long_score, long_structure, long_reasons = self.calculate_score(
            df, idx, "LONG"
        )
        short_score, short_structure, short_reasons = self.calculate_score(
            df, idx, "SHORT"
        )

        if long_score == short_score:
            return None

        if long_score > short_score:
            return {
                "direction": "LONG",
                "score": long_score,
                "structure": long_structure,
                "reasons": long_reasons,
            }

        return {
            "direction": "SHORT",
            "score": short_score,
            "structure": short_structure,
            "reasons": short_reasons,
        }

    # ---------- ML guard ----------
    def ml_guard(self, df, idx, signal):
        """
        ML là lớp bảo vệ bổ sung.
        Nếu model không tồn tại/lỗi -> KHÔNG chặn Strategy.
        """
        model_path = "market_regime_model_swing_15m.pkl"
        if not os.path.exists(model_path):
            return {
                "approved": True,
                "confidence": 0,
                "available": False,
                "reason": "Không có ML model -> bỏ qua lớp ML",
            }

        try:
            clf = joblib.load(model_path)
            r = df.iloc[idx]

            close = r["close"] if r["close"] > 0 else 1
            ema50 = r["ema_50"] if r["ema_50"] > 0 else 1

            bb = ta.volatility.BollingerBands(
                close=df["close"], window=20, window_dev=2
            )

            # Giữ đúng 10 feature của model cũ.
            row = [[
                ((r["ema_21"] - df["ema_21"].iloc[idx - 5])
                 / max(df["ema_21"].iloc[idx - 5], 1e-9)) * 100,
                ((r["ema_50"] - df["ema_50"].iloc[idx - 5])
                 / max(df["ema_50"].iloc[idx - 5], 1e-9)) * 100,
                ((r["ema_21"] - df["ema_21"].iloc[idx - 20])
                 / max(df["ema_21"].iloc[idx - 20], 1e-9)) * 100,
                ((r["ema_50"] - df["ema_50"].iloc[idx - 20])
                 / max(df["ema_50"].iloc[idx - 20], 1e-9)) * 100,
                ((r["ema_21"] - r["ema_50"]) / ema50) * 100,
                ((bb.bollinger_hband().iloc[idx]
                  - bb.bollinger_lband().iloc[idx]) / close) * 100,
                (r["atr"] / close) * 100,
                r["vol_ratio"],
                r["rsi_12"],
                r["adx"],
            ]]

            columns = [
                "ema_21_slope",
                "ema_50_slope",
                "ema_21_slope_20",
                "ema_50_slope_20",
                "ema_dist",
                "bb_width",
                "atr_norm",
                "vol_ratio",
                "rsi",
                "adx",
            ]

            X = pd.DataFrame(row, columns=columns)
            pred = clf.predict(X)[0]

            confidence = 0.0
            if hasattr(clf, "predict_proba"):
                proba = clf.predict_proba(X)[0]
                classes = list(getattr(clf, "classes_", range(len(proba))))
                if pred in classes:
                    confidence = float(
                        proba[classes.index(pred)] * 100
                    )

            # Mapping label mặc định của model cũ; có thể cấu hình bằng .env.
            if pred == Config.ML_SIDEWAY_LABEL:
                return {
                    "approved": False,
                    "confidence": confidence,
                    "available": True,
                    "reason": "ML nhận diện Sideway/Nhiễu",
                }

            if pred == Config.ML_BULLISH_LABEL and signal == "SHORT":
                return {
                    "approved": False,
                    "confidence": confidence,
                    "available": True,
                    "reason": "ML nghiêng Uptrend, chống SHORT",
                }

            if pred == Config.ML_BEARISH_LABEL and signal == "LONG":
                return {
                    "approved": False,
                    "confidence": confidence,
                    "available": True,
                    "reason": "ML nghiêng Downtrend, chống LONG",
                }

            # Confidence quá thấp chỉ giảm chất lượng, không tự động giết setup.
            return {
                "approved": True,
                "confidence": confidence,
                "available": True,
                "reason": f"ML OK ({confidence:.1f}%)",
            }

        except Exception as e:
            logger.warning(f"ML lỗi -> bỏ qua ML: {str(e)[:160]}")
            return {
                "approved": True,
                "confidence": 0,
                "available": False,
                "reason": "ML lỗi -> Strategy tiếp tục",
            }

    # ---------- Gemini guard ----------
    def gemini_guard(self, df, idx, signal, score, structure, reasons):
        if not Config.GEMINI_ENABLED:
            return {
                "approved": True,
                "failed": True,
                "reason": "Gemini OFFLINE/không cấu hình -> Strategy + ML vẫn hoạt động",
            }

        try:
            r = df.iloc[idx]
            prompt = f"""
Bạn là lớp VỆ SĨ cho bot trade SOLUSDT Futures.
Không tự tạo tín hiệu mới. Chỉ đánh giá rủi ro của setup đã được Strategy Engine phát hiện.

Khung: 15m
Signal: {signal}
Score Strategy: {score}/100
Structure: {structure}
Giá đóng: {r['close']:.4f}

EMA9: {r['ema_9']:.4f}
EMA21: {r['ema_21']:.4f}
EMA50: {r['ema_50']:.4f}
RSI6: {r['rsi_6']:.1f}
RSI12: {r['rsi_12']:.1f}
RSI24: {r['rsi_24']:.1f}
ADX: {r['adx']:.1f}
ATR: {r['atr']:.5f}
Volume ratio: {r['vol_ratio']:.2f}x
MACD hist: {r['macd_hist']:.6f}

Các yếu tố Strategy:
{", ".join(reasons[:14])}

Chỉ CHẶN nếu có rủi ro rõ ràng như:
- tín hiệu mâu thuẫn mạnh,
- breakout giả rất dễ thấy,
- biến động bất thường,
- setup đang quá đuổi giá.

Nếu setup hợp lý, APPROVE.

Trả về JSON duy nhất:
{{
  "approved": true,
  "confidence": 0-100,
  "reason": "ngắn gọn"
}}
"""
            genai.configure(api_key=Config.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash-latest")
            text = model.generate_content(prompt).text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)

            approved = bool(result.get("approved", True))
            confidence = float(result.get("confidence", 0))
            reason = str(result.get("reason", "Gemini không nêu lý do"))

            return {
                "approved": approved,
                "failed": False,
                "confidence": confidence,
                "reason": reason,
            }

        except Exception as e:
            logger.warning(
                f"⚠️ Gemini lỗi/offline -> không chặn Strategy: {str(e)[:160]}"
            )
            return {
                "approved": True,
                "failed": True,
                "reason": "AI: OFFLINE — Strategy + ML vẫn được phép phát tín hiệu",
            }

    # ---------- Main closed-candle analysis ----------
    def analyze(self, df_15m):
        try:
            if df_15m is None or len(df_15m) < 80:
                return None

            df = self.prepare(df_15m)
            if len(df) < 30:
                return None

            # [-1] = nến đang chạy, [-2] = nến đã đóng.
            idx = len(df) - 2
            last_closed = df.iloc[idx]

            # Mỗi nến 15m chỉ đánh giá một lần.
            if self.last_closed_evaluated == last_closed["timestamp"]:
                return None

            self.last_closed_evaluated = last_closed["timestamp"]

            detected = self.detect_direction(df, idx)
            if not detected:
                self.last_insight = "Không có hướng rõ ràng"
                return None

            signal = detected["direction"]
            score = detected["score"]
            structure = detected["structure"]
            reasons = detected["reasons"]

            # Score thấp -> không gửi kèo.
            if score < Config.CONFIRMED_SCORE:
                self.last_insight = (
                    f"🟡 {signal} đang hình thành | "
                    f"Score {score}/100 | {structure}"
                )
                return None

            # ML chỉ là guard bổ sung.
            ml = self.ml_guard(df, idx, signal)
            if not ml["approved"]:
                self.last_insight = (
                    f"🛡️ ML chặn {signal}: {ml['reason']}"
                )
                return {
                    "signal": signal,
                    "kind": "REJECTED",
                    "score": score,
                    "entry": f"{last_closed['close']:.4f}",
                    "reason": ml["reason"],
                    "ml_confidence": ml["confidence"],
                    "gemini_failed": False,
                }

            # Gemini chết không được làm bot câm.
            gemini = self.gemini_guard(
                df, idx, signal, score, structure, reasons
            )

            if not gemini["approved"]:
                self.last_insight = (
                    f"🛡️ Gemini chặn {signal}: {gemini['reason']}"
                )
                return {
                    "signal": signal,
                    "kind": "REJECTED",
                    "score": score,
                    "entry": f"{last_closed['close']:.4f}",
                    "reason": gemini["reason"],
                    "ml_confidence": ml["confidence"],
                    "gemini_failed": False,
                }

            entry = float(last_closed["close"])
            atr = float(last_closed["atr"])

            # SL = 1.8 ATR; TP = 1.5R / 3R.
            sl_dist = max(1.8 * atr, entry * 0.003)

            if signal == "LONG":
                sl = entry - sl_dist
                tp1 = entry + sl_dist * 1.5
                tp2 = entry + sl_dist * 3.0
            else:
                sl = entry + sl_dist
                tp1 = entry - sl_dist * 1.5
                tp2 = entry - sl_dist * 3.0

            sl_pct = sl_dist / entry
            # ML confidence thấp không giết setup, nhưng hạ cấp độ rủi ro.
            ml_low_conf = (
                ml.get("available", False)
                and ml.get("confidence", 0) < 45
            )

            if ml_low_conf:
                risk_amount = 10.0
                risk_level = "Hạng 3 (ML confidence thấp)"
            elif score >= 85:
                risk_amount = 15.0
                risk_level = "Hạng 1"
            elif score >= 78:
                risk_amount = 13.0
                risk_level = "Hạng 2"
            else:
                risk_amount = 10.0
                risk_level = "Hạng 3"

            margin = (risk_amount / sl_pct) / 10 if sl_pct > 0 else 0

            ai_text = (
                "AI: OFFLINE — Strategy + ML vẫn được phép phát tín hiệu"
                if gemini["failed"]
                else f"AI: {gemini['reason']}"
            )

            self.last_insight = (
                f"🟢 {signal} CONFIRMED | "
                f"Score {score}/100 | {structure}"
            )

            return {
                "signal": signal,
                "kind": "CONFIRMED",
                "score": score,
                "entry": f"{entry:.4f}",
                "sl": f"{sl:.4f}",
                "tp1": f"{tp1:.4f}",
                "tp2": f"{tp2:.4f}",
                "margin": f"{margin:.2f}",
                "risk_level": risk_level,
                "rsi": f"{last_closed['rsi_12']:.1f}",
                "adx": f"{last_closed['adx']:.1f}",
                "volume_ratio": f"{last_closed['vol_ratio']:.2f}",
                "structure": structure,
                "score_reasons": reasons[:10],
                "ema_trend": ai_text,
                "ai_rejected": False,
                "reject_reason": "",
                "rejected_by": "",
                "gemini_failed": gemini["failed"],
                "ml_confidence": ml["confidence"],
                "candle_time": str(last_closed["timestamp"]),
            }

        except Exception as e:
            logger.exception(f"Lỗi Strategy: {e}")
            return None

    # ---------- Live watch ----------
    def live_watch(self, df_15m):
        """
        Đọc nến đang chạy nhưng KHÔNG dùng để xác nhận entry.
        Mục tiêu: để bot không 'im ru' khi setup đang hình thành.
        """
        try:
            if df_15m is None or len(df_15m) < 80:
                return None

            df = self.prepare(df_15m)
            idx = len(df) - 1
            current = df.iloc[idx]

            detected = self.detect_direction(df, idx)
            if not detected:
                return None

            score = detected["score"]
            direction = detected["direction"]

            if score < Config.WATCH_SCORE:
                return None

            candle_time = current["timestamp"]

            # Không spam cùng một hướng trong cùng một nến.
            if (
                self.last_watch_candle == candle_time
                and self.last_watch_direction == direction
            ):
                return None

            self.last_watch_candle = candle_time
            self.last_watch_direction = direction

            self.last_watch = {
                "signal": direction,
                "kind": "WATCH",
                "score": score,
                "entry": f"{current['close']:.4f}",
                "ema21": f"{current['ema_21']:.4f}",
                "ema50": f"{current['ema_50']:.4f}",
                "rsi6": f"{current['rsi_6']:.1f}",
                "rsi12": f"{current['rsi_12']:.1f}",
                "adx": f"{current['adx']:.1f}",
                "volume_ratio": f"{current['vol_ratio']:.2f}",
                "structure": detected["structure"],
                "score_reasons": detected["reasons"][:8],
                "candle_time": str(candle_time),
            }

            return self.last_watch

        except Exception as e:
            logger.warning(f"Live watch lỗi: {e}")
            return None

    # ---------- Trade protector ----------
    def monitor_trade(self, df_15m, active_trade):
        try:
            trade_type = active_trade.get("type")
            entry_time = active_trade.get("entry_time")
            entry_price = active_trade.get("entry_price")
            sl = active_trade.get("sl")

            if (
                not trade_type
                or not entry_time
                or not entry_price
                or df_15m is None
                or df_15m.empty
            ):
                return None

            df = self.prepare(df_15m)
            if len(df) < 30:
                return None

            last = df.iloc[-2]
            cur_price = float(last["close"])

            pnl = (
                (cur_price - entry_price) / entry_price * 100
                if trade_type == "LONG"
                else (entry_price - cur_price) / entry_price * 100
            )

            elapsed = (
                datetime.datetime.utcnow() - entry_time
            ).total_seconds() / 60

            is_stuck = elapsed >= 90

            body = abs(last["close"] - last["open"])
            candle_range = last["high"] - last["low"]
            strong_body = (
                body / candle_range > 0.60
                if candle_range > 0 else False
            )
            vol_spike = last["vol_ratio"] >= 2.0

            is_reversal = False
            is_bleeding = False

            if len(df) >= 4:
                l3 = df.tail(4).head(3)

                if trade_type == "LONG":
                    if (
                        (l3["close"] < l3["open"]).all()
                        and (l3.iloc[0]["open"] - l3.iloc[-1]["close"])
                        / l3.iloc[0]["open"] * 100 > 1.2
                    ):
                        is_bleeding = True

                    if (
                        last["close"] < last["open"]
                        and strong_body
                        and vol_spike
                        and last["close"] < last["ema_21"]
                    ):
                        is_reversal = True

                else:
                    if (
                        (l3["close"] > l3["open"]).all()
                        and (l3.iloc[-1]["close"] - l3.iloc[0]["open"])
                        / l3.iloc[0]["open"] * 100 > 1.2
                    ):
                        is_bleeding = True

                    if (
                        last["close"] > last["open"]
                        and strong_body
                        and vol_spike
                        and last["close"] > last["ema_21"]
                    ):
                        is_reversal = True

            # SL thực tế chỉ là cảnh báo; user vẫn là người đóng lệnh.
            sl_hit = False
            if sl:
                sl_hit = (
                    cur_price <= sl
                    if trade_type == "LONG"
                    else cur_price >= sl
                )

            if not (is_stuck or is_reversal or is_bleeding or sl_hit):
                return None

            reason = (
                "GIÁ CHẠM SL"
                if sl_hit else
                "XẢ NGƯỢC BẠO LỰC"
                if is_reversal else
                "CƯA CHÂN BÀN"
                if is_bleeding else
                "NGÂM LỆNH > 90 PHÚT"
            )

            # Gemini chỉ đánh giá khi có cảnh báo.
            if Config.GEMINI_ENABLED:
                try:
                    genai.configure(api_key=Config.GEMINI_API_KEY)
                    prompt = f"""
Đang bảo vệ lệnh {trade_type} SOLUSDT Futures.
Entry: {entry_price}
SL: {sl}
Giá hiện tại: {cur_price}
PnL: {pnl:.2f}%
Thời gian: {elapsed:.0f} phút
Cảnh báo kỹ thuật: {reason}

EMA21: {last['ema_21']:.4f}
EMA50: {last['ema_50']:.4f}
RSI12: {last['rsi_12']:.1f}
ADX: {last['adx']:.1f}
Volume ratio: {last['vol_ratio']:.2f}

Chỉ trả JSON:
{{"close_trade_now": true/false, "reason": "ngắn gọn"}}
"""
                    text = genai.GenerativeModel(
                        "gemini-1.5-flash-latest"
                    ).generate_content(prompt).text
                    text = text.replace("```json", "").replace("```", "").strip()
                    res = json.loads(text)

                    if res.get("close_trade_now", False):
                        return (
                            "🚨 **VỆ SĨ CẢNH BÁO**\n"
                            f"⚠️ {reason}\n"
                            f"📊 PnL: `{pnl:.2f}%`\n"
                            f"🤖 {res.get('reason', 'Rủi ro tăng')}\n"
                            "👉 **Cân nhắc thoát lệnh ngay.**"
                        )
                    return None

                except Exception:
                    # Gemini chết trong lúc bảo vệ -> vẫn cảnh báo kỹ thuật.
                    pass

            return (
                "⚠️ **VỆ SĨ KỸ THUẬT CẢNH BÁO**\n"
                f"🚨 {reason}\n"
                f"📊 PnL: `{pnl:.2f}%`\n"
                f"💰 Giá: `{cur_price:.4f}`\n"
                "👉 Kiểm tra lệnh và cân nhắc xử lý."
            )

        except Exception:
            return None


# ==========================================
# 5. TELEGRAM
# ==========================================
class TelegramNotifier:
    def __init__(self):
        self.token = Config.TELEGRAM_BOT_TOKEN
        self.chat_ids = Config.TELEGRAM_CHAT_IDS
        Config.init_users()

        self.api_url = (
            f"https://api.telegram.org/bot{self.token}/sendMessage"
        )
        self.get_updates_url = (
            f"https://api.telegram.org/bot{self.token}/getUpdates"
        )
        self.edit_message_url = (
            f"https://api.telegram.org/bot{self.token}/editMessageText"
        )
        self.answer_callback_url = (
            f"https://api.telegram.org/bot{self.token}/answerCallbackQuery"
        )
        self.last_update_id = None

    def setup_commands(self):
        if not self.token:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.token}/setMyCommands",
                json={
                    "commands": [
                        {"command": "ping", "description": "Ping"},
                        {"command": "status", "description": "Status"},
                    ]
                },
                timeout=10,
            )
        except Exception:
            pass

    def send_watch(self, chat_id, data):
        if not self.token:
            return

        signal = data["signal"]
        icon = "🟡 LONG WATCH" if signal == "LONG" else "🟠 SHORT WATCH"

        msg = (
            f"👀 **SETUP ĐANG HÌNH THÀNH**\n"
            f"Cặp: SOL/USDT\n"
            f"Tín hiệu: **{icon}**\n\n"
            f"📊 Score: `{data['score']}/100`\n"
            f"🎯 Giá hiện tại: `{data['entry']}`\n"
            f"EMA21: `{data['ema21']}`\n"
            f"EMA50: `{data['ema50']}`\n"
            f"RSI6: `{data['rsi6']}` | RSI12: `{data['rsi12']}`\n"
            f"ADX: `{data['adx']}`\n"
            f"Volume: `{data['volume_ratio']}x`\n"
            f"Structure: `{data['structure']}`\n\n"
            f"🧠 {', '.join(data['score_reasons'])}\n\n"
            f"⚠️ **Chưa phải lệnh vào. Chờ nến 15m đóng xác nhận.**"
        )

        try:
            requests.post(
                self.api_url,
                json={
                    "chat_id": chat_id,
                    "text": msg,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
        except Exception:
            pass

    def send_signal(self, chat_id, symbol, data, exchange_name="BINANCE"):
        if not self.token:
            return

        signal = data.get("signal", "UNKNOWN")
        kind = data.get("kind")

        if kind == "REJECTED":
            msg = (
                "🛡️ **VỆ SĨ CHẶN KÈO**\n"
                f"Cặp: {symbol}\n"
                f"Tín hiệu: `{signal}`\n"
                f"Score: `{data.get('score', 0)}/100`\n"
                f"❌ Lý do: {data.get('reason', '')}"
            )
            self.send_message(chat_id, msg)
            return

        icon = "🟢 LONG" if signal == "LONG" else "🔴 SHORT"

        ai_line = data.get("ema_trend", "")
        msg = (
            "🦅 **PHÁT HIỆN KÈO SWING 15M** 🦅\n"
            f"Cặp: {symbol}\n"
            f"Tín hiệu: **{icon}**\n\n"
            f"📊 Score: `{data.get('score')}/100`\n"
            f"🎯 Entry: `{data.get('entry')}`\n"
            f"🛡️ SL: `{data.get('sl')}`\n"
            f"💰 TP1: `{data.get('tp1')}`\n"
            f"🚀 TP2: `{data.get('tp2')}`\n"
            f"⚖️ Risk: `{data.get('risk_level')}`\n"
            f"💵 Margin tham khảo: `{data.get('margin')} USD`\n\n"
            f"📐 Structure: `{data.get('structure')}`\n"
            f"RSI12: `{data.get('rsi')}` | ADX: `{data.get('adx')}`\n"
            f"Volume: `{data.get('volume_ratio')}x`\n\n"
            f"🤖 {ai_line}\n\n"
            f"🧠 {', '.join(data.get('score_reasons', []))}"
        )

        markup = {
            "inline_keyboard": [[
                {
                    "text": "✅ Đã vào lệnh (Bật Vệ Sĩ)",
                    "callback_data": f"ENTERED_{signal}",
                }
            ]]
        }

        try:
            response = requests.post(
                self.api_url,
                json={
                    "chat_id": chat_id,
                    "text": msg,
                    "parse_mode": "Markdown",
                    "reply_markup": markup,
                },
                timeout=10,
            )

            if response.status_code == 200:
                self.make_call(chat_id, symbol, signal)

        except Exception as e:
            logger.error(f"Lỗi gửi Telegram: {e}")

    def make_call(self, chat_id, symbol, signal):
        vn_time = datetime.datetime.utcnow() + datetime.timedelta(hours=7)

        if str(chat_id) == Config.DEV_CHAT_ID:
            username = Config.CALLMEBOT_DEV_USER
            greeting = "Dev ơi"
            limited = False
        else:
            username = Config.CALLMEBOT_BOSS_USER
            greeting = "Sếp ơi"
            limited = True

        if limited and (vn_time.hour >= 23 or vn_time.hour < 6):
            return

        url = (
            "https://api.callmebot.com/start.php"
            f"?user={username}"
            f"&text={greeting},+có+kèo+{signal}+{symbol.replace('/', '+')}"
            "&lang=vi-VN-Standard-A&rpt=2"
        )

        try:
            requests.get(url, timeout=10)
        except Exception:
            pass

    def send_message(self, chat_id, text, reply_markup=None):
        if not self.token:
            return

        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            requests.post(self.api_url, json=payload, timeout=10)
        except Exception:
            pass

    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        if not self.token:
            return

        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        try:
            requests.post(
                self.edit_message_url,
                json=payload,
                timeout=10
            )
        except Exception:
            pass

    def answer_callback(self, callback_id, text):
        try:
            requests.post(
                self.answer_callback_url,
                json={
                    "callback_query_id": callback_id,
                    "text": text
                },
                timeout=10,
            )
        except Exception:
            pass

    def check_commands(self):
        if not self.token or not self.chat_ids:
            return

        params = {"timeout": 1}
        if self.last_update_id is not None:
            params["offset"] = self.last_update_id + 1

        try:
            res = requests.get(
                self.get_updates_url,
                params=params,
                timeout=10
            ).json()

            if not res.get("ok"):
                return

            for item in res.get("result", []):
                self.last_update_id = item["update_id"]

                if "callback_query" in item:
                    cb = item["callback_query"]
                    data = cb.get("data", "")
                    msg = cb.get("message", {})
                    original_text = msg.get("text", "")
                    chat_id = msg.get("chat", {}).get("id")
                    msg_id = msg.get("message_id")

                    if str(chat_id) not in self.chat_ids:
                        self.answer_callback(
                            cb["id"],
                            "Không có quyền thao tác!"
                        )
                        continue

                    if data.startswith("ENTERED_"):
                        trade_type = data.split("_", 1)[1]

                        m_entry = re.search(
                            r"Entry:\s*`?([\d.]+)",
                            original_text
                        )
                        m_sl = re.search(
                            r"SL:\s*`?([\d.]+)",
                            original_text
                        )

                        entry_price = (
                            float(m_entry.group(1))
                            if m_entry else None
                        )
                        sl = float(m_sl.group(1)) if m_sl else None

                        with Config.users_lock:
                            Config.ACTIVE_USERS[str(chat_id)] = {
                                **Config.ACTIVE_USERS.get(str(chat_id), {}),
                                "in_position": True,
                                "type": trade_type,
                                "entry_time": datetime.datetime.utcnow(),
                                "entry_price": entry_price,
                                "sl": sl,
                            }

                        self.edit_message(
                            chat_id,
                            msg_id,
                            original_text
                            + f"\n\n🛡️ **ĐANG BẢO VỆ ({trade_type})**",
                            {
                                "inline_keyboard": [[
                                    {
                                        "text": "🛑 Dừng lệnh",
                                        "callback_data": "STOP_TRADE",
                                    }
                                ]]
                            },
                        )
                        self.answer_callback(
                            cb["id"],
                            f"Đã bật Vệ Sĩ {trade_type}!"
                        )

                    elif data == "STOP_TRADE":
                        with Config.users_lock:
                            if str(chat_id) in Config.ACTIVE_USERS:
                                Config.ACTIVE_USERS[str(chat_id)].update({
                                    "in_position": False,
                                    "type": None,
                                    "entry_time": None,
                                    "entry_price": None,
                                    "sl": None,
                                })

                        self.edit_message(
                            chat_id,
                            msg_id,
                            original_text.split("🛡️")[0]
                            + "\n✅ **LỆNH KẾT THÚC**",
                            {}
                        )
                        self.answer_callback(
                            cb["id"],
                            "Đã tắt Vệ Sĩ!"
                        )

                    continue

                text = item.get("message", {}).get("text", "")
                chat_id = item.get("message", {}).get("chat", {}).get("id")

                if str(chat_id) not in self.chat_ids:
                    continue

                if text == "/ping":
                    self.send_message(chat_id, "🏓 Pong! Bot V7.1 Live!")

                elif text == "/status":
                    with Config.users_lock:
                        mode = (
                            "🛡️ ĐANG BẢO VỆ"
                            if Config.ACTIVE_USERS.get(
                                str(chat_id), {}
                            ).get("in_position")
                            else "⚔️ ĐANG SĂN MỒI"
                        )

                    with Config.status_lock:
                        st = dict(Config.SYSTEM_STATUS)

                    self.send_message(
                        chat_id,
                        f"📊 **BÁO CÁO BOT**\n"
                        f"🔹 Chế độ: {mode}\n"
                        f"🔹 Tình trạng: {st['status']}\n"
                        f"🕒 Lần quét: {st['last_check']}\n"
                        f"🔥 Tín hiệu: {st['last_signal']}\n"
                        f"🧠 Insight: {st['market_insight']}"
                    )

        except Exception as e:
            logger.warning(f"Telegram polling lỗi: {e}")


# ==========================================
# 6. KEEP ALIVE
# ==========================================
class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


def keep_alive():
    try:
        HTTPServer(("0.0.0.0", Config.PORT), DummyServer).serve_forever()
    except Exception:
        pass


# ==========================================
# 7. GLOBAL OBJECTS
# ==========================================
FETCHER = BinanceFetcher()
ANALYZER = StrategyAnalyzer()
NOTIFIER = TelegramNotifier()


# ==========================================
# 8. MAIN JOB
# ==========================================
def run_bot_job():
    try:
        now_vn = (
            datetime.datetime.utcnow()
            + datetime.timedelta(hours=7)
        ).strftime("%Y-%m-%d %H:%M:%S")

        logger.info("👀 Quét SOL/USDT 15m...")

        with Config.status_lock:
            Config.SYSTEM_STATUS["last_check"] = now_vn

        # V7.1 chỉ fetch 15m vì Strategy/Live Watch hiện dùng 15m.
        # 5m + 1h sẽ được bổ sung khi có module MTF thực sự sử dụng chúng.
        df_15m = FETCHER.fetch_ohlcv(
            "SOL/USDT:USDT", "15m", 150
        )

        if df_15m is None:
            with Config.status_lock:
                Config.SYSTEM_STATUS["status"] = "🔴 Lỗi lấy dữ liệu SOL"
            return

        with Config.status_lock:
            Config.SYSTEM_STATUS["status"] = (
                f"🟢 Live | Nguồn: {FETCHER.last_successful_exchange}"
            )

        # Snapshot users để tránh giữ lock trong lúc gọi API.
        with Config.users_lock:
            active_users = {
                k: dict(v)
                for k, v in Config.ACTIVE_USERS.items()
            }

        # 1) Vệ sĩ cho lệnh đang chạy.
        for chat_id, user_state in active_users.items():
            if user_state.get("in_position"):
                warning = ANALYZER.monitor_trade(
                    df_15m,
                    user_state
                )
                if warning:
                    # Không spam cùng một cảnh báo mỗi phút. Cooldown 15 phút/user.
                    warning_key = warning.split("\n", 2)[1] if "\n" in warning else warning[:80]
                    now_utc = datetime.datetime.utcnow()
                    last_warning_at = user_state.get("last_guard_warning_at")
                    last_warning_key = user_state.get("last_guard_warning_key")
                    suppress = (
                        last_warning_key == warning_key
                        and isinstance(last_warning_at, datetime.datetime)
                        and (now_utc - last_warning_at).total_seconds() < 900
                    )
                    if suppress:
                        warning = None
                    else:
                        with Config.users_lock:
                            if str(chat_id) in Config.ACTIVE_USERS:
                                Config.ACTIVE_USERS[str(chat_id)]["last_guard_warning_key"] = warning_key
                                Config.ACTIVE_USERS[str(chat_id)]["last_guard_warning_at"] = now_utc

                if warning:
                    NOTIFIER.send_message(
                        chat_id,
                        warning,
                        {
                            "inline_keyboard": [[
                                {
                                    "text": "🛑 Dừng lệnh",
                                    "callback_data": "STOP_TRADE",
                                }
                            ]]
                        },
                    )

        # 2) Không có lệnh -> live watch + confirmed setup.
        no_position_users = [
            cid for cid, state in active_users.items()
            if not state.get("in_position")
        ]

        if no_position_users:
            # Live candle: cảnh báo sớm.
            watch = ANALYZER.live_watch(df_15m)

            if watch:
                logger.info(
                    f"👀 WATCH {watch['signal']} "
                    f"score={watch['score']}"
                )
                with Config.status_lock:
                    Config.SYSTEM_STATUS["market_insight"] = (
                        f"WATCH {watch['signal']} "
                        f"{watch['score']}/100"
                    )

                for chat_id in no_position_users:
                    NOTIFIER.send_watch(chat_id, watch)

            # Closed candle: tín hiệu chính thức.
            result = ANALYZER.analyze(df_15m)

            if result:
                logger.info(
                    f"🔥 {result['kind']} "
                    f"{result['signal']} "
                    f"score={result.get('score')}"
                )

                with Config.status_lock:
                    Config.SYSTEM_STATUS["last_signal"] = (
                        f"{result['signal']} "
                        f"{result.get('score', 0)}/100 "
                        f"({now_vn})"
                    )
                    Config.SYSTEM_STATUS["market_insight"] = (
                        ANALYZER.last_insight
                    )

                for chat_id in no_position_users:
                    NOTIFIER.send_signal(
                        chat_id,
                        "SOL/USDT",
                        result,
                        FETCHER.last_successful_exchange
                    )

    except Exception as e:
        logger.exception(f"❌ Lỗi chu kỳ: {e}")
        with Config.status_lock:
            Config.SYSTEM_STATUS["last_error"] = str(e)[:300]


# ==========================================
# 9. START
# ==========================================
if __name__ == "__main__":
    logger.info("🤖 Bot Trade Future AI V7.1 đã khởi động!")
    logger.info(
        "🧠 Strategy: SCORE + STRUCTURE + EMA + RSI + ADX + VOLUME"
    )
    logger.info(
        "⏱️ Scheduler: mỗi phút, quét sau giây %02d để bắt nến 15m vừa đóng"
        % Config.SCHEDULE_SECOND
    )
    logger.info(
        "🚫 BTC filter: OFF"
    )
    logger.info(
        "🛡️ Gemini lỗi: Strategy + ML vẫn được phép phát tín hiệu"
    )
    logger.info(
        "🤖 ML labels: sideway=%s bullish=%s bearish=%s"
        % (Config.ML_SIDEWAY_LABEL, Config.ML_BULLISH_LABEL, Config.ML_BEARISH_LABEL)
    )

    Config.init_users()

    threading.Thread(
        target=keep_alive,
        daemon=True
    ).start()

    NOTIFIER.setup_commands()

    for cid in NOTIFIER.chat_ids:
        NOTIFIER.send_message(
            cid,
            "🚀 **Bot Trade Future AI V7.1 đã khởi động!**\n"
            "🧠 Score Engine + Market Structure\n"
            "🚫 Không còn BTC filter\n"
            "🛡️ Gemini OFFLINE không làm bot im"
        )

    run_bot_job()

    # Quét mỗi phút, lệch 2 giây sau mốc phút để bắt nến 15m vừa đóng.
    schedule.every().minute.at(f":{Config.SCHEDULE_SECOND:02d}").do(run_bot_job)

    while True:
        try:
            schedule.run_pending()
            NOTIFIER.check_commands()
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Main loop lỗi: {e}")
            time.sleep(5)
