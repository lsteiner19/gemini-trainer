import streamlit as st
import google.generativeai as genai
import requests
import json
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 1. SETUP ---
st.set_page_config(page_title="AI Coach", page_icon="🚴", layout="centered")
st.title("🚴 Smart Coach Chat")

# Keys laden
if "GOOGLE_API_KEY" in st.secrets:
    google_api_key = st.secrets["GOOGLE_API_KEY"]
else:
    google_api_key = st.text_input("Google API Key", type="password")

if "INTERVALS_ID" in st.secrets:
    intervals_id = st.secrets["INTERVALS_ID"]
else:
    intervals_id = st.text_input("Athlete ID")

if "INTERVALS_KEY" in st.secrets:
    intervals_key = st.secrets["INTERVALS_KEY"]
else:
    intervals_key = st.text_input("Intervals API Key", type="password")

# --- SESSION STATE INITIALISIEREN ---
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "model", "content": "Hi! Ich bin bereit. Sag mir, was wir planen sollen."}]
if "pending_plan" not in st.session_state:
    st.session_state.pending_plan = None
# WICHTIG: Damit Audio nicht doppelt gesendet wird
if "last_processed_audio_id" not in st.session_state:
    st.session_state.last_processed_audio_id = None

# --- 2. HILFSFUNKTIONEN ---

def extract_json(text):
    """Findet JSON in einem Text, auch wenn die KI davor noch etwas schreibt."""
    try:
        # Suche nach dem ersten '{' und dem letzten '}'
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != -1:
            json_str = text[start:end]
            return json.loads(json_str)
        return None
    except:
        return None

def fetch_data(endpoint, days=7, is_future=False):
    """Generische Funktion zum Daten holen"""
    today = datetime.today().strftime('%Y-%m-%d')
    if is_future:
        date_param = f"oldest={today}&newest={(datetime.today() + timedelta(days=days)).strftime('%Y-%m-%d')}"
    else:
        date_param = f"oldest={(datetime.today() - timedelta(days=days)).strftime('%Y-%m-%d')}&newest={today}"
        
    url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/{endpoint}?{date_param}"
    try:
        resp = requests.get(url, auth=('API_KEY', intervals_key))
        if resp.status_code == 200:
            return resp.json()
        return []
    except:
        return []

def upload_workout(workout_data):
    """Lädt ein Workout hoch"""
    url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/events"
    date_str = workout_data['datum']
    if "T" not in date_str:
        date_str = f"{date_str}T09:00:00"
    
    payload = {
        "category": "WORKOUT",
        "start_date_local": date_str,
        "name": workout_data['titel'],
        "description": workout_data.get('beschreibung', ''),
        "type": "Ride"
    }
    try:
        requests.post(url, json=payload, auth=('API_KEY', intervals_key))
        return True
    except:
        return False

# --- 3. CHAT GUI ---

# Alten Chatverlauf anzeigen
for msg in st.session_state.messages:
    role = "assistant" if msg["role"] == "model" else msg["role"]
    st.chat_message(role).write(msg["content"])

# EINGABE-LOGIK
# Wir trennen Audio und Text strikt, um den Loop zu verhindern
input_container = st.container()
with input_container:
    col1, col2 = st.columns([1, 5])
    with col1:
        audio_val = st.audio_input("🎙️")
    with col2:
        text_val = st.chat_input("Nachricht tippen...")

# Bestimmen, was verarbeitet werden soll
user_content = None
input_type = None # 'text' oder 'audio'

# Check 1: Wurde Text gesendet?
if text_val:
    user_content = text_val
    input_type = 'text'

# Check 2: Wurde Audio gesendet? (Und ist es NEUES Audio?)
elif audio_val:
    # Wir nutzen die ID der Datei, um zu prüfen, ob wir das schon kennen
    current_audio_id = audio_val.file_id if hasattr(audio_val, 'file_id') else audio_val.size
    
    if current_audio_id != st.session_state.last_processed_audio_id:
        user_content = audio_val
        input_type = 'audio'
        st.session_state.last_processed_audio_id = current_audio_id # Merken!
    else:
        # Das Audio liegt da noch rum, aber wir haben es schon bearbeitet -> Ignorieren
        pass

# --- 4. VERARBEITUNG ---

if user_content:
    if not google_api_key or not intervals_key:
        st.error("Bitte API Keys eingeben!")
        st.stop()

    # User Nachricht anzeigen
    if input_type == 'audio':
        st.session_state.messages.append({"role": "user", "content": "🎙️ *Audio Nachricht*"})
        with st.chat_message("user"):
            st.audio(user_content)
    else:
        st.session_state.messages.append({"role": "user", "content": user_content})
        st.chat_message("user").write(user_content)

    # CHECK: Will der User den Entwurf speichern?
    if st.session_state.pending_plan and input_type == 'text':
        if any(w in user_content.lower() for w in ["passt", "ja", "hochladen", "ok", "mach"]):
            with st.spinner("Lade Trainings hoch..."):
                count = 0
                for w in st.session_state.pending_plan:
                    if upload_workout(w): count += 1
                msg = f"✅ {count} Einheiten erfolgreich gespeichert!"
                st.session_state.messages.append({"role": "model", "content": msg})
                st.chat_message("assistant").write(msg)
                st.session_state.pending_plan = None
                st.stop()

    # KONTEXT LADEN (Datensparsam)
    context_str = ""
    # Einfache Keyword-Suche (bei Audio nehmen wir an, wir brauchen Kontext, um sicher zu sein)
    trigger_text = "analyse plan rennen" if input_type == 'audio' else user_content.lower()
    
    status_infos = []
    
    if any(k in trigger_text for k in ["analyse", "vergangenheit", "war ich", "letzte"]):
        with st.spinner("Lade Historie..."):
            data = fetch_data("activities", days=7, is_future=False)
            # Daten vereinfachen
            simple_data = [{"date": d['start_date_local'][:10], "name": d['name'], "load": d.get('training_load')} for d in data]
            context_str += f"HISTORIE (7 Tage): {json.dumps(simple_data)}\n"
            status_infos.append("Historie")

    if any(k in trigger_text for k in ["plan", "rennen", "zukunft", "krank", "nächste"]):
        with st.spinner("Lade Kalender..."):
            days = 60 if "monat" in trigger_text else 14
            data = fetch_data("events", days=days, is_future=True)
            simple_data = [{"date": d['start_date_local'][:10], "name": d['name'], "cat": d.get('category')} for d in data]
            context_str += f"KALENDER ({days} Tage): {json.dumps(simple_data)}\n"
            status_infos.append("Zukunft")

    if status_infos:
        st.caption(f"ℹ️ Daten geladen: {', '.join(status_infos)}")

    # KI ANFRAGE
    genai.configure(api_key=google_api_key)
    
    system_prompt = f"""
    Du bist ein Coach. Datum: {datetime.today().strftime('%Y-%m-%d')}.
    KONTEXT: {context_str}
    
    AUFGABE:
    1. Wenn du planst: Erstelle JSON mit `action: propose`.
    2. Wenn du analysierst: Antworte normal (nutze Markdown-Tabellen).
    
    FORMAT FÜR PLANUNG (JSON):
    {{
      "action": "propose",
      "text": "Kurze Erklärung...",
      "workouts": [
        {{ "datum": "YYYY-MM-DD", "titel": "...", "beschreibung": "..." }}
      ]
    }}
    """
    
    try:
        model = genai.GenerativeModel('gemini-flash-latest')
        
        parts = [system_prompt]
        if input_type == 'audio':
            parts.append({"mime_type": user_content.type, "data": user_content.read()})
        else:
            parts.append(f"User: {user_content}")
            
        with st.spinner("Coach denkt nach..."):
            response = model.generate_content(parts)
            reply = response.text
            
            # Versuchen, JSON zu finden
            json_data = extract_json(reply)
            
            if json_data and json_data.get("action") == "propose":
                # ES IST EIN PLAN -> VORSCHAU ZEIGEN
                summary = json_data.get("text", "Hier ist der Plan:")
                workouts = json_data.get("workouts", [])
                
                # 1. Text anzeigen
                st.session_state.messages.append({"role": "model", "content": summary})
                st.chat_message("assistant").write(summary)
                
                # 2. Tabelle anzeigen (Das ist die tabellarische Form!)
                if workouts:
                    df = pd.DataFrame(workouts)
                    st.dataframe(df, hide_index=True)
                    # Wir speichern den DataFrame nicht im Chat-Verlauf (geht technisch schwer),
                    # aber wir merken uns die Daten für den Upload.
                    st.session_state.pending_plan = workouts
                    st.info("Sage 'Passt', um das hochzuladen.")
                    
            else:
                # NORMALER TEXT / ANALYSE
                st.session_state.messages.append({"role": "model", "content": reply})
                st.chat_message("assistant").write(reply)

    except Exception as e:
        st.error(f"Fehler: {e}")

