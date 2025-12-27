import streamlit as st
import google.generativeai as genai
import requests
import json
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONFIG & CSS (Der Trick für das Layout) ---
st.set_page_config(page_title="AI Coach Pro", page_icon="🚀", layout="centered")
st.title("🚀 Coach Chat")

# CSS: Hier passiert die Magie für das Layout
st.markdown("""
<style>
    /* 1. Das Audio-Element fixieren wir unten links */
    div[data-testid="stAudioInput"] {
        position: fixed;
        bottom: 20px; /* Abstand von unten */
        left: 20px;   /* Abstand von links */
        z-index: 1000; /* Damit es über allem anderen liegt */
        width: 50px;  /* Wir machen es klein, damit es wie ein Button aussieht */
        overflow: visible;
    }
    
    /* Der eigentliche Aufnahme-Button */
    div[data-testid="stAudioInput"] button {
        background-color: #ff4b4b;
        color: white;
        border-radius: 50%; /* Rund machen */
        width: 45px;
        height: 45px;
        border: none;
    }

    /* 2. Die Chat-Eingabe (Text) nach rechts schieben, damit Platz für Audio ist */
    div[data-testid="stChatInput"] {
        margin-left: 60px; /* Platz für das Mikrofon schaffen */
        width: calc(100% - 70px) !important; /* Breite anpassen */
    }
    
    /* Optional: Den Standard-Container etwas aufräumen */
    .stMainBlockContainer {
        padding-bottom: 100px; /* Platz unten damit nichts verdeckt wird */
    }
</style>
""", unsafe_allow_html=True)

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

# Session State
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "model", "content": "Hi! Ich bin bereit."}]
if "pending_plan" not in st.session_state:
    st.session_state.pending_plan = None
if "last_processed_audio" not in st.session_state:
    st.session_state.last_processed_audio = None

# --- 2. API FUNKTIONEN ---

def delete_existing_workouts(date_str):
    """Löscht ALLE Workouts an einem bestimmten Tag"""
    url_get = f"https://intervals.icu/api/v1/athlete/{intervals_id}/events?oldest={date_str}&newest={date_str}"
    try:
        resp = requests.get(url_get, auth=('API_KEY', intervals_key))
        if resp.status_code == 200:
            events = resp.json()
            count = 0
            for e in events:
                if e.get('category') == 'WORKOUT':
                    eid = e['id']
                    requests.delete(f"https://intervals.icu/api/v1/athlete/{intervals_id}/events/{eid}", auth=('API_KEY', intervals_key))
                    count += 1
            return count
    except:
        pass
    return 0

def upload_workout(workout_data):
    """Lädt Workout hoch (mit Type & Duration)"""
    delete_existing_workouts(workout_data['datum']) # Erst Platz machen
    
    url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/events"
    date_str = workout_data['datum']
    if "T" not in date_str: date_str = f"{date_str}T09:00:00"
    
    payload = {
        "category": "WORKOUT",
        "start_date_local": date_str,
        "name": workout_data['titel'],
        "description": workout_data.get('beschreibung', ''),
        "type": workout_data.get('sport_type', 'Ride'), 
        "duration": workout_data.get('duration_sec', 3600)
    }
    try:
        requests.post(url, json=payload, auth=('API_KEY', intervals_key))
        return True
    except:
        return False

def fetch_data(endpoint, days=7, is_future=False):
    today = datetime.today().strftime('%Y-%m-%d')
    if is_future:
        date_param = f"oldest={today}&newest={(datetime.today() + timedelta(days=days)).strftime('%Y-%m-%d')}"
    else:
        date_param = f"oldest={(datetime.today() - timedelta(days=days)).strftime('%Y-%m-%d')}&newest={today}"
    url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/{endpoint}?{date_param}"
    try:
        resp = requests.get(url, auth=('API_KEY', intervals_key))
        return resp.json() if resp.status_code == 200 else []
    except:
        return []

def extract_json(text):
    try:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != -1:
            return json.loads(text[start:end])
    except:
        pass
    return None

# --- 3. UI AUFBAU ---

chat_container = st.container()

with chat_container:
    for msg in st.session_state.messages:
        role = "assistant" if msg["role"] == "model" else msg["role"]
        st.chat_message(role).write(msg["content"])

# --- INPUT LOGIK (HIER IST DIE ÄNDERUNG) ---

# 1. Das Audio Widget rendern wir ZUERST.
# Durch das CSS oben ("position: fixed") wird es aus dem Fluss genommen 
# und unten links in die Ecke geklebt.
audio_val = st.audio_input("🎙️", label_visibility="collapsed")

# 2. Das Text Widget (st.chat_input) klebt von Natur aus unten.
# Durch das CSS oben ("margin-left") rutscht es nach rechts, um Platz für Audio zu machen.
text_val = st.chat_input("Nachricht tippen oder 'Passt'...")

# --- 4. VERARBEITUNG ---

user_content = None
input_type = None

# Logik: Wer hat Daten?
if text_val:
    user_content = text_val
    input_type = 'text'
elif audio_val:
    # Check gegen Loop
    audio_id = audio_val.file_id if hasattr(audio_val, 'file_id') else audio_val.size
    if audio_id != st.session_state.last_processed_audio:
        user_content = audio_val
        input_type = 'audio'
        st.session_state.last_processed_audio = audio_id
    else:
        pass

if user_content:
    if not google_api_key or not intervals_key:
        st.error("Keys fehlen!")
        st.stop()

    if input_type == 'audio':
        st.session_state.messages.append({"role": "user", "content": "🎙️ *Audio Befehl*"})
        with chat_container:
            st.chat_message("user").write("🎙️ *Audio Befehl*")
            st.audio(user_content)
    else:
        st.session_state.messages.append({"role": "user", "content": user_content})
        with chat_container:
            st.chat_message("user").write(user_content)

    # UPLOAD CHECK
    if st.session_state.pending_plan and input_type == 'text':
        if any(w in user_content.lower() for w in ["passt", "ja", "hochladen", "ok"]):
            with st.spinner("Aktualisiere Kalender..."):
                count = 0
                for w in st.session_state.pending_plan:
                    if upload_workout(w): count += 1
                msg = f"✅ Erledigt! {count} Einheiten aktualisiert."
                st.session_state.messages.append({"role": "model", "content": msg})
