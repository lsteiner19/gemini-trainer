import streamlit as st
import google.generativeai as genai
import requests
import json
from datetime import datetime

# --- 1. Grundeinstellungen ---
st.set_page_config(page_title="Mein Gemini Coach", page_icon="🚴")
st.title("🚴 Mein Gemini Trainer")

# --- 2. Keys automatisch laden (Secrets) ---
with st.sidebar:
    st.header("Einstellungen")
    
    # Google Key prüfen
    if "GOOGLE_API_KEY" in st.secrets:
        google_api_key = st.secrets["GOOGLE_API_KEY"]
        st.success("✅ Google Key automatisch geladen")
    else:
        google_api_key = st.text_input("Google API Key", type="password")

    # Intervals ID prüfen
    if "INTERVALS_ID" in st.secrets:
        intervals_id = st.secrets["INTERVALS_ID"]
        st.success("✅ Athlete ID geladen")
    else:
        intervals_id = st.text_input("Intervals Athlete ID (z.B. i12345)")

    # Intervals Key prüfen
    if "INTERVALS_KEY" in st.secrets:
        intervals_key = st.secrets["INTERVALS_KEY"]
        st.success("✅ Intervals Key geladen")
    else:
        intervals_key = st.text_input("Intervals API Key", type="password")

# --- 3. Funktion: Training an Intervals senden ---
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

# --- 4. Der Chatbot ---
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "model", "content": "Hi! Ich kenne deine Keys jetzt. Was soll ich planen?"}]

# Alte Nachrichten anzeigen
for msg in st.session_state.messages:
    role = "assistant" if msg["role"] == "model" else msg["role"]
    st.chat_message(role).write(msg["content"])

# Eingabefeld unten
prompt = st.chat_input("Z.B.: Plan mir 2h Zone 2 für morgen")

if prompt:
    # Sicherheitscheck
    if not google_api_key or not intervals_key or not intervals_id:
        st.error("Es fehlen noch Keys! Bitte trage sie in den Streamlit 'Secrets' ein oder links in das Feld.")
        st.stop()

    # User Nachricht anzeigen
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # Gemini konfigurieren (Nutzt 'gemini-pro' oder 'gemini-1.5-flash' je nach Verfügbarkeit)
    genai.configure(api_key=google_api_key)
    # Falls Flash wieder zickt, nutzen wir hier Pro:
    # ... (der Code davor bleibt gleich) ...
    
    # Wir konfigurieren Gemini
    genai.configure(api_key=google_api_key)
    
    # HIER IST DIE ÄNDERUNG: Wir nehmen die "latest" Version
    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        with st.spinner("Ich plane..."):
            response = model.generate_content(system_instruction)
            text_response = response.text
            # ... (Rest des Codes wie vorher) ...
            
            clean_json = text_response.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)

            status, info = upload_to_intervals(data["datum"], data["training_text"], data["titel"], intervals_id, intervals_key)

            if status == 200:
                reply = f"✅ **Erledigt!**\n\n{data['user_antwort']}\n\n*Eingetragen für: {data['datum']}*"
            else:
                reply = f"❌ Fehler bei Intervals: {status} - {info}"
                
            st.session_state.messages.append({"role": "model", "content": reply})
            st.chat_message("assistant").write(reply)

    except Exception as e:
        # Falls das Modell nicht gefunden wird, zeigen wir eine bessere Fehlermeldung
        st.error(f"Fehler: {e}")
        st.warning("Versuche, verfügbare Modelle aufzulisten...")
        try:
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    st.write(f"- {m.name}")
        except:
            pass
    system_instruction = f"""
    Du bist ein professioneller Radsport-Coach.
    Heute ist der {datetime.today().strftime('%Y-%m-%d')}.
    Der User möchte ein Training basierend auf: "{prompt}"
    
    WICHTIG: Antworte AUSSCHLIESSLICH mit einem JSON-Objekt.
    Format:
    {{
      "training_text": "Workout im Intervals-Format", 
      "datum": "YYYY-MM-DD",
      "titel": "Titel",
      "user_antwort": "Deine Antwort an den User."
    }}
    """

    try:
        with st.spinner("Ich plane..."):
            response = model.generate_content(system_instruction)
            text_response = response.text
            
            clean_json = text_response.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)

            status, info = upload_to_intervals(data["datum"], data["training_text"], data["titel"], intervals_id, intervals_key)

            if status == 200:
                reply = f"✅ **Erledigt!**\n\n{data['user_antwort']}\n\n*Eingetragen für: {data['datum']}*"
            else:
                reply = f"❌ Fehler beim Hochladen: {status} - {info}"

    except Exception as e:
        reply = f"Fehler: {e}"

    st.session_state.messages.append({"role": "model", "content": reply})
    st.chat_message("assistant").write(reply)


