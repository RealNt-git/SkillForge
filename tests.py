import traceback
import gradio as gr
from database import log_error, save_test_result, save_test_answer

# Test questions data
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

def start_test(topic):
    try:
        qs = test_questions.get(topic, [])
        return qs, [None] * len(qs)
    except Exception as e:
        log_error(type(e).__name__, str(e), traceback.format_exc())
        return [], []

def load_question(topic, idx):
    try:
        qs = test_questions.get(topic, [])
        if idx < len(qs):
            q = qs[idx]
            return (
                f"**Вопрос {idx+1}:** {q['question']}",
                gr.update(choices=q['options'], value=None),
                idx
            )
        else:
            return (
                "Тест завершён! Нажмите 'Сбросить тест' для нового теста.",
                gr.update(choices=[], value=None),
                idx
            )
    except Exception as e:
        log_error(type(e).__name__, str(e), traceback.format_exc())
        return (
            "Ошибка загрузки вопроса. Попробуйте сбросить тест.",
            gr.update(choices=[], value=None),
            idx
        )

def reset_test(topic):
    try:
        q_text, opts_update, _ = load_question(topic, 0)
        return 0, 0, q_text, opts_update, ""
    except Exception as e:
        log_error(type(e).__name__, str(e), traceback.format_exc())
        return 0, 0, "Ошибка сброса теста.", gr.update(choices=[], value=None), ""

def check_answer(topic, idx, selected, current_score, user_email):
    try:
        qs = test_questions.get(topic, [])
        if idx < len(qs):
            correct = qs[idx]["answer"]
            selected_text = selected if selected else ""
            is_correct = False
            if selected is not None and qs[idx]["options"].index(selected) == correct:
                current_score += 1
                feedback = "✅ Верно!"
                is_correct = True
            else:
                feedback = f"❌ Неверно. Правильный ответ: {qs[idx]['options'][correct]}"
                is_correct = False
            if user_email:
                save_test_answer(user_email, topic, idx, selected_text, is_correct)
            next_idx = idx + 1
            if next_idx < len(qs):
                q_text, opts_update, _ = load_question(topic, next_idx)
                return feedback, current_score, next_idx, q_text, opts_update
            else:
                save_test_result(user_email, topic, current_score, len(qs))
                return (
                    f"🎉 Тест завершён! Результат: {current_score}/{len(qs)}. Сохранено.",
                    current_score,
                    next_idx,
                    "",
                    gr.update(choices=[], value=None)
                )
        return "Ошибка: неверный индекс вопроса.", current_score, idx, "", gr.update(choices=[], value=None)
    except Exception as e:
        log_error(type(e).__name__, str(e), traceback.format_exc())
        return f"Ошибка при проверке ответа: {e}", current_score, idx, "", gr.update(choices=[], value=None)