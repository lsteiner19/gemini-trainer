import streamlit as st
import google.generativeai as genai
import requests
import json
import pandas as pd
from datetime import datetime, timedelta

# --- 1. SETUP & CONFIG ---
st.set_page_config(page_title="AI Coach Lite", page_icon="⚡", layout="centered")
st.title("⚡ Smart Coach Chat")

# Keys aus Secrets laden
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

# Session State für den "Entwurf-Modus"
if "pending_plan" not in st.session_state:
    st.session_state.pending_plan = None
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "model", "content": "Hi! Ich bin bereit. Ich lade Daten nur, wenn du danach fragst."}]

# --- 2. API FUNKTIONEN (Nur auf Abruf) ---

def fetch_past_activities(days=7):
    """Holt nur die Basis-Daten der letzten X Tage"""
    today = datetime.today().strftime('%Y-%m-%d')
    start_date = (datetime.today() - timedelta(days=days)).strftime('%Y-%m-%d')
    url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/activities?oldest={start_date}&newest={today}"
    try:
        resp = requests.get(url, auth=('API_KEY', intervals_key))
        if resp.status_code == 200:
            data = resp.json()
            # Wir reduzieren die Datenmenge für die KI
            simplified = []
            for a in data:
                simplified.append({
                    "date": a['start_date_local'][:10],
                    "name": a.get('name'),
                    "duration_m": int(a.get('moving_time', 0)/60),
                    "avg_hr": a.get('average_heartrate'),
                    "load": a.get('training_load')
                })
            return simplified
        return []
    except:
        return []

def fetch_future_events(days=30):
    """Holt geplante Events der Zukunft"""
    today = datetime.today().strftime('%Y-%m-%d')
    future = (datetime.today() + timedelta(days=days)).strftime('%Y-%m-%d')
    url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/events?oldest={today}&newest={future}"
    try:
        resp = requests.get(url, auth=('API_KEY', intervals_key))
        if resp.status_code == 200:
            data = resp.json()
            simplified = []
            for e in data:
                simplified.append({
                    "date": e['start_date_local'][:10],
                    "name": e.get('name'),
                    "category": e.get('category'),
                    "type": e.get('type')
                })
            return simplified
        return []
    except:
        return []

def upload_workout(workout_data):
    """Lädt ein einzelnes Workout hoch"""
    url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/events"
    # Datum fixen (Zeit anhängen)
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

# --- 3. CHAT LOGIK ---

# Chatverlauf anzeigen
for msg in st.session_state.messages:
    role = "assistant" if msg["role"] == "model" else msg["role"]
    st.chat_message(role).write(msg["content"])

# INPUT (Audio oder Text)
col_audio, col_text = st.columns([1, 5])
with col_audio:
    audio_val = st.audio_input("🎙️")
with col_text:
    text_val = st.chat_input("Nachricht...")

user_input = None
if audio_val:
    user_input = audio_val
    is_audio = True
elif text_val:
    user_input = text_val
    is_audio = False

# --- 4. VERARBEITUNG ---
if user_input:
    if not google_api_key:
        st.error("Kein API Key!")
        st.stop()

    # 1. User Input anzeigen
    if is_audio:
        st.session_state.messages.append({"role": "user", "content": "🎙️ *Audio Anfrage*"})
        with st.chat_message("user"):
            st.audio(user_input)
    else:
        st.session_state.messages.append({"role": "user", "content": user_input})
        st.chat_message("user").write(user_input)

    # 2. PRÜFEN: "Passt" der User den Entwurf?
    # Wenn ein Entwurf wartet und der User sagt "Passt", "Ja", "Hochladen"
    if st.session_state.pending_plan and not is_audio and any(w in text_val.lower() for w in ["passt", "ja", "hochladen", "ok", "mach es"]):
        with st.spinner(f"Lade {len(st.session_state.pending_plan)} Einheiten hoch..."):
            count = 0
            for wo in st.session_state.pending_plan:
                if upload_workout(wo):
                    count += 1
            
            success_msg = f"✅ Fertig! {count} Trainings wurden in deinen Kalender übertragen."
            st.session_state.messages.append({"role": "model", "content": success_msg})
            st.chat_message("assistant").write(success_msg)
            st.session_state.pending_plan = None # Entwurf löschen
            st.stop() # Hier aufhören

    # 3. CONTEXT LADEN (Nur bei Bedarf!)
    context_text = ""
    status_label = []
    
    # Text für Analyse vorbereiten (Audio kann man schwerer prüfen, daher laden wir da ggf. mehr)
    check_text = "analyse plan rennen zukunft" if is_audio else text_val.lower()

    # A) Vergangenheit laden?
    if any(w in check_text for w in ["analyse", "letzten", "vergangenheit", "gemacht", "war ich"]):
        with st.spinner("Lade vergangene Aktivitäten..."):
            past_data = fetch_past_activities(days=7) # Standard 7 Tage, KI kann mehr fordern wenn nötig
            context_text += f"\nVERGANGENHEIT (Letzte 7 Tage): {json.dumps(past_data)}"
            status_label.append("Historie geladen")

    # B) Zukunft laden?
    if any(w in check_text for w in ["plan", "zukunft", "rennen", "krank", "ausfallen", "verschieben"]):
        with st.spinner("Lade Kalender..."):
            # Wenn User sagt "Plan für 2 Monate", brauchen wir evtl. einen längeren Horizont
            future_days = 60 if "monat" in check_text else 14
            future_data = fetch_future_events(days=future_days)
            context_text += f"\nZUKUNFT (Kommende Events): {json.dumps(future_data)}"
            status_label.append("Kalender geladen")

    if status_label:
        st.caption(f"ℹ️ Info: {' & '.join(status_label)}")

    # 4. KI ANFRAGE
    genai.configure(api_key=google_api_key)
    system_instruction = f"""
    Du bist ein effizienter Radsport-Coach.
    Datum: {datetime.today().strftime('%Y-%m-%d')}.
    
    KONTEXT DATEN:
    {context_text}
    
    DEINE REGELN:
    1. **Analyse:** Wenn der User nach Analyse fragt, gib eine saubere Tabelle (Markdown) zurück.
    2. **Planung (Vorschau):** Wenn du Trainings erstellen sollst, lade sie NICHT sofort hoch.
       Gib stattdessen JSON zurück mit `action: propose`. Dann zeigen wir sie dem User erst.
    3. **Einzelnes Training:** Auch hier erst `action: propose`.
    4. **Krankheit/Änderung:** Schlage Änderungen vor.
    
    OUTPUT FORMAT (JSON für Planung, sonst Text):
    Wenn du Trainings planst:
    {{
      "action": "propose",
      "summary": "Kurze Zusammenfassung (z.B. 'Hier ist der Plan für Woche 1...')",
      "workouts": [
        {{ "datum": "YYYY-MM-DD", "titel": "...", "beschreibung": "..." }},
        {{ "datum": "YYYY-MM-DD", "titel": "...", "beschreibung": "..." }}
      ]
    }}
    
    Wenn du nur analysierst/antwortest:
    Einfacher Text (nutze Markdown Tabellen für Daten).
    """

    try:
        model = genai.GenerativeModel('gemini-flash-latest') # 1.5 Flash ist super stabil & günstig
        
        prompt_content = [system_instruction]
        if is_audio:
            prompt_content.append({"mime_type": user_input.type, "data": user_input.read()})
        else:
            prompt_content.append(f"User: {text_val}")

        with st.spinner("..."):
            response = model.generate_content(prompt_content)
            reply_text = response.text.strip()
            
            # JSON Check
            if "action" in reply_text and "propose" in reply_text:
                # JSON bereinigen
                clean_json = reply_text.replace("```json", "").replace("```", "").strip()
                try:
                    data = json.loads(clean_json)
                    
                    # ENTWURF SPEICHERN
                    st.session_state.pending_plan = data['workouts']
                    
                    # Tabelle anzeigen
                    st.session_state.messages.append({"role": "model", "content": data['summary']})
                    st.chat_message("assistant").write(data['summary'])
                    
                    # DataFrame für Vorschau
                    df = pd.DataFrame(data['workouts'])
                    st.dataframe(df, hide_index=True)
                    
                    st.info("Sage 'Passt' oder 'Hochladen', um diese Einheiten zu speichern.")
                    
                except Exception as e:
                    st.error(f"Fehler beim Lesen des Plans: {e}")
                    st.write(reply_text)
            else:
                # Normale Textantwort
                st.session_state.messages.append({"role": "model", "content": reply_text})
                st.chat_message("assistant").write(reply_text)

    except Exception as e:
        st.error(f"Fehler: {e}")

