import os
import sys
import time
import gradio as gr
from database import (
    get_prompt, update_prompt, get_error_logs, log_error,
    get_all_knowledge_base, add_knowledge_item,
    get_all_interests, add_interest, update_interest_active, delete_interest
)
from search import add_resource_to_vector_db

# ========== ПРОМПТЫ ==========
def load_prompt(agent_name):
    return get_prompt(agent_name)

def save_prompt_ui(agent_name, new_prompt):
    update_prompt(agent_name, new_prompt)
    return f"Промпт для {agent_name} сохранён."

# ========== БАЗА ЗНАНИЙ ==========
def add_kb_item_ui(title, link, tags):
    if not title or not link:
        return "⚠️ Название и ссылка обязательны!", gr.update()
    add_knowledge_item(title, link, tags)
    add_resource_to_vector_db(title, link, tags)
    return "✅ Ресурс добавлен!", get_all_knowledge_base()

# ========== ИНТЕРЕСЫ ==========
def get_all_interests_ui():
    return get_all_interests()

def add_interest_ui(title, active):
    if not title:
        return "⚠️ Название обязательно!", gr.update()
    add_interest(title, active)
    return "✅ Направление добавлено!", get_all_interests()

def toggle_interest_active_ui(interest_id, active):
    update_interest_active(interest_id, active)
    return get_all_interests()

def delete_interest_ui(interest_id):
    delete_interest(interest_id)
    return get_all_interests()

# ========== УПРАВЛЕНИЕ СЕРВЕРОМ ==========
def shutdown_server():
    log_error("INFO", "Сервер остановлен администратором", "")
    time.sleep(0.5)
    os._exit(0)