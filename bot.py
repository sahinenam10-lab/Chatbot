# bot_openrouter_context.py
import json
import time
import urllib.request
import requests
import os
from flask import Flask
from threading import Thread

# ==== CONFIGURATION ====
# !!!!! সতর্কতা: আপনার আসল টোকেন এবং API কী নিচের দুটি লাইনে বসান !!!!!
BOT_TOKEN = "8062273828:AAEJ5qaWqFAAVm28s1ikgY4J47gi_Quwhwo"  # এখানে আপনার টেলিগ্রাম বট টোকেন পেস্ট করুন
OPENROUTER_API_KEY = "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" # এখানে আপনার OpenRouter API কী পেস্ট করুন

MODEL_NAME = "gpt-4o-mini"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# ==== CONTEXT / MEMORY SETTINGS ====
CONTEXTS = {}
MAX_HISTORY = 12
MAX_CHARS = 4000

# ==== HELP TEXT ====
HELP_TEXT = (
    "  Commands:\n"
    "/start - Welcome message\n"
    "/reset - Clear conversation memory for this chat\n"
    "/history - Show recent conversation context (debug)\n\n"
    "Just send normal messages to chat with the bot. The bot will remember recent messages so replies feel natural."
)

# Choreo-এর জন্য একটি মিনি Flask ওয়েব অ্যাপ
app = Flask(__name__)

@app.route('/')
def health_check():
    """Choreo এই এন্ডপয়েন্টটি ব্যবহার করে নিশ্চিত হবে যে অ্যাপটি চলছে।"""
    return "Telegram bot is alive and running!", 200

def run_web_server():
    """Flask ওয়েব সার্ভার চালানোর জন্য ফাংশন।"""
    # Choreo দ্বারা নির্ধারিত PORT ব্যবহার করুন, ডিফল্ট 8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# ==== TELEGRAM HELPERS ====
def send_message(chat_id, text):
    url = API_URL + "sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    headers = {"Content-Type": "application/json"}
    data = json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, headers=headers)
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"[ ] Telegram send error: {e}")

def get_updates(offset=None):
    url = API_URL + "getUpdates"
    if offset:
        url += f"?offset={offset}"
    try:
        with urllib.request.urlopen(url) as res:
            return json.loads(res.read())
    except Exception as e:
        print(f"[ ] Update fetch error: {e}")
        return {}

# ==== CONTEXT HELPERS ====
def append_context(chat_id: int, role: str, text: str):
    ctx = CONTEXTS.setdefault(chat_id, [])
    ctx.append({"role": role, "content": text})
    # পুরনো মেসেজ বাদ দিন যদি তা MAX_HISTORY-এর বেশি হয়
    if len(ctx) > MAX_HISTORY * 2:
        CONTEXTS[chat_id] = ctx[-MAX_HISTORY*2:]

def build_messages_for_api(chat_id: int, user_prompt: str):
    system_prompt = {
        "role": "system",
        "content": (
            "You are a friendly, witty, and conversational AI assistant. "
            "Respond like a real person: casual, concise, occasionally humorous, and engaging. "
            "Ask follow-up questions when helpful. Use emojis sparingly. Avoid being robotic or boring."
        )
    }
    messages = [system_prompt]
    ctx = CONTEXTS.get(chat_id, [])
    total_chars = len(system_prompt["content"]) + len(user_prompt)
    for item in ctx:
        est_len = len(item["content"]) + 20
        if total_chars + est_len > MAX_CHARS:
            continue
        messages.append({"role": item["role"], "content": item["content"]})
        total_chars += est_len
    messages.append({"role": "user", "content": user_prompt})
    return messages

# ==== ASK OPENROUTER (with context) ====
def ask_openrouter_with_context(chat_id: int, prompt: str):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    messages = build_messages_for_api(chat_id, prompt)
    data = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 800
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        result = response.json()
        print("  Full OpenRouter Response:", json.dumps(result, indent=2))
        if "choices" in result and len(result["choices"]) > 0:
            reply = result["choices"][0]["message"]["content"]
            append_context(chat_id, "user", prompt)
            append_context(chat_id, "assistant", reply)
            return reply
        else:
            return "  OpenRouter returned empty response."
    except Exception as e:
        print(f"[ ] OpenRouter error: {e}")
        return "  Could not get a response from OpenRouter."

# ==== HANDLE MESSAGE ====
def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    if not text:
        return
    cmd = text.split(maxsplit=1)[0].lower()
    if cmd == "/start":
        send_message(chat_id, "  Hi! I'm your friendly chat bot. I remember recent messages so our chat feels natural.")
        return
    if cmd == "/help":
        send_message(chat_id, HELP_TEXT)
        return
    if cmd == "/reset":
        CONTEXTS.pop(chat_id, None)
        send_message(chat_id, "  Conversation memory cleared for this chat.")
        return
    if cmd == "/history":
        ctx = CONTEXTS.get(chat_id, [])
        if not ctx:
            send_message(chat_id, "  No recent context stored.")
            return
        lines = []
        for i, item in enumerate(ctx[-10:], start=1):
            role = item["role"]
            content = item["content"]
            lines.append(f"{i}. {role}: {content[:200]}")
        send_message(chat_id, "  Recent context:\n\n" + "\n\n".join(lines))
        return
    reply = ask_openrouter_with_context(chat_id, text)
    send_message(chat_id, reply)

# ==== MAIN LOOP ====
def run_bot_polling():
    """এই ফাংশনটি টেলিগ্রাম বট এর মূল লুপটি চালাবে।"""
    print("  Starting Telegram bot polling...")
    last_update_id = None
    while True:
        updates = get_updates(last_update_id)
        for update in updates.get("result", []):
            last_update_id = update["update_id"] + 1
            if "message" in update:
                handle_message(update["message"])
        time.sleep(1)

if __name__ == "__main__":
    print("  OpenRouter Chat Bot (context-aware) is starting...")
    
    # একটি ব্যাকগ্রাউন্ড থ্রেডে ওয়েব সার্ভার চালান
    web_server_thread = Thread(target=run_web_server)
    web_server_thread.daemon = True
    web_server_thread.start()
    
    # মূল থ্রেডে টেলিগ্রাম বট চালান
    run_bot_polling()
