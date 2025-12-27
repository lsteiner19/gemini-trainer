import streamlit as st
import google.generativeai as genai
import requests
import json
import pandas as pd
import altair as alt
from datetime import datetime, timedelta

# --- 1. Grundeinstellungen ---
st.set_page_config(page_title="Mein AI Coach", page_icon="🎙️", layout="wide")
st.title("🎙️ Mein sprechender Coach")

# --- 2. Keys laden ---
with st.sidebar:
    st.header("⚙️ Setup")
    if "GOOGLE_API_KEY" in st.secrets:
        google_api_key = st.secrets["GOOGLE_API_KEY"]
    else:
        google_api_key = st.text_input("Google Key", type="password")

    if "INTERVALS_ID" in st.secrets:
        intervals_id = st.secrets["INTERVALS_ID"]
    else:
        intervals_id = st.text_input("Athlete ID")

    if "INTERVALS_KEY" in st.secrets:
        intervals_key = st.secrets["INTERVALS_KEY"]
    else:
        intervals_key = st.text_input("Intervals API Key", type="password")

# --- 3. API Funktionen ---

def get_activities(limit=10):
    """Holt vergangene Aktivitäten der letzten 30 Tage"""
    # FEHLER-FIX: Intervals braucht Datumsangaben, kein reines Limit
    today = datetime.today().strftime('%Y-%m-%d')
    start_date = (datetime.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/activities?oldest={start_date}&newest={today}"
    
    try:
        resp = requests.get(url, auth=('API_KEY', intervals_key))
        if resp.status_code == 200:
            # Wir sortieren sie sicherheitshalber und nehmen die neuesten
            data = resp.json()
            # Falls data leer ist, geben wir leere Liste zurück
            if not data:
                return []
            # Neueste zuerst
            return sorted(data, key=lambda x: x['start_date_local'], reverse=True)[:limit]
        else:
            # WICHTIG: Wir geben jetzt den genauen Fehlertext aus, falls es wieder passiert
            st.error(f"Fehler 422 Details: {resp.text}") 
            return []
    except Exception as e:
        st.error(f"Verbindungsfehler: {e}")
        return []

def get_streams(activity_id):
    """Holt GPS und Werte"""
    url = f"https://intervals.icu/api/v1/activity/{activity_id}/streams?types=latlng,heartrate,watts,time"
    resp = requests.get(url, auth=('API_KEY', intervals_key))
    return resp.json() if resp.status_code == 200 else []

def get_future_events(days=21):
    """Holt Zukunft für Auto-Kontext"""
    today = datetime.today().strftime('%Y-%m-%d')
    future = (datetime.today() + timedelta(days=days)).strftime('%Y-%m-%d')
    url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/events?oldest={today}&newest={future}"
    resp = requests.get(url, auth=('API_KEY', intervals_key))
    return resp.json() if resp.status_code == 200 else []

def create_event(payload):
    url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/events"
    resp = requests.post(url, json=payload, auth=('API_KEY', intervals_key))
    return resp.status_code, resp.text

# --- 4. Layout ---

tab1, tab2 = st.tabs(["📊 Analyse & Karte", "💬 AI Coach (Sprache)"])

# === TAB 1: ANALYSE ===
with tab1:
    st.header("Vergangene Einheiten")
    if intervals_key and intervals_id:
        activities = get_activities(limit=15)
        
        if not activities:
            st.warning("Keine Aktivitäten gefunden. Hast du Workouts in Intervals.icu hochgeladen?")
        else:
            # Dropdown bauen
            # Wir formatieren das Label schöner, damit man sieht was es ist
            act_options = {}
            for a in activities:
                # Sicherstellen, dass Felder existieren
                date = a.get('start_date_local', 'Unbekannt')[:10]
                name = a.get('name', 'Unbenannt')
                act_id = a.get('id')
                label = f"{date}: {name}"
                act_options[label] = act_id
            
            selection = st.selectbox("Wähle eine Einheit zur Analyse:", list(act_options.keys()))
            
            if selection:
                current_id = act_options[selection]
                # Daten holen
                streams = get_streams(current_id)
                
                if streams:
                    data = {s['type']: s['data'] for s in streams}
                    
                    if 'time' in data:
                        df = pd.DataFrame(data)
                        
                        # Karte
                        if 'latlng' in data:
                            lat_lon = pd.DataFrame(data['latlng'], columns=['lat', 'lon'])
                            # Filter 0-Werte
                            lat_lon = lat_lon[(lat_lon['lat'] != 0) & (lat_lon['lon'] != 0)]
                            st.map(lat_lon, color="#FF0000") # Rote Linie
                        
                        # Diagramm mit Zoom
                        st.subheader("Leistungsdaten")
                        max_time = int(df['time'].max() / 60)
                        zoom = st.slider("Zeitbereich (Minuten)", 0, max_time, (0, max_time))
                        
                        # Filtern
                        mask = (df['time'] >= zoom[0]*60) & (df['time'] <= zoom[1]*60)
                        df_zoom = df[mask]
                        
                        # Altair Chart
                        chart_data = df_zoom.melt('time', var_name='Sensor', value_name='Wert')
                        chart_data = chart_data[chart_data['Sensor'].isin(['heartrate', 'watts'])]
                        
                        c = alt.Chart(chart_data).mark_line().encode(
                            x='time', y='Wert', color='Sensor', tooltip=['time', 'Wert']
                        ).interactive()
                        st.altair_chart(c, use_container_width=True)
                    else:
                        st.info("Diese Einheit hat keine Zeit-Daten (vielleicht manuell eingetragen?).")
                else:
                    st.warning("Keine Detaildaten (GPS/Watt/Puls) für diese Einheit verfügbar.")

# === TAB 2: AI COACH MIT SPRACHE & AUTO-KONTEXT ===
with tab2:
    st.header("Sprich mit deinem Coach")
    
    # 1. Chat History initialisieren
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "model", "content": "Ich höre zu. Drücke auf 'Aufnahme' oder schreibe mir."}]

    for msg in st.session_state.messages:
        role = "assistant" if msg["role"] == "model" else msg["role"]
        st.chat_message(role).write(msg["content"])

    # 2. INPUT: Entweder Audio ODER Text
    col_audio, col_text = st.columns([1, 4])
    with col_audio:
        audio_val = st.audio_input("🎙️ Aufnahme")
    with col_text:
        text_val = st.chat_input("Nachricht tippen...")

    # Logik: Was wurde eingegeben?
    user_input = None
    is_audio = False

    if audio_val:
        user_input = audio_val # Das ist eine Datei (Bytes)
        is_audio = True
    elif text_val:
        user_input = text_val
        is_audio = False

    # 3. VERARBEITUNG
    if user_input:
        if not google_api_key:
            st.error("Bitte API Key eingeben!")
            st.stop()

        # A) Anzeige im Chat
        if is_audio:
            st.session_state.messages.append({"role": "user", "content": "🎤 *Audio-Nachricht gesendet*"})
            with st.chat_message("user"):
                st.audio(user_input)
        else:
            st.session_state.messages.append({"role": "user", "content": user_input})
            st.chat_message("user").write(user_input)

        # B) AUTO-KONTEXT LADEN
        # Wir prüfen nur bei Text auf Keywords. Bei Audio laden wir zur Sicherheit IMMER den Kontext, 
        # weil wir den Text ja noch nicht kennen.
        context_str = "Kein Kalender-Kontext."
        
        should_load_calendar = False
        
        if is_audio:
            should_load_calendar = True # Bei Audio wissen wir nicht was kommt -> sicherheitshalber laden
        elif isinstance(user_input, str):
            # Schlüsselwörter Check
            keywords = ["plan", "kalender", "woche", "morgen", "übermorgen", "rennen", "training", "wann", "freitag", "samstag", "sonntag", "montag"]
            if any(word in user_input.lower() for word in keywords):
                should_load_calendar = True
        
        if should_load_calendar:
            with st.status("🔍 Prüfe Kalender...", expanded=False) as status:
                events = get_future_events(days=14)
                # Daten vereinfachen für die KI
                simple_ev = [{"date": e['start_date_local'][:10], "name": e['name'], "cat": e.get('category')} for e in events]
                context_str = f"GEPLANTER KALENDER (Nächste 14 Tage): {json.dumps(simple_ev)}"
                status.update(label="📅 Kalender-Daten automatisch geladen!", state="complete")

        # C) KI ANFRAGE
        genai.configure(api_key=google_api_key)
        # Wir nutzen Gemini 2.0 Flash (kann Audio UND Text)
        model = genai.GenerativeModel('gemini-2.0-flash')

        system_instruction = f"""
        Du bist ein Radsport-Coach. Datum: {datetime.today().strftime('%Y-%m-%d')}.
        
        HINTERGRUND-WISSEN:
        {context_str}
        
        AUFGABE:
        Analysiere die Anfrage (Text oder Audio).
        - Wenn der User ein Training will -> JSON (action: create).
        - Wenn der User krank ist -> JSON (action: create -> Ruhe/Note eintragen).
        - Sonst -> Antworte hilfreich als Text.
        
        FORMAT FÜR AKTIONEN (JSON):
        {{
          "action": "create",
          "category": "WORKOUT" (oder "NOTE"),
          "datum": "YYYY-MM-DD",
          "titel": "Titel",
          "beschreibung": "Details",
          "text": "Antwort an User"
        }}
        """

        try:
            with st.spinner("Coach hört zu & denkt nach..."):
                # Wir bauen die Prompt-Liste
                prompt_parts = [system_instruction]
                
                if is_audio:
                    prompt_parts.append("Hier ist die Audio-Anfrage des Users:")
                    prompt_parts.append(user_input) # Audio direkt an Gemini!
                else:
                    prompt_parts.append(f"User Anfrage: {user_input}")

                response = model.generate_content(prompt_parts)
                clean_reply = response.text.replace("```json", "").replace("```", "").strip()

                # JSON Parsen versuchen
                final_text = clean_reply
                try:
                    if "{" in clean_reply: # Nur parsen wenn es wie JSON aussieht
                        data = json.loads(clean_json)
                        if data.get("action") == "create":
                            payload = {
                                "category": data.get("category", "WORKOUT"),
                                "start_date_local": f"{data['datum']}T09:00:00",
                                "name": data['titel'],
                                "description": data.get("beschreibung", ""),
                                "type": "Ride"
                            }
                            # Senden
                            code, txt = create_event(payload)
                            if code == 200:
                                final_text = f"✅ **Ausgeführt:** {data['titel']} am {data['datum']}\n\n{data.get('text', '')}"
                            else:
                                final_text = f"❌ Fehler bei Intervals: {txt}"
                        elif "text" in data:
                             final_text = data["text"]
                except:
                    pass # Wenn kein JSON, einfach Text ausgeben

        except Exception as e:
            final_text = f"Fehler: {e}"

        st.session_state.messages.append({"role": "model", "content": final_text})
        st.chat_message("assistant").write(final_text)

