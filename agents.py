from database import get_prompt, error_logged

# Эта функция будет импортирована в main.py для chat_respond
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
    # Импортируем внутри, чтобы избежать циклических зависимостей
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