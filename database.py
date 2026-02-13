import sqlite3
import traceback
from datetime import datetime
from threading import Lock
from functools import wraps
import atexit

db_lock = Lock()
conn = sqlite3.connect("skillforge.db", check_same_thread=False)
c = conn.cursor()

# Таблицы
c.execute('''CREATE TABLE IF NOT EXISTS progress
             (user_id TEXT, skill TEXT, status TEXT, date TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS agent_prompts
             (agent_name TEXT PRIMARY KEY, prompt_template TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS error_logs
             (timestamp TEXT, error_type TEXT, message TEXT, traceback TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS test_results
             (user_id TEXT, topic TEXT, score INTEGER, total INTEGER, date TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS chat_history
             (user_id TEXT, role TEXT, content TEXT, date TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS test_answers
             (user_id TEXT, topic TEXT, question_index INTEGER,
              selected TEXT, correct BOOLEAN, date TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS knowledge_base
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              title TEXT NOT NULL,
              link TEXT NOT NULL,
              tags TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
conn.commit()

def close_db():
    conn.close()
    print("✅ Соединение с БД закрыто корректно")
atexit.register(close_db)

# ========== ЛОГИРОВАНИЕ ОШИБОК ==========
def log_error(error_type, message, tb):
    with db_lock:
        c.execute("INSERT INTO error_logs VALUES (?, ?, ?, ?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), error_type, message, tb))
        conn.commit()

def get_error_logs(limit=50):
    with db_lock:
        c.execute("SELECT timestamp, error_type, message, traceback FROM error_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
        return c.fetchall()

# ========== ДЕКОРАТОР ==========
def error_logged(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            tb = traceback.format_exc()
            log_error(type(e).__name__, str(e), tb)
            raise e
    return wrapper

# ========== ПРОМПТЫ ==========
DEFAULT_PROMPTS = {
    "plan_agent": "Ты HR-аналитик. Составь план развития для {grade}. Учти текущий уровень и цели.",
    "validator": "Оцени ответ на вопрос: {question}. Текст ответа: {content}. Дай краткий вердикт и рекомендацию.",
    "search_agent": "Найди бесплатные ресурсы по теме: {query}. Верни список ссылок и краткое описание.",
    "interview_agent": "Ты технический интервьюер. Задай 3 вопроса по теме {topic} для уровня {grade}."
}

def init_prompts():
    for name, prompt in DEFAULT_PROMPTS.items():
        c.execute("INSERT OR IGNORE INTO agent_prompts VALUES (?, ?)", (name, prompt))
    conn.commit()

def get_prompt(agent_name: str) -> str:
    with db_lock:
        c.execute("SELECT prompt_template FROM agent_prompts WHERE agent_name=?", (agent_name,))
        row = c.fetchone()
        return row[0] if row else ""

def update_prompt(agent_name: str, new_prompt: str):
    with db_lock:
        c.execute("UPDATE agent_prompts SET prompt_template=? WHERE agent_name=?", (new_prompt, agent_name))
        conn.commit()

# ========== ПРОГРЕСС ==========
def save_progress(user_id, skill, status):
    with db_lock:
        c.execute("INSERT INTO progress VALUES (?, ?, ?, ?)",
                  (user_id, skill, status, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()

def get_progress(user_id):
    with db_lock:
        c.execute("SELECT skill, status, date FROM progress WHERE user_id=? ORDER BY date DESC", (user_id,))
        return c.fetchall()

def get_all_progress():
    with db_lock:
        c.execute("SELECT user_id, skill, status, date FROM progress ORDER BY date DESC")
        return c.fetchall()

# ========== ИСТОРИЯ ЧАТА ==========
def save_chat_message(user_id, role, content):
    with db_lock:
        c.execute("INSERT INTO chat_history VALUES (?, ?, ?, ?)",
                  (user_id, role, content, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()

def get_chat_history(user_id, limit=20):
    with db_lock:
        c.execute("""
            SELECT role, content, date 
            FROM chat_history 
            WHERE user_id=? 
            ORDER BY date DESC 
            LIMIT ?
        """, (user_id, limit))
        return c.fetchall()

# ========== ТЕСТЫ ==========
def save_test_result(user_id, topic, score, total):
    with db_lock:
        c.execute("INSERT INTO test_results VALUES (?, ?, ?, ?, ?)",
                  (user_id, topic, score, total, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()

def save_test_answer(user_id, topic, question_index, selected, correct):
    with db_lock:
        c.execute("INSERT INTO test_answers VALUES (?, ?, ?, ?, ?, ?)",
                  (user_id, topic, question_index, selected, correct, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()

# ========== БАЗА ЗНАНИЙ ==========
DEFAULT_KNOWLEDGE_BASE = [
    {"title": "SQL для аналитиков — Stepik", "link": "https://stepik.org/course/123456", "tags": "sql,junior"},
    {"title": "BPMN 2.0 — полное руководство", "link": "https://habr.com/ru/post/bpmn/", "tags": "bpmn,middle"},
    {"title": "REST API Best Practices", "link": "https://restfulapi.net/", "tags": "api,middle"},
    {"title": "OpenAPI Specification 3.1", "link": "https://swagger.io/specification/", "tags": "api,openapi"},
    {"title": "Kafka basics", "link": "https://kafka.apache.org/quickstart", "tags": "kafka,senior"},
    {"title": "Микросервисная архитектура", "link": "https://microservices.io/", "tags": "arch,senior"},
    {"title": "Event Storming", "link": "https://www.eventstorming.com/", "tags": "ddd,senior"},
    {"title": "SQL Academy — тренажёр", "link": "https://sql-academy.org/", "tags": "sql,practice"},
]

def init_knowledge_base():
    with db_lock:
        c.execute("SELECT COUNT(*) FROM knowledge_base")
        count = c.fetchone()[0]
        if count == 0:
            for item in DEFAULT_KNOWLEDGE_BASE:
                c.execute("INSERT INTO knowledge_base (title, link, tags) VALUES (?, ?, ?)",
                          (item["title"], item["link"], item["tags"]))
            conn.commit()
            print("✅ Таблица knowledge_base заполнена начальными данными.")

def get_all_knowledge_base():
    with db_lock:
        c.execute("SELECT id, title, link, tags, created_at FROM knowledge_base ORDER BY id DESC")
        return c.fetchall()

def add_knowledge_item(title, link, tags):
    with db_lock:
        c.execute("INSERT INTO knowledge_base (title, link, tags) VALUES (?, ?, ?)",
                  (title, link, tags))
        conn.commit()
        return c.lastrowid

def search_knowledge_base_simple(query: str) -> list:
    query = query.lower()
    with db_lock:
        c.execute("""
            SELECT title, link FROM knowledge_base
            WHERE LOWER(title) LIKE ? OR LOWER(tags) LIKE ?
            ORDER BY id DESC
        """, (f"%{query}%", f"%{query}%"))
        return c.fetchall()