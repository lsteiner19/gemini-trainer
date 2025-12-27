import streamlit as st
import google.generativeai as genai
import requests
import json
from datetime import datetime

# --- 1. Grundeinstellungen ---
st.set_page_config(page_title="Mein Gemini Coach", page_icon="🚴")
st.title("🚴 Mein Gemini Trainer (v2.0)")

# --- 2. Keys automatisch laden ---
with st.sidebar:
    st.header("Einstellungen")
    
    if "GOOGLE_API_KEY" in st.secrets:
        google_api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("✅ Google Key geladen")
    else:
        google_api_key = st.text_input("Google API Key", type="password")

    if "INTERVALS_ID" in st.secrets:
        intervals_id = st.secrets["INTERVALS_ID"]
        st.success("✅ Athlete ID geladen")
    else:
        intervals_id = st.text_input("Intervals Athlete ID")

    if "INTERVALS_KEY" in st.secrets:
        intervals_key = st.secrets["INTERVALS_KEY"]
        st.success("✅ Intervals Key geladen")
    else:
        intervals_key = st.text_input("Intervals API Key", type="password")

# --- 3. Upload Funktion ---
# --- 3. Upload Funktion (Repariert) ---
def upload_to_intervals(date_str, description, title, i_id, i_key):
    # FEHLERBEHEBUNG:
    # Intervals braucht zwingend eine Uhrzeit (z.B. T09:00:00).
    # Wenn die KI nur "2025-12-28" liefert, hängen wir automatisch 9 Uhr morgens an.
    if "T" not in date_str:
        date_str = f"{date_str}T09:00:00"
    
    url = f"https://intervals.icu/api/v1/athlete/{i_id}/events"
    payload = {
        "category": "WORKOUT",
        "start_date_local": date_str, # Jetzt mit Uhrzeit!
        "name": title,
        "description": description,
        "type": "Ride"
    }
    try:
        response = requests.post(url, json=payload, auth=('API_KEY', i_key))
        return response.status_code, response.text
    except Exception as e:
        return 0, str(e)

# --- 4. Chat ---
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "model", "content": "Hi! Ich nutze jetzt Gemini 2.0 Flash. Was wollen wir planen?"}]

for msg in st.session_state.messages:
    role = "assistant" if msg["role"] == "model" else msg["role"]
    st.chat_message(role).write(msg["content"])

prompt = st.chat_input("Z.B.: Plan mir 2h Zone 2 für morgen")

if prompt:
    if not google_api_key or not intervals_key or not intervals_id:
        st.error("Bitte erst Keys eingeben!")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    system_instruction = f"""
    Du bist ein Radsport-Coach. Heute ist {datetime.today().strftime('%Y-%m-%d')}.
    User-Wunsch: "{prompt}"
    
    Antworte NUR als JSON:
    {{
      "training_text": "Workout-Text für Intervals.icu", 
      "datum": "YYYY-MM-DD",
      "titel": "Titel",
      "user_antwort": "Text an User"
    }}
    """

    genai.configure(api_key=google_api_key)
    
    try:
        # HIER IST DIE ÄNDERUNG: Wir nehmen exakt den Namen aus deiner Liste
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        with st.spinner("Ich plane mit Gemini 2.0..."):
            response = model.generate_content(system_instruction)
            clean_json = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)

            status, info = upload_to_intervals(data["datum"], data["training_text"], data["titel"], intervals_id, intervals_key)

            if status == 200:
                reply = f"✅ **Erledigt!**\n\n{data['user_antwort']}\n\n*Datum: {data['datum']}*"
            else:
                reply = f"❌ Intervals Fehler: {status} - {info}"

    except Exception as e:
        reply = f"⚠️ Fehler: {e}"
        # Fallback, falls er doch meckert
        if "404" in str(e):
             reply += "\n\n**Tipp:** Der Server braucht evtl. einen Neustart (Reboot), damit er Gemini 2.0 erkennt."

    st.session_state.messages.append({"role": "model", "content": reply})
    st.chat_message("assistant").write(reply)

