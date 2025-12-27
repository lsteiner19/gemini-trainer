import streamlit as st
import google.generativeai as genai
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
import concurrent.futures # Für den Turbo-Modus

# --- 1. CONFIG & CSS ---
st.set_page_config(page_title="AI Coach Pro", page_icon="🚀", layout="centered")
st.title("🚀 Coach Chat")

st.markdown("""
<style>
    div[data-testid="stAudioInput"] {
        position: fixed; bottom: 20px; left: 20px; z-index: 1000; width: 50px; overflow: visible;
    }
    div[data-testid="stAudioInput"] button {
        background-color: #ff4b4b; color: white; border-radius: 50%; width: 45px; height: 45px; border: none;
    }
    div[data-testid="stChatInput"] { margin-left: 60px; width: calc(100% - 70px) !important; }
    .stMainBlockContainer { padding-bottom: 100px; }
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

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "model", "content": "Hi! Ich bin bereit."}]
if "pending_plan" not in st.session_state:
    st.session_state.pending_plan = None
if "last_processed_audio" not in st.session_state:
    st.session_state.last_processed_audio = None

# --- 2. TURBO API FUNKTIONEN ---

def delete_single_event(event_id):
    """Löscht ein einzelnes Event (Hilfsfunktion für Threading)"""
    url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/events/{event_id}"
    try:
        requests.delete(url, auth=('API_KEY', intervals_key))
        return True
    except:
        return False

def clear_and_upload_bulk(new_workouts):
    """
    1. Ermittelt den Zeitraum des neuen Plans (Start bis Ende).
    2. Löscht ALLE Workouts in diesem Zeitraum gleichzeitig (Parallel).
    3. Lädt die neuen Workouts hoch.
    """
    
    # A) Zeitraum ermitteln
    dates = [w['datum'] for w in new_workouts]
    if not dates: return 0
    start_date = min(dates)
    end_date = max(dates)
    
    status_text = st.empty() # Platzhalter für Statusmeldungen
    status_text.info(f"🧹 Bereinige Zeitraum {start_date} bis {end_date}...")
    
    # B) Alte Events holen
    url_get = f"https://intervals.icu/api/v1/athlete/{intervals_id}/events?oldest={start_date}&newest={end_date}"
    ids_to_delete = []
    try:
        resp = requests.get(url_get, auth=('API_KEY', intervals_key))
        if resp.status_code == 200:
            events = resp.json()
            # Nur Workouts löschen, keine Rennen!
            ids_to_delete = [e['id'] for e in events if e.get('category') == 'WORKOUT']
    except Exception as e:
        st.error(f"Fehler beim Lesen: {e}")
        return 0

    # C) TURBO LÖSCHEN (Parallel)
    if ids_to_delete:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(delete_single_event, ids_to_delete))
    
    status_text.info(f"💾 Speichere {len(new_workouts)} neue Einheiten...")

    # D) Neue Hochladen
    success_count = 0
    for w in new_workouts:
        url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/events"
        date_str = w['datum']
        if "T" not in date_str: date_str = f"{date_str}T09:00:00"
        
        payload = {
            "category": "WORKOUT",
            "start_date_local": date_str,
            "name": w['titel'],
            "description": w.get('beschreibung', ''),
            "type": w.get('sport_type', 'Ride'),
            "duration": w.get('duration_sec', 3600)
        }
        try:
            r = requests.post(url, json=payload, auth=('API_KEY', intervals_key))
            if r.status_code == 200: success_count += 1
        except:
            pass
            
    status_text.empty() # Text entfernen
    return success_count

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

# --- 3. UI ---

chat_container = st.container()
with chat_container:
    for msg in st.session_state.messages:
        role = "assistant" if msg["role"] == "model" else msg["role"]
        st.chat_message(role).write(msg["content"])

audio_val = st.audio_input("🎙️", label_visibility="collapsed")
text_val = st.chat_input("Nachricht tippen oder 'Passt'...")

# --- 4. LOGIK ---

user_content = None
input_type = None

if text_val:
    user_content = text_val
    input_type = 'text'
elif audio_val:
    audio_id = audio_val.file_id if hasattr(audio_val, 'file_id') else audio_val.size
    if audio_id != st.session_state.last_processed_audio:
        user_content = audio_val
        input_type = 'audio'
        st.session_state.last_processed_audio = audio_id

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

    # UPLOAD CHECK (Hier nutzen wir jetzt die neue Turbo-Funktion)
    if st.session_state.pending_plan and input_type == 'text':
        if any(w in user_content.lower() for w in ["passt", "ja", "hochladen", "ok"]):
            
            # --- HIER IST DIE ÄNDERUNG ---
            count = clear_and_upload_bulk(st.session_state.pending_plan)
            # -----------------------------
            
            msg = f"✅ Fertig! Der Zeitraum wurde bereinigt und {count} neue Einheiten gespeichert."
            st.session_state.messages.append({"role": "model", "content": msg})
            with chat_container:
                st.chat_message("assistant").write(msg)
            st.session_state.pending_plan = None
            st.stop()

    # KONTEXT
    context_str = ""
    trigger_text = "analyse plan rennen" if input_type == 'audio' else user_content.lower()
    
    if any(k in trigger_text for k in ["analyse", "gemacht", "letzte", "woche"]):
        with st.spinner("Lade Historie..."):
            d = fetch_data("activities", days=7)
            s = [{"date": x['start_date_local'][:10], "name": x['name'], "load": x.get('training_load')} for x in d]
            context_str += f"HISTORIE: {json.dumps(s)}\n"

    if any(k in trigger_text for k in ["plan", "zukunft", "rennen", "krank", "morgen"]):
        with st.spinner("Lade Kalender..."):
            days = 60 if "monat" in trigger_text else 14
            d = fetch_data("events", days=days, is_future=True)
            s = [{"date": x['start_date_local'][:10], "name": x['name'], "cat": x.get('category')} for x in d]
            context_str += f"KALENDER: {json.dumps(s)}\n"

    # KI ANFRAGE
    genai.configure(api_key=google_api_key)
    
    system_prompt = f"""
    Du bist Coach. Datum: {datetime.today().strftime('%Y-%m-%d')}.
    KONTEXT: {context_str}
    
    REGELN:
    1. Erkenne Sportart ('Ride' oder 'Run').
    2. Berechne Dauer in SEKUNDEN (duration_sec).
    3. Bei Plan-Erstellung: JSON `action: propose`.
    
    JSON FORMAT:
    {{
      "action": "propose",
      "text": "Vorschlag...",
      "workouts": [
        {{ "datum": "YYYY-MM-DD", "titel": "...", "beschreibung": "...", "sport_type": "Ride", "duration_sec": 3600 }}
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
        
        with st.spinner("..."):
            response = model.generate_content(parts)
            reply = response.text
            
            json_data = extract_json(reply)
            
            if json_data and json_data.get("action") == "propose":
                summary = json_data.get("text", "Vorschlag:")
                workouts = json_data.get("workouts", [])
                
                st.session_state.messages.append({"role": "model", "content": summary})
                with chat_container:
                    st.chat_message("assistant").write(summary)
                    if workouts:
                        df = pd.DataFrame(workouts)
                        df['min'] = df['duration_sec'] / 60
                        st.dataframe(df[['datum', 'sport_type', 'min', 'titel']], hide_index=True)
                        st.session_state.pending_plan = workouts
                        # Hinweis an User
                        dates = [w['datum'] for w in workouts]
                        st.info(f"⚠️ Achtung: Wenn du 'Passt' sagst, werden ALLE alten Trainings vom {min(dates)} bis {max(dates)} gelöscht und durch diesen Plan ersetzt.")
            else:
                st.session_state.messages.append({"role": "model", "content": reply})
                with chat_container:
                    st.chat_message("assistant").write(reply)

    except Exception as e:
        st.error(f"Fehler: {e}")
