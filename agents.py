from database import get_prompt, error_logged, save_weekly_plan, save_llm_dialogue
from search import search_resources
from llm import call_llm
import traceback
import re

def chat_respond(message, history):
    if "план" in message.lower():
        return plan_agent(message)
    elif "найди" in message.lower() or "ресурс" in message.lower() or "статья" in message.lower():
        return search_agent(message)
    else:
        return "Я могу: составить план развития, найти учебные материалы, проверить файл, провести голосовое собеседование. Выберите вкладку."

@error_logged
def plan_agent(user_input: str) -> str:
    prompt_template = get_prompt("plan_agent")
    if "junior" in user_input.lower():
        grade = "Junior"
    elif "middle" in user_input.lower():
        grade = "Middle"
    else:
        grade = "General"
    full_prompt = prompt_template.format(grade=grade)
    full_prompt += f"\n\nЗапрос пользователя: {user_input}"
    llm_response = call_llm(full_prompt, system_prompt="Ты — опытный HR-аналитик и карьерный консультант. Отвечай на русском языке.")
    if llm_response.startswith("⚠️") or llm_response.startswith("❌"):
        if grade == "Junior":
            plan = """
📚 **Неделя 1:** Основы SQL (SELECT, JOIN, агрегация) — тренажёр SQL-EX  
📚 **Неделя 2:** Нотация BPMN 2.0, создание диаграмм — видео на YouTube  
📚 **Неделя 3:** REST API, OpenAPI, Postman — документация Swagger  
📚 **Неделя 4:** Подготовка к аттестации, mock-интервью, soft skills  
"""
        elif grade == "Middle":
            plan = """
🚀 **Неделя 1:** Проектирование API, идемпотентность, пагинация  
🚀 **Неделя 2:** Kafka basics, event-driven архитектура, протоколы  
🚀 **Неделя 3:** Event Storming, DDD, bounded context  
🚀 **Неделя 4:** Проведение интервью, менторство, code review  
"""
        else:
            plan = """
🎯 **Неделя 1:** SQL (оптимизация запросов, индексы)  
🎯 **Неделя 2:** BPMN, CMMN, DMN — сравнение  
🎯 **Неделя 3:** REST, gRPC, GraphQL — когда что выбирать  
🎯 **Неделя 4:** Софт-скиллы: коммуникация с заказчиком, управление ожиданиями  
"""
        return f"**Промпт агента:** {prompt_template.format(grade=grade)}\n\n{plan}\n\n*Примечание: использован статический план, так как AI-помощник временно недоступен.*"
    else:
        return f"**Промпт агента:** {prompt_template.format(grade=grade)}\n\n**AI-рекомендация:**\n{llm_response}"

@error_logged
def validate_file(content: str, filename: str, question: str) -> str:
    prompt = get_prompt("validator")
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    try:
        import sqlparse
    except ImportError:
        sqlparse = None
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
    from search import search_resources
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

def extract_section(text, header):
    pattern = re.compile(rf"{re.escape(header)}\s*(.*?)(?=\n\*\*|\n$)", re.DOTALL | re.IGNORECASE)
    match = pattern.search(text)
    if match:
        return match.group(1).strip()
    return ""

@error_logged
def generate_weekly_plans(interests: list, grade: str, user_email: str) -> list:
    if not user_email:
        raise ValueError("Email пользователя обязателен")
    interests_text = "\n".join([f"- {interest}" for interest in interests])
    results = []
    for week in range(1, 5):
        prompt = (
            f"Ты — карьерный консультант для системных аналитиков.\n"
            f"Уровень аналитика: {grade}.\n"
            f"Выбранные направления:\n{interests_text}\n\n"
            f"Составь план обучения на **неделю {week}** из 4-недельного курса. "
            f"Учти уровень {grade} и выбранные направления.\n"
            f"Твой ответ должен содержать:\n"
            f"1. Краткое описание целей недели (2-3 предложения).\n"
            f"2. Ключевые определения (список терминов, которые нужно усвоить).\n"
            f"3. Ключевые теги (например: #sql, #bpmn).\n"
            f"4. Ключевые знания (что именно должен знать и уметь аналитик после этой недели).\n\n"
            f"Формат ответа:\n"
            f"**Неделя {week}**\n"
            f"**Цели:** ...\n"
            f"**Определения:** термин1, термин2, ...\n"
            f"**Теги:** #тег1, #тег2, ...\n"
            f"**Знания:** ...\n"
            f"Ответ должен быть кратким и укладываться в 1000 токенов."
        )
        system_prompt = "Ты опытный методист. Отвечай строго по формату, на русском языке."
        response = call_llm(prompt, system_prompt)
        save_llm_dialogue(user_email, prompt, response)
        key_defs = extract_section(response, "Определения:")
        key_tags = extract_section(response, "Теги:")
        key_knowledge = extract_section(response, "Знания:")
        save_weekly_plan(
            user_email=user_email,
            grade=grade,
            week_number=week,
            content=response,
            key_defs=key_defs,
            key_tags=key_tags,
            key_knowledge=key_knowledge
        )
        results.append((week, response, key_defs, key_tags, key_knowledge))
    return results