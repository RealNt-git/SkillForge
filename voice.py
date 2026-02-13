import tempfile
import traceback
from database import error_logged, log_error

# Whisper and gTTS are optional; check imports later
whisper = None
gTTS = None
try:
    import whisper
except ImportError:
    pass
try:
    from gtts import gTTS
except ImportError:
    pass

@error_logged
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

@error_logged
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

def add_chat_message(history, role, content):
    history.append({"role": role, "content": content})
    return history