# bot_openrouter_context.py
import json
import time
import urllib.request
import requests
import os 

# ==== CONFIGURATION ====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

MODEL_NAME = "gpt-4o-mini"

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# ==== CONTEXT / MEMORY SETTINGS ====
CONTEXTS = {}          # chat_id -> list of {"role": "user"|"assistant", "content": "text"}
MAX_HISTORY = 12       #     X message pairs (user+assistant counts separately)
MAX_CHARS = 4000       #  prompt length    ()   

# ==== HELP TEXT ====
HELP_TEXT = (
    " Commands:\n"
    "/start - Welcome message\n"
    "/reset - Clear conversation memory for this chat\n"
    "/history - Show recent conversation context (debug)\n\n"
    "Just send normal messages to chat with the bot. The bot will remember recent messages so replies feel natural."
)

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
        print(f"[] Telegram send error: {e}")

def get_updates(offset=None):
    url = API_URL + "getUpdates"
    if offset:
        url += f"?offset={offset}"
    try:
        with urllib.request.urlopen(url) as res:
            return json.loads(res.read())
    except Exception as e:
        print(f"[] Update fetch error: {e}")
        return {}

# ==== CONTEXT HELPERS ====
def append_context(chat_id: int, role: str, text: str):
    ctx = CONTEXTS.setdefault(chat_id, [])
    ctx.append({"role": role, "content": text})
    # trim older if too long (keep most recent)
    if len(ctx) > MAX_HISTORY * 2:
        CONTEXTS[chat_id] = ctx[-MAX_HISTORY*2:]

def build_messages_for_api(chat_id: int, user_prompt: str):
    """
    Build messages array for OpenRouter-compatible chat API.
    We'll include a system prompt first, then as much recent context as fits.
    """
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
    # include as much context as possible, newest last
    total_chars = len(system_prompt["content"]) + len(user_prompt)
    # iterate from oldest to newest, include if within MAX_CHARS
    for item in ctx:
        est_len = len(item["content"]) + 20
        if total_chars + est_len > MAX_CHARS:
            # skip oldest entries until fits
            continue
        messages.append({"role": item["role"], "content": item["content"]})
        total_chars += est_len

    # finally add the current user prompt
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
        # you can tweak temperature, max_tokens etc.
        "temperature": 0.7,
        "max_tokens": 800
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        result = response.json()
        print(" Full OpenRouter Response:", json.dumps(result, indent=2))
        if "choices" in result and len(result["choices"]) > 0:
            # assistant reply
            reply = result["choices"][0]["message"]["content"]
            # update context: append user prompt and assistant reply
            append_context(chat_id, "user", prompt)
            append_context(chat_id, "assistant", reply)
            return reply
        else:
            return " OpenRouter returned empty response."
    except Exception as e:
        print(f"[] OpenRouter error: {e}")
        return " Could not get a response from OpenRouter."

# ==== HANDLE MESSAGE ====
def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if not text:
        return

    # handle commands
    cmd = text.split(maxsplit=1)[0].lower()
    if cmd == "/start":
        send_message(chat_id, " Hi! I'm your friendly chat bot. I remember recent messages so our chat feels natural.")
        return
    if cmd == "/help":
        send_message(chat_id, HELP_TEXT)
        return
    if cmd == "/reset":
        CONTEXTS.pop(chat_id, None)
        send_message(chat_id, " Conversation memory cleared for this chat.")
        return
    if cmd == "/history":
        ctx = CONTEXTS.get(chat_id, [])
        if not ctx:
            send_message(chat_id, " No recent context stored.")
            return
        # show last few items
        lines = []
        for i, item in enumerate(ctx[-10:], start=1):
            role = item["role"]
            content = item["content"]
            lines.append(f"{i}. {role}: {content[:200]}")
        send_message(chat_id, " Recent context:\n\n" + "\n\n".join(lines))
        return

    # normal user message -> ask with context
    reply = ask_openrouter_with_context(chat_id, text)
    send_message(chat_id, reply)

# ==== MAIN LOOP ====
def main():
    print(" OpenRouter Chat Bot (context-aware) is running...")
    last_update_id = None
    while True:
        updates = get_updates(last_update_id)
        for update in updates.get("result", []):
            last_update_id = update["update_id"] + 1
            if "message" in update:
                handle_message(update["message"])
        time.sleep(1)

if __name__ == "__main__":
    main()
