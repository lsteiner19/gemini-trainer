import streamlit as st
import google.generativeai as genai
import requests
import json
from datetime import datetime

# --- 1. Grundeinstellungen ---
st.set_page_config(page_title="Mein Gemini Coach", page_icon="🚴")
st.title("🚴 Mein Gemini Trainer")

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

    # --- DIAGNOSE BUTTON (NEU) ---
    st.divider()
    if st.button("🛠️ Modelle prüfen (Diagnose)"):
        if google_api_key:
            try:
                genai.configure(api_key=google_api_key)
                st.write("Verfügbare Modelle:")
                found = False
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        st.code(m.name) # Zeigt den exakten Namen an
                        found = True
                if not found:
                    st.error("Keine Modelle gefunden. API Key prüfen?")
            except Exception as e:
                st.error(f"Fehler bei der Diagnose: {e}")
        else:
            st.warning("Erst Key eingeben!")

# --- 3. Upload Funktion ---
def upload_to_intervals(date_str, description, title, i_id, i_key):
    url = f"https://intervals.icu/api/v1/athlete/{i_id}/events"
    payload = {
        "category": "WORKOUT",
        "start_date_local": date_str,
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
    st.session_state.messages = [{"role": "model", "content": "Hi! Ich versuche es jetzt mit dem stabilen Modell. Was wollen wir planen?"}]

for msg in st.session_state.messages:
    role = "assistant" if msg["role"] == "model" else msg["role"]
    st.chat_message(role).write(msg["content"])

prompt = st.chat_input("Z.B.: Plan mir 2h Zone 2 für morgen")

if prompt:
    if not google_api_key or not intervals_key or not intervals_id:
        st.error("Bitte Keys eingeben.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    system_instruction = f"""
    Du bist ein Radsport-Coach. Heute ist {datetime.today().strftime('%Y-%m-%d')}.
    User-Wunsch: "{prompt}"
    
    Antworte NUR als JSON:
    {{
      "training_text": "Workout-Text", 
      "datum": "YYYY-MM-DD",
      "titel": "Titel",
      "user_antwort": "Text an User"
    }}
    """

    genai.configure(api_key=google_api_key)
    
    try:
        # ÄNDERUNG: Wir nutzen 'gemini-pro', das ist stabiler als flash
        model = genai.GenerativeModel('gemini-pro')
        
        with st.spinner("Ich plane..."):
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
        # Automatische Diagnose im Fehlerfall
        if "404" in str(e):
             reply += "\n\n**DIAGNOSE:** Ich konnte das Modell 'gemini-pro' nicht finden. Bitte klicke links auf 'Modelle prüfen' und sende dem Entwickler (mir), welche Namen dort stehen."

    st.session_state.messages.append({"role": "model", "content": reply})
    st.chat_message("assistant").write(reply)
