import os
import requests
import traceback
from datetime import datetime
from database import log_error

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "stepfun/step-3.5-flash:free"  # бесплатная модель

def call_llm(prompt: str, system_prompt: str = None) -> str:
    if not OPENROUTER_API_KEY:
        msg = "⚠️ Внешний AI-помощник недоступен: не задан ключ API OpenRouter."
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")
        return msg

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        # Некоторые модели требуют HTTP-Referer (можно указать любой)
        "HTTP-Referer": "https://skillforge.local",
        "X-Title": "SkillForge Analyst"
    }
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": DEFAULT_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1000
    }

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LLM запрос: {prompt[:200]}...")

    try:
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=60)
        
        if response.status_code != 200:
            error_body = response.text
            error_msg = f"❌ HTTP {response.status_code}: {error_body[:200]}"
            log_error("LLM_API_HTTP", error_msg, traceback.format_exc())
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {error_msg}")
            return f"Ошибка внешнего API: {response.status_code}"

        data = response.json()
        answer = data['choices'][0]['message']['content']
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LLM ответ: {answer[:200]}...")
        return answer

    except requests.exceptions.Timeout:
        log_error("LLM_API_TIMEOUT", "Request timeout", traceback.format_exc())
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ Тайм-аут при обращении к API")
        return "Превышено время ожидания ответа от AI-помощника."

    except requests.exceptions.ConnectionError:
        log_error("LLM_API_CONNECTION", "Connection error", traceback.format_exc())
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ Ошибка соединения с API")
        return "Не удалось подключиться к AI-помощнику."

    except Exception as e:
        log_error("LLM_API", str(e), traceback.format_exc())
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ Неизвестная ошибка: {e}")
        return f"❌ Ошибка при обращении к AI-помощнику: {e}"