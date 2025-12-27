import streamlit as st
import google.generativeai as genai
import requests
import json
from datetime import datetime

# --- 1. Grundeinstellungen ---
st.set_page_config(page_title="Mein Gemini Coach", page_icon="🚴")
st.title("🚴 Mein Gemini Trainer")

# --- 2. Seitenleiste für die Keys ---
with st.sidebar:
    st.header("Einstellungen")
    st.info("Gib hier einmalig deine Schlüssel ein:")
    google_api_key = st.text_input("Google API Key", type="password")
    intervals_id = st.text_input("Intervals Athlete ID (z.B. i12345)")
    intervals_key = st.text_input("Intervals API Key", type="password")

# --- 3. Funktion: Training an Intervals senden ---
def upload_to_intervals(date_str, description, title, i_id, i_key):
    url = f"https://intervals.icu/api/v1/athlete/{i_id}/events"
    payload = {
        "category": "WORKOUT",
        "start_date_local": date_str,
        "name": title,
        "description": description,
        "type": "Ride" # Du kannst hier auch 'Run' eintragen, wenn du läufst
    }
    # Senden an Intervals
    try:
        response = requests.post(url, json=payload, auth=('API_KEY', i_key))
        return response.status_code, response.text
    except Exception as e:
        return 0, str(e)

# --- 4. Der Chatbot ---
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "model", "content": "Hi! Ich bin bereit. Was soll ich für dich planen?"}]

# Alte Nachrichten anzeigen
for msg in st.session_state.messages:
    role = "assistant" if msg["role"] == "model" else msg["role"]
    st.chat_message(role).write(msg["content"])

# Eingabefeld unten
prompt = st.chat_input("Z.B.: Plan mir 2h Zone 2 für morgen")

if prompt:
    # Prüfen, ob Keys da sind
    if not google_api_key or not intervals_key or not intervals_id:
        st.error("Stop! Bitte gib erst links in der Leiste deine Keys ein.")
        st.stop()

    # User Nachricht anzeigen
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # Gemini vorbereiten
    genai.configure(api_key=google_api_key)
    model = genai.GenerativeModel('gemini-pro')

    # Der Befehl an die KI (System Prompt)
    system_instruction = f"""
    Du bist ein professioneller Radsport-Coach.
    Heute ist der {datetime.today().strftime('%Y-%m-%d')}.
    Der User möchte ein Training basierend auf: "{prompt}"
    
    WICHTIG: Antworte AUSSCHLIESSLICH mit einem JSON-Objekt. Kein anderer Text.
    Das Format muss so aussehen:
    {{
      "training_text": "Hier das Workout im Intervals-Format (z.B. 10m 50%...)", 
      "datum": "YYYY-MM-DD",
      "titel": "Kurzer Titel des Trainings",
      "user_antwort": "Ein netter Satz an den User, was du geplant hast."
    }}
    """

    try:
        with st.spinner("Ich denke nach..."):
            response = model.generate_content(system_instruction)
            text_response = response.text

            # JSON säubern (falls Gemini Formatierungszeichen mitschickt)
            clean_json = text_response.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)

            # An Intervals senden
            status, info = upload_to_intervals(data["datum"], data["training_text"], data["titel"], intervals_id, intervals_key)

            if status == 200:
                reply = f"✅ **Erledigt!**\n\n{data['user_antwort']}\n\n*Eingetragen für: {data['datum']}*"
            else:
                reply = f"❌ Fehler beim Hochladen: {status} - {info}"

    except Exception as e:
        reply = f"Hoppla, da lief was schief: {e}. Versuch es bitte noch mal genauer."

    # Antwort anzeigen und speichern
    st.session_state.messages.append({"role": "model", "content": reply})

    st.chat_message("assistant").write(reply)
