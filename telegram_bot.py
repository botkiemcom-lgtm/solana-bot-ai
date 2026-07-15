import os
import requests
from dotenv import load_dotenv

load_dotenv()

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_signal(self, symbol, signal_type, entry, tp, sl, rsi, ema_trend):
        """
        Gửi tin nhắn tín hiệu trade về Telegram
        """
        if not self.token or not self.chat_id:
            print("Chưa cấu hình Telegram Token hoặc Chat ID.")
            return

        icon = "🟢 LONG" if signal_type == "LONG" else "🔴 SHORT"
        
        message = (
            f"🚀 **TÍN HIỆU {icon} {symbol}** 🚀\n\n"
            f"🔹 **Entry:** {entry}\n"
            f"🎯 **Take Profit (TP):** {tp}\n"
            f"🛑 **Stop Loss (SL):** {sl}\n\n"
            f"📊 **Thông số kỹ thuật:**\n"
            f"- RSI: {rsi:.2f}\n"
            f"- Xu hướng EMA: {ema_trend}\n"
        )

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }

        try:
            response = requests.post(self.api_url, json=payload)
            if response.status_code == 200:
                print("Đã gửi tín hiệu Telegram thành công!")
            else:
                print(f"Lỗi gửi Telegram: {response.text}")
        except Exception as e:
            print(f"Lỗi kết nối Telegram: {e}")

    def send_message(self, text):
        """
        Gửi tin nhắn text bình thường (dùng để test hoặc thông báo trạng thái)
        """
        if not self.token or not self.chat_id:
            return

        payload = {
            "chat_id": self.chat_id,
            "text": text
        }
        try:
            requests.post(self.api_url, json=payload)
        except Exception as e:
            print(f"Lỗi gửi tin nhắn Telegram: {e}")
