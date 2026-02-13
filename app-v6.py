import gradio as gr
print(f"✅ Используется Gradio версии: {gr.__version__}")

import sqlite3
import json
import csv
import os
import sys
import traceback
import atexit
import tempfile
from datetime import datetime
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from functools import wraps
from threading import Lock

# ========== УНИВЕРСАЛЬНАЯ РАБОТА С ЧАТОМ (КОРТЕЖНЫЙ ФОРМАТ) ==========
def add_chat_message(history, role, content):
    history.append({"role": role, "content": content})
    return history

def clear_chat():
    return []

# ========== ПРОВЕРКА ЗАВИСИМОСТЕЙ ==========
MISSING_MODULES = []

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    chromadb = None
    MISSING_MODULES.append("chromadb")

try:
    import sentence_transformers
except ImportError:
    sentence_transformers = None
    MISSING_MODULES.append("sentence-transformers")

try:
    import whisper
except ImportError:
    whisper = None
    MISSING_MODULES.append("openai-whisper")

try:
    from gtts import gTTS
    import pydub
    from pydub.playback import play
except ImportError:
    gTTS = None
    MISSING_MODULES.append("gtts/pydub")

try:
    import sqlparse
except ImportError:
    sqlparse = None
    MISSING_MODULES.append("sqlparse")

if MISSING_MODULES:
    print("⚠️ Внимание! Отсутствуют модули:", ", ".join(MISSING_MODULES))
    print("Некоторые функции будут работать в упрощённом режиме.")
    print("Для полной функциональности выполните: pip install " + " ".join(MISSING_MODULES))

# ========== БАЗА ДАННЫХ ==========
db_lock = Lock()
conn = sqlite3.connect("skillforge.db", check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS progress
             (user_id TEXT, skill TEXT, status TEXT, date TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS agent_prompts
             (agent_name TEXT PRIMARY KEY, prompt_template TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS error_logs
             (timestamp TEXT, error_type TEXT, message TEXT, traceback TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS test_results
             (user_id TEXT, topic TEXT, score INTEGER, total INTEGER, date TEXT)''')
conn.commit()

def close_db():
    conn.close()
    print("✅ Соединение с БД закрыто корректно")

atexit.register(close_db)

default_prompts = {
    "plan_agent": "Ты HR-аналитик. Составь план развития для {grade}. Учти текущий уровень и цели.",
    "validator": "Оцени ответ на вопрос: {question}. Текст ответа: {content}. Дай краткий вердикт и рекомендацию.",
    "search_agent": "Найди бесплатные ресурсы по теме: {query}. Верни список ссылок и краткое описание.",
    "interview_agent": "Ты технический интервьюер. Задай 3 вопроса по теме {topic} для уровня {grade}."
}
for name, prompt in default_prompts.items():
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

def load_prompt(agent_name):
    return get_prompt(agent_name)

def save_prompt_ui(agent_name, new_prompt):
    update_prompt(agent_name, new_prompt)
    return f"Промпт для {agent_name} сохранён."

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

def show_progress(user_id):
    data = get_progress(user_id)
    if not data:
        return [["Нет записей", "", ""]]
    return data

def add_progress(user_id, skill, status):
    save_progress(user_id, skill, status)
    return f"Достижение '{skill}' добавлено!"

def save_test_result(user_id, topic, score, total):
    with db_lock:
        c.execute("INSERT INTO test_results VALUES (?, ?, ?, ?, ?)",
                  (user_id, topic, score, total, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()

def log_error(error_type, message, tb):
    with db_lock:
        c.execute("INSERT INTO error_logs VALUES (?, ?, ?, ?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), error_type, message, tb))
        conn.commit()

def get_error_logs(limit=50):
    with db_lock:
        c.execute("SELECT timestamp, error_type, message, traceback FROM error_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
        return c.fetchall()

# ========== ДЕКОРАТОР ДЛЯ ЛОГИРОВАНИЯ ОШИБОК ==========
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

# ========== ВЕКТОРНАЯ БАЗА ЗНАНИЙ (CHROMADB) ==========
def init_vector_db():
    if chromadb is None or sentence_transformers is None:
        return None
    try:
        client = chromadb.PersistentClient(path="./chroma_db")
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="intfloat/multilingual-e5-small"
        )
        try:
            collection = client.get_collection("analyst_skills", embedding_function=ef)
        except:
            collection = client.create_collection("analyst_skills", embedding_function=ef)
            documents = []
            metadatas = []
            ids = []
            for i, item in enumerate(KNOWLEDGE_BASE):
                documents.append(f"{item['title']} {' '.join(item['tags'])}")
                metadatas.append({"link": item["link"], "title": item["title"]})
                ids.append(f"doc_{i}")
            collection.add(documents=documents, metadatas=metadatas, ids=ids)
        return collection
    except Exception as e:
        log_error("VectorDBInit", str(e), traceback.format_exc())
        return None

KNOWLEDGE_BASE = [
    {"title": "SQL для аналитиков — Stepik", "link": "https://stepik.org/course/123456", "tags": ["sql", "junior"]},
    {"title": "BPMN 2.0 — полное руководство", "link": "https://habr.com/ru/post/bpmn/", "tags": ["bpmn", "middle"]},
    {"title": "REST API Best Practices", "link": "https://restfulapi.net/", "tags": ["api", "middle"]},
    {"title": "OpenAPI Specification 3.1", "link": "https://swagger.io/specification/", "tags": ["api", "openapi"]},
    {"title": "Kafka basics", "link": "https://kafka.apache.org/quickstart", "tags": ["kafka", "senior"]},
    {"title": "Микросервисная архитектура", "link": "https://microservices.io/", "tags": ["arch", "senior"]},
    {"title": "Event Storming", "link": "https://www.eventstorming.com/", "tags": ["ddd", "senior"]},
    {"title": "SQL Academy — тренажёр", "link": "https://sql-academy.org/", "tags": ["sql", "practice"]},
]

vector_collection = init_vector_db()

def search_resources(query: str) -> str:
    if vector_collection is not None:
        try:
            results = vector_collection.query(query_texts=[query], n_results=5)
            output = []
            for i in range(len(results['documents'][0])):
                title = results['metadatas'][0][i]['title']
                link = results['metadatas'][0][i]['link']
                output.append(f"- [{title}]({link})")
            return "\n".join(output) if output else "Ничего не найдено."
        except Exception as e:
            log_error("VectorSearch", str(e), traceback.format_exc())
    query = query.lower()
    results = []
    for item in KNOWLEDGE_BASE:
        if any(tag in query for tag in item["tags"]) or query in item["title"].lower():
            results.append(f"- [{item['title']}]({item['link']})")
    return "\n".join(results) if results else "Ничего не найдено. Попробуйте изменить запрос."

# ========== ГОЛОСОВОЙ ВВОД/ВЫВОД ==========
def transcribe_audio(audio_path):
    if whisper is None:
        return "⚠️ Whisper не установлен. Голосовой ввод недоступен."
    try:
        model = whisper.load_model("small")
        result = model.transcribe(audio_path)
        return result["text"]
    except Exception as e:
        log_error("Whisper", str(e), traceback.format_exc())
        return f"Ошибка распознавания: {e}"

def text_to_speech(text, lang="ru"):
    if gTTS is None:
        return None
    try:
        tts = gTTS(text=text, lang=lang)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_file.close()
        tts.save(temp_file.name)
        return temp_file.name
    except Exception as e:
        log_error("TTS", str(e), traceback.format_exc())
        return None

# ========== АГЕНТЫ ==========
@error_logged
def plan_agent(user_input: str) -> str:
    prompt_template = get_prompt("plan_agent")
    if "junior" in user_input.lower():
        grade = "Junior"
        plan = """
📚 **Неделя 1:** Основы SQL (SELECT, JOIN, агрегация) — тренажёр SQL-EX  
📚 **Неделя 2:** Нотация BPMN 2.0, создание диаграмм — видео на YouTube  
📚 **Неделя 3:** REST API, OpenAPI, Postman — документация Swagger  
📚 **Неделя 4:** Подготовка к аттестации, mock-интервью, soft skills  
"""
    elif "middle" in user_input.lower():
        grade = "Middle"
        plan = """
🚀 **Неделя 1:** Проектирование API, идемпотентность, пагинация  
🚀 **Неделя 2:** Kafka basics, event-driven архитектура, протоколы  
🚀 **Неделя 3:** Event Storming, DDD, bounded context  
🚀 **Неделя 4:** Проведение интервью, менторство, code review  
"""
    else:
        grade = "General"
        plan = """
🎯 **Неделя 1:** SQL (оптимизация запросов, индексы)  
🎯 **Неделя 2:** BPMN, CMMN, DMN — сравнение  
🎯 **Неделя 3:** REST, gRPC, GraphQL — когда что выбирать  
🎯 **Неделя 4:** Софт-скиллы: коммуникация с заказчиком, управление ожиданиями  
"""
    return f"**Промпт агента:** {prompt_template.format(grade=grade)}\n\n{plan}"

@error_logged
def validate_file(content: str, filename: str, question: str) -> str:
    prompt = get_prompt("validator")
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext in ["sql", "txt"] and ("SELECT" in content or "select" in content):
        if sqlparse:
            try:
                parsed = sqlparse.parse(content)
                if parsed:
                    verdict = "✅ Синтаксис SQL корректен. "
                    if "join" in content.lower():
                        verdict += "Использован JOIN, проверьте типы."
                    else:
                        verdict += "Рекомендуется добавить условия WHERE и индексы."
                else:
                    verdict = "❌ Некорректный SQL-запрос."
            except:
                verdict = "❌ Ошибка парсинга SQL."
        else:
            verdict = "✅ SQL-запрос получен (установите sqlparse для детальной проверки)."
    elif ext in ["bpmn", "xml", "txt"] and ("Actor" in content or "Flow" in content or "process" in content.lower()):
        verdict = "✅ BPMN-диаграмма описана верно. Добавьте обработку ошибок и альтернативные потоки."
    else:
        verdict = "❌ Формат не распознан. Загрузите SQL-запрос (.sql), BPMN-схему (.bpmn) или текстовое описание."
    return f"**Промпт агента:** {prompt.format(question=question, content=content[:50])}\n\n**Вердикт:** {verdict}"

@error_logged
def search_agent(query: str) -> str:
    prompt = get_prompt("search_agent")
    resources = search_resources(query)
    return f"**Промпт агента:** {prompt.format(query=query)}\n\n**Найденные ресурсы:**\n{resources}"

@error_logged
def interview_agent(topic: str, grade: str) -> str:
    prompt = get_prompt("interview_agent")
    questions_db = {
        "sql": [
            "Чем отличается INNER JOIN от LEFT JOIN?",
            "Что такое индекс и когда его использовать?",
            "Объясните разницу между UNION и UNION ALL."
        ],
        "bpmn": [
            "Какие основные элементы BPMN 2.0 вы знаете?",
            "Чем отличается процесс от подпроцесса?",
            "Как моделировать исключительные ситуации в BPMN?"
        ],
        "api": [
            "Что такое идемпотентность в REST?",
            "Какие статус-коды HTTP вы используете чаще всего?",
            "В чём разница между PUT и PATCH?"
        ]
    }
    topic_lower = topic.lower()
    questions = []
    for key in questions_db:
        if key in topic_lower:
            questions = questions_db[key][:3]
            break
    if not questions:
        questions = [
            "Расскажите о вашем опыте системного анализа.",
            "Как вы собираете требования?",
            "Как документируете архитектурные решения?"
        ]
    return f"**Тема:** {topic} ({grade})\n\n**Вопросы:**\n" + "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])

# ========== ТЕСТИРОВАНИЕ ==========
test_questions = {
    "SQL": [
        {"question": "Какой оператор используется для выборки данных?", "options": ["SELECT", "INSERT", "UPDATE", "DELETE"], "answer": 0},
        {"question": "Какой оператор объединяет таблицы по условию?", "options": ["JOIN", "UNION", "MERGE", "COMBINE"], "answer": 0},
        {"question": "Какой оператор сортирует результат?", "options": ["ORDER BY", "GROUP BY", "SORT BY", "HAVING"], "answer": 0}
    ],
    "BPMN": [
        {"question": "Какой элемент BPMN обозначает событие?", "options": ["Круг", "Прямоугольник", "Ромб", "Стрелка"], "answer": 0},
        {"question": "Что обозначает пунктирная стрелка?", "options": ["Поток сообщений", "Поток управления", "Ассоциация", "Комментарий"], "answer": 2}
    ],
    "REST": [
        {"question": "Какой метод HTTP используется для обновления ресурса?", "options": ["PUT", "GET", "POST", "DELETE"], "answer": 0},
        {"question": "Какой статус-код означает 'успешно создано'?", "options": ["201", "200", "204", "404"], "answer": 0}
    ]
}

def run_test(user_id, topic, answers):
    questions = test_questions.get(topic, [])
    if not questions:
        return "Тема не найдена.", 0, 0
    score = 0
    for i, q in enumerate(questions):
        if i < len(answers) and answers[i] == q["answer"]:
            score += 1
    total = len(questions)
    save_test_result(user_id, topic, score, total)
    return f"✅ Вы набрали {score} из {total}. Результат сохранён.", score, total

# ========== GRADIO ИНТЕРФЕЙС ==========
def chat_respond(message, history):
    if "план" in message.lower():
        response = plan_agent(message)
    elif "найди" in message.lower() or "ресурс" in message.lower() or "статья" in message.lower():
        response = search_agent(message)
    else:
        response = "Я могу: составить план развития, найти учебные материалы, проверить файл, провести голосовое собеседование. Выберите вкладку."
    return response

def file_verification(file, task_desc):
    try:
        with open(file.name, 'r', encoding='utf-8') as f:
            content = f.read()
        filename = file.name.split("\\")[-1]
        return validate_file(content, filename, task_desc)
    except Exception as e:
        log_error("FileVerification", str(e), traceback.format_exc())
        return f"Ошибка чтения файла: {e}"

def voice_chat_respond(audio, history):
    try:
        text = transcribe_audio(audio)
        if text.startswith("Ошибка") or text.startswith("⚠️"):
            return history, None
        bot_msg = chat_respond(text, history)
        audio_path = text_to_speech(bot_msg)
        history = add_chat_message(history, "user", text)
        history = add_chat_message(history, "assistant", bot_msg)
        return history, audio_path
    except Exception as e:
        tb = traceback.format_exc()
        log_error(type(e).__name__, str(e), tb)
        return history, None

def export_progress_csv():
    data = get_all_progress()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Email", "Навык", "Статус", "Дата"])
    writer.writerows(data)
    return output.getvalue()

def copy_error_to_clipboard(error_text):
    return None

# ========== ПОСТРОЕНИЕ ИНТЕРФЕЙСА ==========
with gr.Blocks(title="SkillForge Analyst") as demo:
    gr.Markdown("# 🤖 SkillForge Analyst — AI-наставник системных аналитиков")
    gr.Markdown("Векторный поиск, голосовое общение, тесты, админ-панель с логом ошибок.")
    # ----- Чат-тьютор -----
    with gr.Tab("💬 Чат-тьютор"):
        chatbot = gr.Chatbot(value=[])
        msg = gr.Textbox(placeholder="Напишите: составь план для junior / найди статьи по sql")
        clear = gr.Button("Очистить")
        def respond(message, chat_history):
            try:
               bot_msg = chat_respond(message, chat_history)
               chat_history.append({"role": "user", "content": message})
               chat_history.append({"role": "assistant", "content": bot_msg})
               return "", chat_history
            except Exception as e:
               tb = traceback.format_exc()
               log_error(type(e).__name__, str(e), tb)
               chat_history.append({"role": "user", "content": message})
               chat_history.append({"role": "assistant", "content": "Ошибка. Администратор уведомлён."})
               return "", chat_history
        msg.submit(respond, [msg, chatbot], [msg, chatbot])
        
        def clear_all():
            return [], ""
        
        clear.click(clear_all, None, [chatbot, msg], queue=False)
    # ----- Голосовое собеседование -----
    with gr.Tab("🎤 Голосовое собеседование"):
        gr.Markdown("Нажмите на микрофон и задайте вопрос голосом. Ответ будет озвучен.")
        audio_input = gr.Audio(sources=["microphone", "upload"], type="filepath")
        with gr.Row():
            voice_chatbot = gr.Chatbot(label="Диалог", value=[])
            audio_output = gr.Audio(label="Ответ", type="filepath", autoplay=True)
        voice_btn = gr.Button("Отправить голос")
        voice_btn.click(
            voice_chat_respond,
            [audio_input, voice_chatbot],
            [voice_chatbot, audio_output]
        )
    # ----- Проверка артефактов -----
    with gr.Tab("📁 Проверка артефактов"):
        gr.Markdown("Загрузите SQL (.sql), BPMN (.bpmn) или текстовое описание.")
        file_input = gr.File(label="Файл")
        task_desc = gr.Textbox(label="Что нужно было сделать? (описание задачи)")
        check_btn = gr.Button("Проверить")
        output = gr.Textbox(label="Результат проверки", lines=8)
        check_btn.click(file_verification, [file_input, task_desc], output)
    # ----- Тестирование -----
    with gr.Tab("📝 Тестирование"):
        gr.Markdown("### Проверьте свои знания")
        with gr.Row():
            user_id_test = gr.Textbox(label="Ваш Email", placeholder="analyst@company.ru")
            topic_selector = gr.Dropdown(choices=["SQL", "BPMN", "REST"], label="Выберите тему")
            reset_test_btn = gr.Button("🔄 Сбросить тест", variant="secondary")

        # Состояния
        current_q_index = gr.State(0)
        score = gr.State(0)

        # Элементы интерфейса
        question_html = gr.HTML()
        options = gr.Radio(choices=[], label="Выберите ответ")
        submit_answer = gr.Button("Ответить")
        test_result = gr.Textbox(label="Результат")

        # Функция загрузки вопроса
        def load_question(topic, idx):
            try:
                qs = test_questions.get(topic, [])
                if idx < len(qs):
                    q = qs[idx]
                    return f"**Вопрос {idx+1}:** {q['question']}", q['options'], idx
                else:
                    return "Тест завершён! Нажмите 'Сбросить тест' для нового теста.", [], idx
            except Exception as e:
                tb = traceback.format_exc()
                log_error(type(e).__name__, str(e), tb)
                return "Ошибка загрузки вопроса. Попробуйте сбросить тест.", [], idx

        # При смене темы: сбрасываем индекс и счёт, загружаем первый вопрос
        def change_topic(topic):
            try:
                # Сброс индекса и счёта
                new_idx = 0
                new_score = 0
                q_text, opts, _ = load_question(topic, 0)
                return new_idx, new_score, q_text, opts, ""  # очищаем результат
            except Exception as e:
                tb = traceback.format_exc()
                log_error(type(e).__name__, str(e), tb)
                return 0, 0, "Ошибка загрузки темы.", [], ""

        topic_selector.change(
            change_topic,
            topic_selector,
            [current_q_index, score, question_html, options, test_result]
        )

        # Проверка ответа
        def check_answer(topic, idx, selected, current_score, user_email):
            try:
                qs = test_questions.get(topic, [])
                if idx < len(qs):
                    correct = qs[idx]["answer"]
                    if selected is not None and qs[idx]["options"].index(selected) == correct:
                        current_score += 1
                        feedback = "✅ Верно!"
                    else:
                        correct_answer = qs[idx]["options"][correct]
                        feedback = f"❌ Неверно. Правильный ответ: {correct_answer}"
                    next_idx = idx + 1
                    if next_idx < len(qs):
                        q_text, opts, _ = load_question(topic, next_idx)
                        return feedback, current_score, next_idx, q_text, opts
                    else:
                        save_test_result(user_email, topic, current_score, len(qs))
                        return f"🎉 Тест завершён! Результат: {current_score}/{len(qs)}. Сохранено.", current_score, next_idx, "", []
                return "Ошибка: неверный индекс вопроса.", current_score, idx, "", []
            except Exception as e:
                tb = traceback.format_exc()
                log_error(type(e).__name__, str(e), tb)
                return f"Ошибка при проверке ответа: {e}", current_score, idx, "", []

        submit_answer.click(
            check_answer,
            [topic_selector, current_q_index, options, score, user_id_test],
            [test_result, score, current_q_index, question_html, options]
        )

        # Сброс теста
        def reset_test(topic):
            try:
                new_idx = 0
                new_score = 0
                q_text, opts, _ = load_question(topic, 0)
                return new_idx, new_score, q_text, opts, ""  # очищаем результат
            except Exception as e:
                tb = traceback.format_exc()
                log_error(type(e).__name__, str(e), tb)
                return 0, 0, "Ошибка сброса теста.", [], ""

        reset_test_btn.click(
            reset_test,
            [topic_selector],
            [current_q_index, score, question_html, options, test_result]
        )

    # ----- Мой прогресс -----
    with gr.Tab("📊 Мой прогресс"):
        with gr.Row():
            user_id_progress = gr.Textbox(label="Email сотрудника", placeholder="analyst@company.ru")
            show_btn = gr.Button("Показать достижения")
        achievements = gr.Dataframe(headers=["Навык", "Статус", "Дата"], row_count=5)
        show_btn.click(show_progress, user_id_progress, achievements)
        gr.Markdown("---\n**Добавить новое достижение:**")
        with gr.Row():
            new_user = gr.Textbox(label="Email")
            new_skill = gr.Textbox(label="Навык")
            new_status = gr.Dropdown(["Изучено", "В процессе", "Запланировано"], label="Статус")
            add_btn = gr.Button("Добавить")
            add_status = gr.Textbox(label="")
        add_btn.click(add_progress, [new_user, new_skill, new_status], add_status)
        gr.Markdown("---\n**Командный прогресс**")
        team_btn = gr.Button("Показать всю команду")
        team_table = gr.Dataframe(headers=["Email", "Навык", "Статус", "Дата"])
        team_btn.click(get_all_progress, [], team_table)
        export_btn = gr.Button("📥 Экспорт в CSV")
        export_file = gr.File()
        export_btn.click(lambda: export_progress_csv(), [], export_file)
    # ----- Администрирование -----
    with gr.Tab("⚙️ Администрирование"):
        gr.Markdown("### Редактирование промптов агентов")
        agent_selector = gr.Dropdown(
            choices=["plan_agent", "validator", "search_agent", "interview_agent"],
            label="Выберите агента"
        )
        current_prompt = gr.Textbox(label="Текущий промпт", lines=5, interactive=False)
        new_prompt = gr.Textbox(label="Новый промпт", lines=5, placeholder="Введите новый текст промпта...")
        save_btn = gr.Button("💾 Сохранить изменения")
        save_status = gr.Textbox(label="Статус")
        agent_selector.change(load_prompt, agent_selector, current_prompt)
        save_btn.click(save_prompt_ui, [agent_selector, new_prompt], save_status)
        gr.Markdown("---")
        gr.Markdown("### 🚨 Лог ошибок приложения")
        error_table = gr.Dataframe(
            headers=["Время", "Тип", "Сообщение", "Traceback"],
            value=get_error_logs,
            every=10
        )
        refresh_btn = gr.Button("🔄 Обновить лог")
        refresh_btn.click(get_error_logs, [], error_table)
        error_text_to_copy = gr.Textbox(label="Текст ошибки для копирования", lines=2)
        copy_btn = gr.Button("📋 Копировать в буфер")
        copy_status = gr.Textbox(label="Статус")
        copy_btn.click(
            None,
            [error_text_to_copy],
            copy_status,
            js="(text) => { navigator.clipboard.writeText(text); return 'Скопировано!'; }"
        )
        gr.Markdown("---")
        gr.Markdown("### 📚 Управление базой знаний")
        gr.Markdown(f"Сейчас база содержит {len(KNOWLEDGE_BASE)} записей.")
        gr.Markdown("---")
        gr.Markdown("### 🛑 Управление сервером")
        gr.Markdown("При нажатии приложение будет остановлено.")
        def shutdown_server():
            log_error("INFO", "Сервер остановлен администратором", "")
            import time
            time.sleep(0.5)
            os._exit(0)
        shutdown_btn = gr.Button("🛑 Остановить сервер", variant="stop")
        shutdown_btn.click(
            fn=shutdown_server,
            inputs=[],
            outputs=[],
            js="() => { if(!confirm('Вы уверены?')) throw new Error('Отменено'); }"
        )
# ========== ЗАПУСК ==========
if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft())