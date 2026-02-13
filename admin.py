import os
import sys
import time
import gradio as gr
from database import (
    get_prompt, update_prompt, get_error_logs, log_error,
    get_all_knowledge_base, add_knowledge_item
)
from search import add_resource_to_vector_db

def load_prompt(agent_name):
    return get_prompt(agent_name)

def save_prompt_ui(agent_name, new_prompt):
    update_prompt(agent_name, new_prompt)
    return f"Промпт для {agent_name} сохранён."

def shutdown_server():
    log_error("INFO", "Сервер остановлен администратором", "")
    time.sleep(0.5)
    os._exit(0)

def add_kb_item_ui(title, link, tags):
    if not title or not link:
        return "⚠️ Название и ссылка обязательны!", gr.update()
    add_knowledge_item(title, link, tags)
    add_resource_to_vector_db(title, link, tags)  # здесь уже есть логирование внутри
    return "✅ Ресурс добавлен!", get_all_knowledge_base()