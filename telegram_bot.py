import os
import requests
import datetime
from dotenv import load_dotenv

load_dotenv()

SYSTEM_STATUS = {
    "status": "🟡 Đang khởi động...",
    "last_check": "Chưa có",
    "last_error": "Không có",
    "last_signal": "Chưa có"
}

ACTIVE_TRADE = {
    "in_position": False,
    "type": None
}

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.get_updates_url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        self.edit_message_url = f"https://api.telegram.org/bot{self.token}/editMessageText"
        self.answer_callback_url = f"https://api.telegram.org/bot{self.token}/answerCallbackQuery"
        self.last_update_id = None

    def setup_commands(self):
        """Thiết lập Menu các lệnh có sẵn cho Bot"""
        if not self.token: return
        url = f"https://api.telegram.org/bot{self.token}/setMyCommands"
        commands = [
            {"command": "ping", "description": "Kiểm tra kết nối Bot (Pong)"},
            {"command": "status", "description": "Xem báo cáo tình trạng hệ thống"}
        ]
        try:
            requests.post(url, json={"commands": commands})
        except Exception as e:
            print(f"Lỗi tạo Menu Telegram: {e}")

    def send_signal(self, symbol, signal_type, entry, tp, sl, rsi, ema_trend):
        """
        Gửi tin nhắn tín hiệu trade về Telegram kèm Nút Bấm
        """
        if not self.token or not self.chat_id:
            print("Chưa cấu hình Telegram Token hoặc Chat ID.")
            return

        icon = "🟢 LONG" if signal_type == "LONG" else "🔴 SHORT"
        
        # --- PHÂN TÍCH RỦI RO & ĐI LỆNH ---
        risk_warnings = []
        
        # 1. Rủi ro trượt giá (FOMO / Slippage)
        # Nới lỏng khoảng cách cho phép trượt giá lên 1.0 ATR (trước đây là 0.5 nên quá khắt khe)
        atr_value = abs(entry - sl) / 2.0
        if signal_type == "LONG":
            fomo_price = entry + atr_value
            ideal_zone = f"{entry - atr_value:.4f} ➡️ {entry + (0.3*atr_value):.4f}"
            slip_warning = f"Nếu giá lỡ bay quá `{fomo_price:.4f}`, khuyên sếp ĐI NỬA VOLUME để bù đắp rủi ro Stoploss bị xa."
        else:
            fomo_price = entry - atr_value
            ideal_zone = f"{entry:.4f} ➡️ {entry + atr_value:.4f}"
            slip_warning = f"Nếu giá lỡ sập quá `{fomo_price:.4f}`, khuyên sếp ĐI NỬA VOLUME để bù đắp rủi ro Stoploss bị xa."
            
        risk_warnings.append(f"🎯 **Entry lý tưởng:** Quanh vùng `{ideal_zone}`.\n👉 {slip_warning}")
        
        # 2. Rủi ro RSI (Quá Mua / Quá Bán)
        if signal_type == "LONG" and rsi > 65:
            risk_warnings.append("⚠️ **Cẩn thận RSI:** Đang ở vùng quá mua (>65), rất dễ có nhịp chỉnh (Pullback) đỏ lửa rồi mới lên tiếp.")
        elif signal_type == "SHORT" and rsi < 35:
            risk_warnings.append("⚠️ **Cẩn thận RSI:** Đang ở vùng quá bán (<35), rất dễ bị giật râu lên quét thanh khoản rồi mới sập.")
            
        # 3. Phân tích độ tự tin của AI
        try:
            # Bóc tách win_prob từ chuỗi ema_trend (Ví dụ: "... | AI_Win_Prob: 96.7%")
            win_prob = float(ema_trend.split("AIWinProb: ")[-1].replace("%", "").strip())
            if win_prob < 70.0:
                risk_warnings.append(f"⚠️ **Rủi ro AI:** Xác suất thắng chỉ ở mức Khá ({win_prob}%). Khuyến nghị đi Volume nhỏ lại.")
            elif win_prob >= 90.0:
                risk_warnings.append(f"🔥 **AI Tự Tin:** Tỷ lệ ăn cực cao ({win_prob}%). Kèo này đẹp, có thể vã Full Volume!")
        except Exception:
            pass
            
        advice = "\n💡 **PHÂN TÍCH RỦI RO KÈO NÀY:**\n" + "\n\n".join(risk_warnings)
        
        message = (
            f"🚀 **TÍN HIỆU {icon} {symbol}** 🚀\n\n"
            f"🔹 **Giá Bot Quét:** {entry}\n"
            f"🎯 **Take Profit:** {tp}\n"
            f"🛑 **Stop Loss:** {sl}\n\n"
            f"📊 **Thông số kỹ thuật:**\n"
            f"- RSI: {rsi:.2f}\n"
            f"- Xu hướng: {ema_trend}\n"
            f"{advice}\n"
        )

        reply_markup = {
            "inline_keyboard": [
                [{"text": "✅ Đã vào lệnh (Bật Vệ Sĩ)", "callback_data": f"ENTERED_{signal_type}"}]
            ]
        }

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "reply_markup": reply_markup
        }

        try:
            response = requests.post(self.api_url, json=payload)
            if response.status_code == 200:
                print("Đã gửi tín hiệu Telegram thành công!")
                # Kích hoạt cuộc gọi điện thoại
                self.make_call(symbol, signal_type)
            else:
                print(f"Lỗi gửi Telegram: {response.text}")
        except Exception as e:
            print(f"Lỗi kết nối Telegram: {e}")

    def make_call(self, symbol, signal_type):
        """Sử dụng CallMeBot để gọi điện thoại cảnh báo tín hiệu"""
        username = "@huyduong112233"
        text = f"Sếp ơi, có kèo {signal_type} con {symbol.replace('/', ' ')}, vào Telegram kiểm tra ngay nhé!"
        # Thay khoảng trắng bằng dấu +
        text = text.replace(" ", "+")
        url = f"http://api.callmebot.com/start.php?user={username}&text={text}&lang=vi-VN-Standard-A&rpt=2"
        try:
            requests.get(url)
            print("Đã kích hoạt cuộc gọi CallMeBot thành công!")
        except Exception as e:
            print(f"Lỗi gọi CallMeBot: {e}")

    def send_message(self, text, reply_markup=None):
        """
        Gửi tin nhắn text bình thường (có hỗ trợ Nút Bấm)
        """
        if not self.token or not self.chat_id:
            return

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
            
        try:
            requests.post(self.api_url, json=payload)
        except Exception as e:
            print(f"Lỗi gửi tin nhắn Telegram: {e}")

    def edit_message(self, chat_id, message_id, text, reply_markup=None):
        """Sửa đổi tin nhắn cũ (Ví dụ: Thêm trạng thái Đang Bảo Vệ)"""
        if not self.token: return
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        requests.post(self.edit_message_url, json=payload)

    def answer_callback(self, callback_query_id, text):
        """Hiển thị thông báo nhỏ (Toast) khi người dùng bấm nút"""
        if not self.token: return
        payload = {
            "callback_query_id": callback_query_id,
            "text": text
        }
        requests.post(self.answer_callback_url, json=payload)

    def check_commands(self):
        """
        Lắng nghe và phản hồi lệnh/nút bấm từ người dùng
        """
        global ACTIVE_TRADE
        
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
                    
                    # 1. Xử lý nút bấm (Callback Query)
                    if "callback_query" in result:
                        callback = result["callback_query"]
                        data = callback.get("data", "")
                        message = callback.get("message", {})
                        msg_id = message.get("message_id")
                        chat_id = message.get("chat", {}).get("id")
                        original_text = message.get("text", "")
                        
                        if data.startswith("ENTERED_"):
                            trade_type = data.split("_")[1]
                            # Cập nhật trạng thái sang ĐANG GỒNG LỆNH
                            ACTIVE_TRADE["in_position"] = True
                            ACTIVE_TRADE["type"] = trade_type
                            
                            new_text = original_text + f"\n\n🛡️ **CHẾ ĐỘ BẢO VỆ: ĐANG BẬT ({trade_type})**\n_Bot đang theo dõi sát sao thị trường để bảo vệ vốn..._"
                            new_markup = {
                                "inline_keyboard": [
                                    [{"text": "🛑 Dừng lệnh (Chốt/Cắt xong)", "callback_data": "STOP_TRADE"}]
                                ]
                            }
                            self.edit_message(chat_id, msg_id, new_text, new_markup)
                            self.answer_callback(callback["id"], f"Đã bật Vệ Sĩ bảo vệ lệnh {trade_type}!")
                            print(f"Sếp đã xác nhận vào lệnh {trade_type}. Chuyển sang chế độ Vệ Sĩ!")
                            
                        elif data == "STOP_TRADE":
                            # Tắt chế độ bảo vệ, quay lại săn mồi
                            ACTIVE_TRADE["in_position"] = False
                            ACTIVE_TRADE["type"] = None
                            
                            # Xóa đoạn text Bảo Vệ Đang Bật
                            if "🛡️" in original_text:
                                new_text = original_text.split("🛡️")[0] + "✅ **LỆNH ĐÃ KẾT THÚC**\n_Bot đang quay lại chế độ săn mồi..._"
                            else:
                                new_text = original_text + "\n\n✅ **LỆNH ĐÃ KẾT THÚC**"
                                
                            self.edit_message(chat_id, msg_id, new_text, {}) # Bỏ hết nút
                            self.answer_callback(callback["id"], "Đã tắt Vệ Sĩ, quay lại săn mồi!")
                            print("Sếp đã chốt lệnh. Chuyển sang chế độ Săn Mồi!")
                            
                        continue
                    
                    # 2. Xử lý tin nhắn văn bản (Commands)
                    message = result.get("message", {})
                    text = message.get("text", "")
                    chat_id = message.get("chat", {}).get("id")

                    if text == "/ping" and str(chat_id) == str(self.chat_id):
                        self.send_message("🏓 Pong! Bot V4.0 (Fast Scalping) vẫn đang thức trắng đêm phục vụ sếp!")
                    elif text == "/status" and str(chat_id) == str(self.chat_id):
                        mode = "🛡️ ĐANG BẢO VỆ LỆNH" if ACTIVE_TRADE["in_position"] else "⚔️ ĐANG SĂN MỒI"
                        msg = (
                            f"📊 **BÁO CÁO TRẠNG THÁI HỆ THỐNG**\n\n"
                            f"🔹 **Chế độ:** {mode}\n"
                            f"🔹 **Tình trạng:** {SYSTEM_STATUS['status']}\n"
                            f"🕒 **Lần quét nến gần nhất:** {SYSTEM_STATUS['last_check']}\n"
                            f"⚠️ **Lỗi hiện tại:** {SYSTEM_STATUS['last_error']}\n"
                            f"🔥 **Tín hiệu gần nhất:** {SYSTEM_STATUS['last_signal']}"
                        )
                        self.send_message(msg)
        except Exception:
            pass
