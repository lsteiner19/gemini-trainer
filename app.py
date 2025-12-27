import streamlit as st
import google.generativeai as genai
import requests
import json
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CONFIG & CSS ---
st.set_page_config(page_title="AI Coach Pro", page_icon="🚀", layout="centered")
st.title("🚀 Coach Chat")

# CSS: Audio-Input etwas hübscher machen
st.markdown("""
<style>
    /* Audio Input etwas kompakter */
    div[data-testid="stAudioInput"] { margin-bottom: 10px; }
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
    st.session_state.messages = [{"role": "model", "content": "Hi! Ich bin bereit für Analyse und Planung."}]
if "pending_plan" not in st.session_state:
    st.session_state.pending_plan = None
if "last_processed_audio" not in st.session_state:
    st.session_state.last_processed_audio = None

# --- 2. API FUNKTIONEN (LÖSCHEN & SCHREIBEN) ---

def delete_existing_workouts(date_str):
    """Löscht ALLE Workouts an einem bestimmten Tag, um Dopplungen zu vermeiden."""
    # 1. Events für diesen Tag holen
    url_get = f"https://intervals.icu/api/v1/athlete/{intervals_id}/events?oldest={date_str}&newest={date_str}"
    try:
        resp = requests.get(url_get, auth=('API_KEY', intervals_key))
        if resp.status_code == 200:
            events = resp.json()
            # 2. Alle Events durchgehen und löschen, wenn es Workouts sind
            count = 0
            for e in events:
                if e.get('category') == 'WORKOUT':
                    eid = e['id']
                    del_url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/events/{eid}"
                    requests.delete(del_url, auth=('API_KEY', intervals_key))
                    count += 1
            return count
    except Exception as e:
        print(f"Delete error: {e}")
    return 0

def upload_workout(workout_data):
    """Lädt ein Workout hoch (mit Type-Erkennung und Duration)"""
    
    # SCHRITT 1: Platz schaffen (Altes löschen)
    delete_existing_workouts(workout_data['datum'])
    
    url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/events"
    
    # Datum fixen
    date_str = workout_data['datum']
    if "T" not in date_str:
        date_str = f"{date_str}T09:00:00" # Standard 9 Uhr
    
    # Payload bauen
    payload = {
        "category": "WORKOUT",
        "start_date_local": date_str,
        "name": workout_data['titel'],
        "description": workout_data.get('beschreibung', ''),
        # WICHTIG: Hier kommen die neuen Felder
        "type": workout_data.get('sport_type', 'Ride'), # Default Ride, aber kann 'Run' sein
        "duration": workout_data.get('duration_sec', 3600) # Dauer in Sekunden für Load-Berechnung
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

# Chat Container (Scrollbar)
chat_container = st.container()

with chat_container:
    for msg in st.session_state.messages:
        role = "assistant" if msg["role"] == "model" else msg["role"]
        st.chat_message(role).write(msg["content"])

# INPUT BEREICH (Ganz unten)
st.divider() # Trennlinie

# Layout: Audio Button links oben, Textfeld darunter (Fixed)
# Da st.chat_input immer ganz unten klebt, packen wir Audio in einen Expander oder direkt drüber
with st.container():
    col_audio, col_info = st.columns([1, 4])
    with col_audio:
        # Audio Input (Leider nicht "sticky" in Streamlit, aber nah am Textfeld)
        audio_val = st.audio_input("🎙️ Memo", key="audio_in")
    with col_info:
        if audio_val:
            st.info("Audio bereit zum Senden...")

# Das hier klebt IMMER am unteren Bildschirmrand
text_val = st.chat_input("Nachricht tippen oder 'Passt' zum Speichern...")

# --- 4. LOGIK ---

user_content = None
input_type = None

# A) Text Input hat Vorrang
if text_val:
    user_content = text_val
    input_type = 'text'

# B) Audio Input verarbeiten (nur wenn neu)
elif audio_val:
    # Checken ob wir dieses Audio schon hatten (Streamlit Rerun Loop Fix)
    audio_id = audio_val.file_id if hasattr(audio_val, 'file_id') else audio_val.size
    if audio_id != st.session_state.last_processed_audio:
        user_content = audio_val
        input_type = 'audio'
        st.session_state.last_processed_audio = audio_id # Merken!
    else:
        pass # Schon erledigt

if user_content:
    if not google_api_key or not intervals_key:
        st.error("API Keys fehlen!")
        st.stop()

    # User Nachricht anzeigen
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
            with st.spinner("Lösche alte Trainings und speichere neue..."):
                count = 0
                for w in st.session_state.pending_plan:
                    if upload_workout(w): count += 1
                msg = f"✅ Erledigt! {count} Einheiten wurden aktualisiert (Alte überschrieben)."
                st.session_state.messages.append({"role": "model", "content": msg})
                with chat_container:
                    st.chat_message("assistant").write(msg)
                st.session_state.pending_plan = None
                st.stop()

    # KONTEXT
    context_str = ""
    trigger_text = "analyse plan rennen" if input_type == 'audio' else user_content.lower()
    
    if any(k in trigger_text for k in ["analyse", "gemacht", "letzte"]):
        with st.spinner("Lade Daten..."):
            d = fetch_data("activities", days=7)
            # Nur relevante Infos
            s = [{"date": x['start_date_local'][:10], "name": x['name'], "type": x.get('type'), "load": x.get('training_load')} for x in d]
            context_str += f"HISTORIE: {json.dumps(s)}\n"

    if any(k in trigger_text for k in ["plan", "zukunft", "rennen", "krank"]):
        with st.spinner("Lade Kalender..."):
            days = 60 if "monat" in trigger_text else 14
            d = fetch_data("events", days=days, is_future=True)
            s = [{"date": x['start_date_local'][:10], "name": x['name'], "cat": x.get('category')} for x in d]
            context_str += f"KALENDER: {json.dumps(s)}\n"

    # KI
    genai.configure(api_key=google_api_key)
    
    # NEUER SYSTEM PROMPT (Mit Regeln für Löschen, Typ & Dauer)
    system_prompt = f"""
    Du bist ein Rad- und Laufcoach. Datum: {datetime.today().strftime('%Y-%m-%d')}.
    KONTEXT: {context_str}
    
    AUFGABE:
    Erstelle oder ändere Trainingspläne.
    
    REGELN FÜR NEUE TRAININGS (WICHTIG):
    1. **Sportart:** Erkenne ob 'Ride' (Rad) oder 'Run' (Laufen). Standard ist Ride.
    2. **Dauer:** Berechne die Dauer in SEKUNDEN (z.B. 1h = 3600).
    3. **Format:** Antworte mit JSON `action: propose`.
    
    JSON FORMAT:
    {{
      "action": "propose",
      "text": "Zusammenfassung...",
      "workouts": [
        {{ 
           "datum": "YYYY-MM-DD", 
           "titel": "Titel", 
           "beschreibung": "Genaue Schritte...",
           "sport_type": "Ride" oder "Run",
           "duration_sec": 3600 
        }}
      ]
    }}
    """
    
    try:
        # Modell Wahl
        try:
            model = genai.GenerativeModel('gemini-flash-latest')
            parts = [system_prompt]
            if input_type == 'audio':
                parts.append({"mime_type": user_content.type, "data": user_content.read()})
            else:
                parts.append(f"User: {user_content}")
            
            with st.spinner("Coach denkt..."):
                response = model.generate_content(parts)
                reply = response.text
                
                json_data = extract_json(reply)
                
                if json_data and json_data.get("action") == "propose":
                    # VORSCHAU
                    summary = json_data.get("text", "Plan Vorschlag:")
                    workouts = json_data.get("workouts", [])
                    
                    st.session_state.messages.append({"role": "model", "content": summary})
                    with chat_container:
                        st.chat_message("assistant").write(summary)
                        if workouts:
                            # Tabelle zeigen
                            df = pd.DataFrame(workouts)
                            # Dauer für Anzeige in Minuten umrechnen
                            df['minuten'] = df['duration_sec'] / 60
                            st.dataframe(df[['datum', 'sport_type', 'minuten', 'titel']], hide_index=True)
                            
                            st.session_state.pending_plan = workouts
                            st.info("Alte Trainings an diesen Tagen werden gelöscht! Sage 'Passt' zum Speichern.")
                else:
                    st.session_state.messages.append({"role": "model", "content": reply})
                    with chat_container:
                        st.chat_message("assistant").write(reply)

        except Exception as e:
            st.error(f"Modell Fehler: {e}")

    except Exception as e:
        st.error(f"Fehler: {e}")
