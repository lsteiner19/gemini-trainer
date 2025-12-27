import streamlit as st
import google.generativeai as genai
import requests
import json
import pandas as pd
import altair as alt
from datetime import datetime, timedelta

# --- 1. Grundeinstellungen ---
st.set_page_config(page_title="Mein Pro-Coach", page_icon="🚴", layout="wide")
st.title("🚴 Mein AI Performance Center")

# --- 2. Keys automatisch laden ---
with st.sidebar:
    st.header("Einstellungen")
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

# --- 3. Komplexe API Funktionen ---

def get_activities(limit=5):
    """Holt die letzten durchgeführten Aktivitäten"""
    url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/activities?limit={limit}"
    resp = requests.get(url, auth=('API_KEY', intervals_key))
    return resp.json() if resp.status_code == 200 else []

def get_streams(activity_id):
    """Holt die Sekunden-Daten (GPS, Puls, Watt) für eine Einheit"""
    # Wir fragen explizit nach latlng (GPS), heartrate, watts, velocity_smooth
    url = f"https://intervals.icu/api/v1/activity/{activity_id}/streams?types=latlng,heartrate,watts,velocity_smooth,time"
    resp = requests.get(url, auth=('API_KEY', intervals_key))
    return resp.json() if resp.status_code == 200 else []

def get_future_events(days=90):
    """Holt geplante Trainings UND Rennen"""
    today = datetime.today().strftime('%Y-%m-%d')
    future = (datetime.today() + timedelta(days=days)).strftime('%Y-%m-%d')
    url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/events?oldest={today}&newest={future}"
    resp = requests.get(url, auth=('API_KEY', intervals_key))
    return resp.json() if resp.status_code == 200 else []

def create_event(payload):
    url = f"https://intervals.icu/api/v1/athlete/{intervals_id}/events"
    resp = requests.post(url, json=payload, auth=('API_KEY', intervals_key))
    return resp.status_code, resp.text

# --- 4. Dashboard & Analyse Bereich ---

tab1, tab2 = st.tabs(["📊 Analyse & Karte", "💬 Planung & Coach"])

with tab1:
    st.header("Deep Dive Analyse")
    if intervals_key and intervals_id:
        activities = get_activities(limit=10)
        if activities:
            # Dropdown zur Auswahl der Aktivität
            opts = {f"{a['start_date_local'][:10]} - {a['name']}": a['id'] for a in activities}
            selection = st.selectbox("Wähle eine Einheit:", list(opts.keys()))
            
            if selection:
                act_id = opts[selection]
                
                with st.spinner("Lade GPS und Sensordaten..."):
                    streams = get_streams(act_id)
                
                if streams:
                    # Daten in Pandas DataFrame umwandeln
                    data = {}
                    for s in streams:
                        data[s['type']] = s['data']
                    
                    # DataFrame erstellen (nur wenn Zeitdaten da sind)
                    if 'time' in data:
                        df = pd.DataFrame(data)
                        
                        # GPS Daten aufbereiten (Intervals liefert [lat, lon] als Liste)
                        if 'latlng' in data:
                            # Wir splitten die Liste in zwei Spalten für st.map
                            lat_lon = pd.DataFrame(data['latlng'], columns=['lat', 'lon'])
                            # Bereinigen (0,0 Koordinaten entfernen)
                            lat_lon = lat_lon[(lat_lon['lat'] != 0) & (lat_lon['lon'] != 0)]
                            
                            st.subheader("🗺️ Die Strecke")
                            st.map(lat_lon)

                        # Filter: "Nur die ersten X Minuten"
                        st.divider()
                        st.subheader("📈 Werte-Verlauf")
                        
                        max_min = int(df['time'].max() / 60)
                        range_min = st.slider("Zeitfenster (Minuten):", 0, max_min, (0, max_min))
                        
                        # Filtern basierend auf Sekunden
                        start_sec = range_min[0] * 60
                        end_sec = range_min[1] * 60
                        df_filtered = df[(df['time'] >= start_sec) & (df['time'] <= end_sec)]
                        
                        # Diagramm zeichnen (Puls & Watt)
                        chart_data = df_filtered.melt('time', var_name='Sensor', value_name='Wert')
                        # Wir filtern nur Puls und Watt für die Grafik
                        chart_data = chart_data[chart_data['Sensor'].isin(['heartrate', 'watts'])]
                        
                        chart = alt.Chart(chart_data).mark_line().encode(
                            x=alt.X('time', title='Sekunden'),
                            y='Wert',
                            color='Sensor',
                            tooltip=['time', 'Wert', 'Sensor']
                        ).interactive()
                        
                        st.altair_chart(chart, use_container_width=True)
                    else:
                        st.warning("Keine Zeit-Streams gefunden.")
                else:
                    st.warning("Keine Detaildaten (Streams) für diese Aktivität verfügbar.")

with tab2:
    st.header("AI Coach: Planung & Strategie")
    
    # Context laden
    if st.button("📅 Kalender & Rennen scannen"):
        with st.spinner("Analysiere Saisonplanung..."):
            future_events = get_future_events()
            st.session_state['events_context'] = future_events
            st.success(f"{len(future_events)} Einträge geladen (Rennen & Trainings).")

    # Chat Interface
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "model", "content": "Ich bin bereit. Sag mir 'Ich bin krank' oder 'Erstelle Plan für mein Rennen'."}]

    for msg in st.session_state.messages:
        role = "assistant" if msg["role"] == "model" else msg["role"]
        st.chat_message(role).write(msg["content"])

    prompt = st.chat_input("Nachricht an den Coach...")

    if prompt:
        if not google_api_key:
            st.error("Key fehlt!")
            st.stop()

        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        # Kontext aufbauen
        context_str = "Keine Kalenderdaten geladen."
        if 'events_context' in st.session_state:
            # Wir filtern die Daten, damit der Prompt nicht zu riesig wird
            simple_events = []
            for e in st.session_state['events_context']:
                simple_events.append({
                    "date": e['start_date_local'][:10],
                    "name": e.get('name'),
                    "category": e.get('category'), # WORKOUT oder RACE
                    "type": e.get('type')
                })
            context_str = json.dumps(simple_events)

        system_instruction = f"""
        Du bist ein Elite-Radsport-Coach. Heute: {datetime.today().strftime('%Y-%m-%d')}.
        
        SITUATION DES ATHLETEN (Kommende Events):
        {context_str}
        
        DEINE AUFGABEN:
        1. **Planung:** Wenn ein Rennen ansteht, plane rückwärts (Tapering, Build-Phase).
        2. **Krankheit:** Wenn der User sagt "Ich bin krank", schlage vor, die nächsten Trainings zu löschen oder in "Ruhe" zu ändern.
        3. **Rennen eintragen:** Wenn der User sagt "Neues Rennen am...", erstelle ein Event mit category='RACE'.
        
        OUTPUT FORMAT (WICHTIG):
        Antworte IMMER im JSON-Format.
        
        Wenn du nur antwortest:
        {{ "action": "chat", "text": "Deine Antwort..." }}
        
        Wenn du ein Training oder Rennen erstellst:
        {{ 
          "action": "create", 
          "category": "WORKOUT" (oder "RACE"),
          "datum": "YYYY-MM-DD", 
          "titel": "...", 
          "beschreibung": "...",
          "text": "Antwort an User"
        }}
        """

        genai.configure(api_key=google_api_key)
        try:
            model = genai.GenerativeModel('gemini-2.0-flash') # Oder 'gemini-3-flash-preview'
            
            with st.spinner("Coach arbeitet..."):
                response = model.generate_content(system_instruction + f"\nUSER: {prompt}")
                clean_json = response.text.replace("```json", "").replace("```", "").strip()
                try:
                    data = json.loads(clean_json)
                    
                    if data.get("action") == "create":
                        # Payload bauen
                        payload = {
                            "category": data.get("category", "WORKOUT"),
                            "start_date_local": f"{data['datum']}T09:00:00",
                            "name": data['titel'],
                            "description": data.get("beschreibung", ""),
                            "type": "Ride"
                        }
                        status, txt = create_event(payload)
                        reply = f"✅ **Eintrag erstellt:** {data['titel']} am {data['datum']}\n\n{data['text']}"
                    
                    else:
                        reply = data.get("text", "Keine Antwort.")

                except json.JSONDecodeError:
                    reply = response.text # Fallback falls kein JSON

        except Exception as e:
            reply = f"Fehler: {e}"

        st.session_state.messages.append({"role": "model", "content": reply})
        st.chat_message("assistant").write(reply)
