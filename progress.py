from database import (
    save_progress, get_progress, get_all_progress,
    save_chat_message, get_chat_history,
    save_test_result, save_test_answer, c, db_lock
)
import csv
from io import StringIO

def show_progress(user_id):
    data = get_progress(user_id)
    if not data:
        return [["Нет записей", "", ""]]
    return data

def add_progress_ui(user_id, skill, status):
    save_progress(user_id, skill, status)
    return f"Достижение '{skill}' добавлено!"

def export_progress_csv():
    data = get_all_progress()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Email", "Навык", "Статус", "Дата"])
    writer.writerows(data)
    return output.getvalue()

def get_test_details(user_id, test_questions, limit=20):
    with db_lock:
        c.execute("""
            SELECT topic, question_index, selected, correct, date 
            FROM test_answers 
            WHERE user_id=? 
            ORDER BY date DESC 
            LIMIT ?
        """, (user_id, limit))
        rows = c.fetchall()
        result = []
        for row in rows:
            topic, q_idx, selected, correct, date = row
            try:
                q_text = test_questions[topic][q_idx]["question"]
            except:
                q_text = f"Вопрос {q_idx+1}"
            result.append([topic, q_text, selected, "✅" if correct else "❌", date])
        return result