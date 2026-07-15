import os
import requests
from dotenv import load_dotenv

load_dotenv()

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.get_updates_url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        self.last_update_id = None

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

    def check_commands(self):
        """
        Lắng nghe và phản hồi lệnh từ người dùng (vd: /ping)
        """
        if not self.token or not self.chat_id:
            return

        params = {"timeout": 1}
        if self.last_update_id:
            params["offset"] = self.last_update_id + 1

        try:
            response = requests.get(self.get_updates_url, params=params).json()
            if response.get("ok"):
                for result in response.get("result", []):
                    self.last_update_id = result["update_id"]
                    
                    message = result.get("message", {})
                    text = message.get("text", "")
                    chat_id = message.get("chat", {}).get("id")

                    if text == "/ping" and str(chat_id) == str(self.chat_id):
                        self.send_message("🏓 Pong! Bot V3.0 (Có AI) vẫn đang thức trắng đêm quét tín hiệu cho sếp đây!")
        except Exception:
            pass
