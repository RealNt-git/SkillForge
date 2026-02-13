import gradio as gr
import traceback
from database import (
    init_prompts, init_knowledge_base, init_interests,
    log_error,
    save_chat_message, get_chat_history, get_all_progress, get_error_logs,
    get_all_knowledge_base, c, db_lock,
    get_active_interests, get_all_interests,
    get_weekly_plans, get_llm_dialogues
)
print("database loaded")
from agents import chat_respond, validate_file, generate_weekly_plans
from voice import transcribe_audio, text_to_speech, add_chat_message
from tests import (
    test_questions, start_test, load_question, reset_test, check_answer
)
from progress import (
    show_progress, add_progress_ui, export_progress_csv, get_test_details
)
from admin import (
    load_prompt, save_prompt_ui, shutdown_server, add_kb_item_ui,
    get_all_interests_ui, add_interest_ui, toggle_interest_active_ui, delete_interest_ui
)

print(f"✅ Используется Gradio версии: {gr.__version__}")

# Инициализация БД
init_prompts()
init_knowledge_base()
init_interests()

# ========== CSS ==========
custom_css = """
#plan-output {
    max-height: 500px;
    overflow-y: auto;
    border: 1px solid #ccc;
    padding: 10px;
    border-radius: 5px;
}
#llm-dialogues {
    max-height: 500px;
    overflow-y: auto;
    border: 1px solid #ccc;
    padding: 10px;
    border-radius: 5px;
}
"""

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def file_verification(file, task_desc):
    try:
        with open(file.name, 'r', encoding='utf-8') as f:
            content = f.read()
        filename = file.name.split("\\")[-1]
        return validate_file(content, filename, task_desc)
    except Exception as e:
        log_error("FileVerification", str(e), traceback.format_exc())
        return f"Ошибка чтения файла: {e}"

def get_table_data(table_name):
    with db_lock:
        c.execute(f"SELECT * FROM {table_name} ORDER BY rowid DESC LIMIT 100")
        rows = c.fetchall()
        c.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in c.fetchall()]
        return rows, columns

def show_table(table_name):
    data, headers = get_table_data(table_name)
    if data:
        return gr.update(value=data, headers=headers)
    else:
        return gr.update(value=[["Нет данных"]], headers=["Сообщение"])

# ========== ИНТЕРФЕЙС ==========
with gr.Blocks(title="SkillForge Analyst") as demo:
    gr.Markdown("# 🤖 SkillForge Analyst — AI-наставник системных аналитиков")
    gr.Markdown("Векторный поиск, голосовое общение, тесты, админ-панель с логом ошибок.")
   
    # ----- Вкладка 1: Подбор плана по интересам (обновлённая) -----
    with gr.Tab("🎯 Подбор плана по интересам"):
        gr.Markdown("### Выберите направления, которые вам интересны")
        questions_state = gr.State(value=get_active_interests())
        interests = gr.CheckboxGroup(choices=questions_state.value, label="Отметьте интересующие направления")
        refresh_btn = gr.Button("🔄 Обновить список направлений", variant="secondary")
        with gr.Row():
            user_email = gr.Textbox(label="Ваш Email", placeholder="analyst@company.ru", scale=2)
            grade = gr.Radio(choices=["Junior", "Middle", "Expert"], label="Уровень", value="Junior", scale=1)
        generate_btn = gr.Button("🎯 Сгенерировать 4-недельный план", variant="primary")
        output_plan = gr.Markdown(label="Ваш план развития", elem_id="plan-output")
        
        def refresh_interests():
            new_list = get_active_interests()
            return gr.update(choices=new_list), new_list
        refresh_btn.click(refresh_interests, outputs=[interests, questions_state])
        
        def generate_full_plan(selected, email, grade_value):
            if not selected:
                return "⚠️ Пожалуйста, выберите хотя бы одно направление."
            if not email:
                return "⚠️ Укажите ваш email для сохранения плана."
            try:
                weeks = generate_weekly_plans(selected, grade_value, email)
                output = ""
                for week, content, defs, tags, knowledge in weeks:
                    output += f"## Неделя {week}\n\n{content}\n\n---\n"
                return output
            except Exception as e:
                log_error("GeneratePlan", str(e), traceback.format_exc())
                return f"❌ Ошибка при генерации плана: {e}"
        generate_btn.click(generate_full_plan, inputs=[interests, user_email, grade], outputs=output_plan)
    
    # ----- Вкладка 2: Диалоги с LLM -----
    with gr.Tab("📜 Диалоги с LLM"):
        gr.Markdown("### История запросов к языковой модели")
        with gr.Row():
            filter_email = gr.Textbox(label="Фильтр по email (оставьте пустым для всех)", placeholder="analyst@company.ru")
            refresh_dialogues_btn = gr.Button("🔄 Обновить")
        dialogues_table = gr.Dataframe(
            headers=["Email", "Запрос", "Ответ", "Дата"] if not filter_email else ["Запрос", "Ответ", "Дата"],
            value=get_llm_dialogues,
            every=5,
            elem_id="llm-dialogues"
        )
        def refresh_dialogues(email):
            if email:
                data = get_llm_dialogues(email)
                headers = ["Запрос", "Ответ", "Дата"]
            else:
                data = get_llm_dialogues()
                headers = ["Email", "Запрос", "Ответ", "Дата"]
            return gr.update(value=data, headers=headers)
        refresh_dialogues_btn.click(refresh_dialogues, inputs=[filter_email], outputs=dialogues_table)
    
    # ----- Вкладка 3: Чат-тьютор -----
    with gr.Tab("💬 Чат-тьютор"):
        chatbot = gr.Chatbot(value=[])
        with gr.Row():
            user_email_chat = gr.Textbox(label="Ваш Email", placeholder="analyst@company.ru", scale=3)
            msg = gr.Textbox(placeholder="Напишите сообщение...", scale=5)
        clear = gr.Button("Очистить")
        def respond(message, chat_history, user_email):
            try:
                bot_msg = chat_respond(message, chat_history)
                chat_history.append({"role": "user", "content": message})
                chat_history.append({"role": "assistant", "content": bot_msg})
                if user_email:
                    save_chat_message(user_email, "user", message)
                    save_chat_message(user_email, "assistant", bot_msg)
                return "", chat_history, user_email
            except Exception as e:
                tb = traceback.format_exc()
                log_error(type(e).__name__, str(e), tb)
                chat_history.append({"role": "user", "content": message})
                chat_history.append({"role": "assistant", "content": "Ошибка. Администратор уведомлён."})
                return "", chat_history, user_email
        msg.submit(respond, [msg, chatbot, user_email_chat], [msg, chatbot, user_email_chat])
        def clear_all():
            return [], "", None
        clear.click(clear_all, None, [chatbot, msg, user_email_chat], queue=False)

    # ----- Вкладка 4: Голосовое собеседование -----
    with gr.Tab("🎤 Голосовое собеседование"):
        gr.Markdown("Нажмите на микрофон и задайте вопрос голосом. Ответ будет озвучен.")
        with gr.Row():
            user_email_voice = gr.Textbox(label="Ваш Email", placeholder="analyst@company.ru", scale=3)
            audio_input = gr.Audio(sources=["microphone", "upload"], type="filepath", scale=5)
        with gr.Row():
            voice_chatbot = gr.Chatbot(label="Диалог", value=[])
            audio_output = gr.Audio(label="Ответ", type="filepath", autoplay=True)
        voice_btn = gr.Button("Отправить голос")
        def voice_respond(audio, history, user_email):
            try:
                text = transcribe_audio(audio)
                if text.startswith("Ошибка") or text.startswith("⚠️"):
                    return history, None, user_email
                bot_msg = chat_respond(text, history)
                audio_path = text_to_speech(bot_msg)
                history = add_chat_message(history, "user", text)
                history = add_chat_message(history, "assistant", bot_msg)
                if user_email:
                    save_chat_message(user_email, "user", text)
                    save_chat_message(user_email, "assistant", bot_msg)
                return history, audio_path, user_email
            except Exception as e:
                tb = traceback.format_exc()
                log_error(type(e).__name__, str(e), tb)
                return history, None, user_email
        voice_btn.click(voice_respond, [audio_input, voice_chatbot, user_email_voice],
                        [voice_chatbot, audio_output, user_email_voice])

    # ----- Вкладка 5: Проверка артефактов -----
    with gr.Tab("📁 Проверка артефактов"):
        gr.Markdown("Загрузите SQL (.sql), BPMN (.bpmn) или текстовое описание.")
        file_input = gr.File(label="Файл")
        task_desc = gr.Textbox(label="Что нужно было сделать? (описание задачи)")
        check_btn = gr.Button("Проверить")
        output = gr.Textbox(label="Результат проверки", lines=8)
        check_btn.click(file_verification, [file_input, task_desc], output)

    # ----- Вкладка 6: Тестирование -----
    with gr.Tab("📝 Тестирование"):
        gr.Markdown("### Проверьте свои знания")
        with gr.Row():
            user_id_test = gr.Textbox(label="Ваш Email", placeholder="analyst@company.ru")
            topic_selector = gr.Dropdown(choices=["SQL", "BPMN", "REST"], label="Выберите тему")
            reset_test_btn = gr.Button("🔄 Сбросить тест", variant="secondary")
        questions_state = gr.State([])
        answers_state = gr.State([])
        topic_selector.change(start_test, topic_selector, [questions_state, answers_state])
        question_html = gr.HTML()
        options = gr.Radio(choices=[], label="Выберите ответ")
        submit_answer = gr.Button("Ответить")
        test_result = gr.Textbox(label="Результат")
        current_q_index = gr.State(0)
        score = gr.State(0)
        topic_selector.change(lambda t: load_question(t, 0), topic_selector,
                              [question_html, options, current_q_index])
        reset_test_btn.click(reset_test, [topic_selector],
                             [current_q_index, score, question_html, options, test_result])
        submit_answer.click(check_answer,
                            [topic_selector, current_q_index, options, score, user_id_test],
                            [test_result, score, current_q_index, question_html, options])

    # ----- Вкладка 7: Мой прогресс -----
    with gr.Tab("📊 Мой прогресс"):
        with gr.Row():
            user_id_progress = gr.Textbox(label="Email сотрудника", placeholder="analyst@company.ru")
            show_btn = gr.Button("Показать активность")
        gr.Markdown("### 📝 История чата")
        chat_history_display = gr.Dataframe(headers=["Роль", "Сообщение", "Дата"], row_count=10, column_count=3)
        gr.Markdown("### 📊 Детализация тестов")
        test_details_display = gr.Dataframe(
            headers=["Тема", "Вопрос", "Ваш ответ", "Результат", "Дата"],
            row_count=10, column_count=5
        )
        gr.Markdown("### 🏆 Мои достижения")
        achievements = gr.Dataframe(headers=["Навык", "Статус", "Дата"], row_count=5, column_count=3)
        def show_full_progress(user_email):
            if not user_email:
                return ([["Нет записей", "", ""]],
                        [["Нет записей", "", "", "", ""]],
                        [["Нет записей", "", ""]])
            chat_data = get_chat_history(user_email, 20) or [["Нет записей", "", ""]]
            test_data = get_test_details(user_email, test_questions, 20) or [["Нет записей", "", "", "", ""]]
            prog_data = show_progress(user_email)
            return chat_data, test_data, prog_data
        show_btn.click(show_full_progress, [user_id_progress],
                       [chat_history_display, test_details_display, achievements])
        gr.Markdown("---\n**Добавить новое достижение:**")
        with gr.Row():
            new_user = gr.Textbox(label="Email")
            new_skill = gr.Textbox(label="Навык")
            new_status = gr.Dropdown(["Изучено", "В процессе", "Запланировано"], label="Статус")
            add_btn = gr.Button("Добавить")
            add_status = gr.Textbox(label="")
        add_btn.click(add_progress_ui, [new_user, new_skill, new_status], add_status)
        gr.Markdown("---\n**Командный прогресс**")
        team_btn = gr.Button("Показать всю команду")
        team_table = gr.Dataframe(headers=["Email", "Навык", "Статус", "Дата"])
        team_btn.click(get_all_progress, [], team_table)
        export_btn = gr.Button("📥 Экспорт в CSV")
        export_file = gr.File()
        export_btn.click(lambda: export_progress_csv(), [], export_file)

    # ----- Вкладка 8: Администрирование -----
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
        gr.Markdown("### 📚 Управление базой знаний")
        with gr.Row():
            kb_title = gr.Textbox(label="Название", placeholder="Введите название ресурса")
            kb_link = gr.Textbox(label="Ссылка", placeholder="https://...")
            kb_tags = gr.Textbox(label="Теги (через запятую)", placeholder="sql, junior")
            kb_add_btn = gr.Button("➕ Добавить ресурс")
        kb_status = gr.Textbox(label="", visible=False)
        kb_table = gr.Dataframe(
            headers=["ID", "Название", "Ссылка", "Теги", "Дата создания"],
            value=get_all_knowledge_base,
            every=10
        )
        refresh_kb_btn = gr.Button("🔄 Обновить список")
        kb_add_btn.click(add_kb_item_ui, [kb_title, kb_link, kb_tags], [kb_status, kb_table])
        refresh_kb_btn.click(get_all_knowledge_base, [], kb_table)

        gr.Markdown("---")
        gr.Markdown("### 🎯 Управление направлениями для подбора плана")
        all_interests_state = gr.State(value=get_all_interests())
        def refresh_all_interests():
            data = get_all_interests() or []
            choices = [(row[1], str(row[0])) for row in data if len(row) >= 2]
            return gr.update(choices=choices, value=None), data
        with gr.Row():
            int_title = gr.Textbox(label="Название направления", placeholder="Введите интерес", scale=3)
            int_active = gr.Checkbox(label="Активно", value=True, scale=1)
            int_add_btn = gr.Button("➕ Добавить направление", scale=1)
        int_status = gr.Textbox(label="", visible=False)
        int_table = gr.Dataframe(
            headers=["ID", "Название", "Активно", "Дата создания"],
            value=get_all_interests_ui,
            every=10
        )
        with gr.Row():
            interest_selector = gr.Dropdown(choices=[], label="Выберите направление для редактирования", scale=3)
            edit_active = gr.Checkbox(label="Активно", value=True, scale=1)
            update_active_btn = gr.Button("🔄 Обновить активность", scale=1)
        with gr.Row():
            copy_title_btn = gr.Button("📋 Копировать название", scale=1)
            delete_interest_btn = gr.Button("❌ Удалить направление", variant="stop", scale=1)
        refresh_int_btn = gr.Button("🔄 Обновить список направлений", variant="secondary")
        demo.load(fn=refresh_all_interests, outputs=[interest_selector, all_interests_state])
        def on_interest_change(selected_id_str, all_data):
            if not selected_id_str:
                return False
            try:
                selected_id = int(selected_id_str)
                for row in all_data:
                    if row[0] == selected_id:
                        return row[2]
            except:
                pass
            return False
        interest_selector.change(fn=on_interest_change, inputs=[interest_selector, all_interests_state], outputs=edit_active)
        def update_interest(selected_id_str, active):
            if not selected_id_str:
                return "⚠️ Сначала выберите направление!", gr.update(), gr.update()
            try:
                selected_id = int(selected_id_str)
                toggle_interest_active_ui(selected_id, active)
                new_data = get_all_interests()
                choices = [(row[1], str(row[0])) for row in new_data]
                return "✅ Активность обновлена!", gr.update(choices=choices, value=None), new_data
            except Exception as e:
                return f"❌ Ошибка: {e}", gr.update(), gr.update()
        update_active_btn.click(update_interest, [interest_selector, edit_active],
                                 [int_status, interest_selector, all_interests_state]).then(
            fn=get_all_interests_ui, outputs=int_table)
        def get_selected_title(selected_id_str, all_data):
            if not selected_id_str:
                return ""
            try:
                selected_id = int(selected_id_str)
                for row in all_data:
                    if row[0] == selected_id:
                        return row[1]
            except:
                pass
            return ""
        copy_js = """function copyTitle(title) { navigator.clipboard.writeText(title); return 'Скопировано!'; }"""
        copy_title_btn.click(fn=get_selected_title, inputs=[interest_selector, all_interests_state],
                             outputs=[int_status], js=copy_js).then(fn=lambda: "✅ Название скопировано!", outputs=int_status)
        def delete_interest(selected_id_str):
            if not selected_id_str:
                return "⚠️ Сначала выберите направление!", gr.update(), gr.update()
            try:
                selected_id = int(selected_id_str)
                delete_interest_ui(selected_id)
                new_data = get_all_interests()
                choices = [(row[1], str(row[0])) for row in new_data]
                return "✅ Направление удалено!", gr.update(choices=choices, value=None), new_data
            except Exception as e:
                return f"❌ Ошибка: {e}", gr.update(), gr.update()
        delete_interest_btn.click(delete_interest, [interest_selector],
                                  [int_status, interest_selector, all_interests_state]).then(
            fn=get_all_interests_ui, outputs=int_table)
        def add_int_and_refresh(title, active):
            if not title:
                return "⚠️ Название обязательно!", gr.update(), gr.update(), ""
            try:
                add_interest_ui(title, active)
                new_data = get_all_interests()
                choices = [(row[1], str(row[0])) for row in new_data]
                return "✅ Направление добавлено!", gr.update(choices=choices, value=None), new_data, ""
            except Exception as e:
                return f"❌ Ошибка: {e}", gr.update(), gr.update(), title
        int_add_btn.click(add_int_and_refresh, [int_title, int_active],
                          [int_status, interest_selector, all_interests_state, int_title]).then(
            fn=get_all_interests_ui, outputs=int_table)
        refresh_int_btn.click(fn=refresh_all_interests, outputs=[interest_selector, all_interests_state]).then(
            fn=get_all_interests_ui, outputs=int_table)

        gr.Markdown("---")
        gr.Markdown("### 🚨 Лог ошибок приложения")
        error_table = gr.Dataframe(headers=["Время", "Тип", "Сообщение", "Traceback"],
                                    value=get_error_logs, every=10)
        refresh_btn = gr.Button("🔄 Обновить лог")
        refresh_btn.click(get_error_logs, [], error_table)
        error_text_to_copy = gr.Textbox(label="Текст ошибки для копирования", lines=2)
        copy_btn = gr.Button("📋 Копировать в буфер")
        copy_status = gr.Textbox(label="Статус")
        copy_btn.click(None, [error_text_to_copy], copy_status,
                       js="(text) => { navigator.clipboard.writeText(text); return 'Скопировано!'; }")
        gr.Markdown("---")
        gr.Markdown("### 🛑 Управление сервером")
        gr.Markdown("При нажатии приложение будет остановлено.")
        shutdown_btn = gr.Button("🛑 Остановить сервер", variant="stop")
        shutdown_btn.click(fn=shutdown_server, inputs=[], outputs=[],
                           js="() => { if(!confirm('Вы уверены?')) throw new Error('Отменено'); }")

    # ----- Вкладка 9: Просмотр БД -----
    with gr.Tab("📊 База данных"):
        gr.Markdown("### Просмотр содержимого таблиц")
        table_selector = gr.Dropdown(
            choices=[
                "progress", "agent_prompts", "error_logs", "test_results",
                "chat_history", "test_answers", "knowledge_base", "interests",
                "weekly_plans", "llm_dialogues"
            ],
            label="Выберите таблицу"
        )
        view_btn = gr.Button("Показать")
        table_display = gr.Dataframe()
        view_btn.click(show_table, table_selector, table_display)

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(), css=custom_css)