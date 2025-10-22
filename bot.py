import json
import time
import urllib.request
import requests

# ==== CONFIGURATION ====
BOT_TOKEN = "8062273828:AAEJ5qaWqFAAVm28s1ikgY4J47gi_Quwhwo"
OPENROUTER_API_KEY = "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"
MODEL_NAME = "gpt-4o-mini"

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# ==== SEND TELEGRAM MESSAGE ====
def send_message(chat_id, text):
    url = API_URL + "sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    headers = {"Content-Type": "application/json"}
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        urllib.request.urlopen(req)
        print(f"[✓] Message sent to {chat_id}")
    except Exception as e:
        print(f"[✗] Telegram send error: {e}")

# ==== GET UPDATES ====
def get_updates(offset=None):
    url = API_URL + "getUpdates"
    if offset:
        url += f"?offset={offset}"
    try:
        with urllib.request.urlopen(url) as res:
            return json.loads(res.read())
    except Exception as e:
        print(f"[✗] Update fetch error: {e}")
        return {}

# ==== ASK OPENROUTER WITH AUREVIX IDENTITY ====
def ask_openrouter(prompt):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Aurevix, a friendly, witty, human-like AI assistant. "
                    "You always introduce yourself as Aurevix whenever asked who you are. "
                    "Talk naturally, keep conversations fun and engaging, "
                    "and respond in a human-like friendly tone."
                )
            },
            {"role": "user", "content": prompt}
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        result = response.json()
        print("💡 Full OpenRouter Response:", json.dumps(result, indent=2))

        # Error handling
        if "error" in result:
            return f"⚠️ OpenRouter Error: {result['error'].get('message', 'Unknown error')}"
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        else:
            return "Hmm, I didn't quite get that. Try asking differently."
    except Exception as e:
        print(f"[✗] OpenRouter error: {e}")
        return "Oops! Could not get a response from Aurevix right now."

# ==== HANDLE MESSAGE ====
def handle_message(message):
    chat_id = message["chat"]["id"]
    user_first_name = message["chat"].get("first_name", "there")
    text = message.get("text", "")

    if text == "/start":
        send_message(chat_id, f"Hey {user_first_name}! 👋 I'm **Aurevix**, your AI chat buddy. Ask me anything and let's have fun chatting!")
    else:
        reply = ask_openrouter(text)
        send_message(chat_id, reply)

# ==== MAIN LOOP ====
def main():
    print("🤖 Aurevix Chat Bot is running on your mobile...")
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
