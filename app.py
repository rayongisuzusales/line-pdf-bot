import os
from flask import Flask, request, abort, send_from_directory
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, FileMessage, TextSendMessage, ImageSendMessage

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET       = os.environ.get("LINE_CHANNEL_SECRET", "")
BASE_URL = os.environ.get("BASE_URL", "")
OUTPUT_DIR = "/tmp/line_jpg"

os.makedirs(OUTPUT_DIR, exist_ok=True)

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler      = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=FileMessage)
def handle_file(event):
    file_name = event.message.file_name or "file"
    if not file_name.lower().endswith(".pdf"):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ กรุณาส่งเฉพาะไฟล์ .pdf เท่านั้นครับ"))
        return
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"⏳ กำลังแปลง {file_name} เป็น JPG..."))
    message_content = line_bot_api.get_message_content(event.message.id)
    pdf_bytes = b"".join(chunk for chunk in message_content.iter_content())
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)
        push_messages = []
        for i in range(total_pages):
            page = doc[i]
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat)
            jpg_filename = f"{event.message.id}_p{i+1}.jpg"
            pix.save(os.path.join(OUTPUT_DIR, jpg_filename))
            img_url = f"{BASE_URL}/jpg/{jpg_filename}"
            push_messages.append(ImageSendMessage(original_content_url=img_url, preview_image_url=img_url))
        doc.close()
        line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"✅ แปลงเสร็จ! {file_name} = {total_pages} หน้า"))
        for chunk in [push_messages[i:i+5] for i in range(0, len(push_messages), 5)]:
            line_bot_api.push_message(event.source.user_id, chunk)
    except Exception as e:
        line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"❌ เกิดข้อผิดพลาด: {str(e)}"))

@app.route("/jpg/<filename>")
def serve_jpg(filename):
    return send_from_directory(OUTPUT_DIR, filename)

@app.route("/")
def index():
    return "LINE PDF to JPG Bot is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
