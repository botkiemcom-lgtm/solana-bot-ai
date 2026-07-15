import time
import datetime
import schedule
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from data_fetcher import BinanceFetcher
from analyzer import StrategyAnalyzer
import telegram_bot
from telegram_bot import TelegramNotifier

class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Bot Trade Future AI is running live on Render Free Tier!")

def keep_alive():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyServer)
    server.serve_forever()

def run_bot_job():
    print("🔄 Đang quét dữ liệu SOL/USDT khung 5m...")
    telegram_bot.SYSTEM_STATUS["last_check"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Khởi tạo các module
    fetcher = BinanceFetcher()
    analyzer = StrategyAnalyzer()
    notifier = TelegramNotifier()

    # 2. Lấy dữ liệu đa khung thời gian (5m, 15m, 1h, 4h)
    df_5m = fetcher.fetch_ohlcv(symbol="SOL/USDT", timeframe="5m", limit=100)
    df_15m = fetcher.fetch_ohlcv(symbol="SOL/USDT", timeframe="15m", limit=100)
    df_1h = fetcher.fetch_ohlcv(symbol="SOL/USDT", timeframe="1h", limit=100)
    df_4h = fetcher.fetch_ohlcv(symbol="SOL/USDT", timeframe="4h", limit=100)
    
    if df_5m is not None and df_15m is not None and df_1h is not None and df_4h is not None:
        telegram_bot.SYSTEM_STATUS["status"] = "🟢 Đang hoạt động tốt"
        telegram_bot.SYSTEM_STATUS["last_error"] = "Không có"
        
        # 3. Đưa vào bộ não phân tích (V4.0)
        result = analyzer.analyze(df_5m, df_15m, df_1h, df_4h)
        
        # 4. Gửi tín hiệu nếu có
        if result:
            print(f"🔥 Phát hiện tín hiệu {result['signal']}! Đang gửi Telegram...")
            telegram_bot.SYSTEM_STATUS["last_signal"] = f"{result['signal']} ({telegram_bot.SYSTEM_STATUS['last_check']})"
            notifier.send_signal(
                symbol="SOL/USDT",
                signal_type=result['signal'],
                entry=result['entry'],
                tp=result['tp'],
                sl=result['sl'],
                rsi=result['rsi'],
                ema_trend=result['ema_trend']
            )
        else:
            print("💤 Chưa có tín hiệu đẹp, tiếp tục chờ...")
    else:
        print("❌ Lỗi lấy dữ liệu, sẽ thử lại ở chu kỳ sau.")
        telegram_bot.SYSTEM_STATUS["status"] = "🔴 Lỗi lấy dữ liệu nến"
        telegram_bot.SYSTEM_STATUS["last_error"] = "Binance API chặn hoặc lỗi mạng"

def main():
    print("🤖 Bot Trade Future AI đã khởi động!")
    print("Bot sẽ tự động quét tín hiệu mỗi 5 phút...")
    
    # Khởi chạy server giả để Render không tắt bot
    threading.Thread(target=keep_alive, daemon=True).start()
    
    # Gửi tin nhắn test khởi động
    notifier = TelegramNotifier()
    notifier.send_message("🟢 **Bot Trade Future AI đã khởi động thành công!**\n\nBot đang tiến hành theo dõi cặp **SOL/USDT** (Khung 5m). Nếu có tín hiệu tốt, bot sẽ lập tức báo về đây cho sếp!")
    
    # Chạy ngay lần đầu tiên khi vừa bật bot
    run_bot_job()

    # Lập lịch chạy mỗi 5 phút
    schedule.every(5).minutes.do(run_bot_job)

    # Vòng lặp giữ bot luôn chạy
    notifier_listener = TelegramNotifier()
    while True:
        schedule.run_pending()
        notifier_listener.check_commands()
        time.sleep(2)

if __name__ == "__main__":
    main()
