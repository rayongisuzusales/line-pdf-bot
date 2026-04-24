"""
LINE Bot - รับ PDF แปลงเป็น JPG ส่งกลับทันที
ติดตั้ง: pip install flask line-bot-sdk pdf2image pillow requests
"""

import os
import io
import tempfile
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, FileMessage, TextSendMessage, ImageSendMessage
)
from pdf2image import convert_from_bytes

app = Flask(__name__)

# ===== ตั้งค่าตรงนี้ =====
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "ใส่ token ของคุณ")
LINE_CHANNEL_SECRET       = os.environ.get("LINE_CHANNEL_SECRET", "ใส่ secret ของคุณ")
# Poppler path (Windows ใส่ path, Linux/Mac ใส่ None)
POPPLER_PATH = os.environ.get("POPPLER_PATH", None)
# Base URL ของ server (ใช้ส่ง image กลับ LINE)
BASE_URL = os.environ.get("BASE_URL", "https://your-server.com")
# โฟลเดอร์เก็บ JPG ชั่วคราว
OUTPUT_DIR = "/tmp/line_jpg"
# =========================

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
    """รับไฟล์ PDF → แปลงเป็น JPG → ส่งกลับ"""
    file_name = event.message.file_name or "file"

    # รับเฉพาะ PDF
    if not file_name.lower().endswith(".pdf"):
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="⚠️ กรุณาส่งเฉพาะไฟล์ .pdf เท่านั้นครับ")
        )
        return

    # แจ้งผู้ใช้ว่ากำลังประมวลผล
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=f"⏳ กำลังแปลง {file_name} เป็น JPG...")
    )

    # ดาวน์โหลดไฟล์ PDF จาก LINE
    message_content = line_bot_api.get_message_content(event.message.id)
    pdf_bytes = b"".join(chunk for chunk in message_content.iter_content())

    try:
        # แปลง PDF → list of PIL Images
        kwargs = {"dpi": 200}
        if POPPLER_PATH:
            kwargs["poppler_path"] = POPPLER_PATH

        images = convert_from_bytes(pdf_bytes, **kwargs)
        total_pages = len(images)

        push_messages = []

        for i, img in enumerate(images):
            # บันทึก JPG
            jpg_path = os.path.join(OUTPUT_DIR, f"{event.message.id}_p{i+1}.jpg")
            img.save(jpg_path, "JPEG", quality=90)

            # สร้าง URL สำหรับส่งกลับ LINE
            img_url = f"{BASE_URL}/jpg/{event.message.id}_p{i+1}.jpg"

            push_messages.append(
                ImageSendMessage(
                    original_content_url=img_url,
                    preview_image_url=img_url
                )
            )

        # ส่งทีละ 5 รูป (LINE limit)
        chunks = [push_messages[i:i+5] for i in range(0, len(push_messages), 5)]

        # ส่งสรุปก่อน
        line_bot_api.push_message(
            event.source.user_id,
            TextSendMessage(text=f"✅ แปลงเสร็จ! {file_name} = {total_pages} หน้า กำลังส่งรูปให้...")
        )

        # ส่งรูปทีละ chunk
        for chunk in chunks:
            line_bot_api.push_message(event.source.user_id, chunk)

    except Exception as e:
        line_bot_api.push_message(
            event.source.user_id,
            TextSendMessage(text=f"❌ เกิดข้อผิดพลาด: {str(e)}")
        )


# Serve JPG files
from flask import send_from_directory

@app.route("/jpg/<filename>")
def serve_jpg(filename):
    return send_from_directory(OUTPUT_DIR, filename)


@app.route("/")
def index():
    return "LINE PDF→JPG Bot กำลังทำงาน ✅"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
