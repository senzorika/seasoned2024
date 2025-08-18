import streamlit as st
import pandas as pd
import json
from datetime import datetime
import urllib.parse
import sqlite3
import hashlib
import streamlit.components.v1 as components
import random

# --- Základné nastavenia a inicializácia ---
st.set_page_config(page_title="Hodnotenie vzoriek", page_icon="🧪", layout="wide")

# --- Databázové funkcie ---
def init_database():
    db_path = "consumervote.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS evaluation_settings (id INTEGER PRIMARY KEY, session_name TEXT, session_active BOOLEAN, samples_count INTEGER, samples_names TEXT, session_winner TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS evaluations (id INTEGER PRIMARY KEY AUTOINCREMENT, session_name TEXT, evaluator_name TEXT NOT NULL, evaluation_data TEXT NOT NULL, comment TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS device_tracking (id INTEGER PRIMARY KEY AUTOINCREMENT, device_fingerprint TEXT NOT NULL, ip_address TEXT, user_agent TEXT, session_name TEXT, last_evaluation TIMESTAMP, UNIQUE(device_fingerprint, session_name))')
    cursor.execute('CREATE TABLE IF NOT EXISTS admin_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, session_token TEXT UNIQUE NOT NULL, ip_address TEXT, user_agent TEXT, created_at TIMESTAMP, last_activity TIMESTAMP, expires_at TIMESTAMP)')
    if cursor.execute('SELECT COUNT(*) FROM evaluation_settings').fetchone()[0] == 0:
        cursor.execute("INSERT INTO evaluation_settings (id, session_name, session_active, samples_count, samples_names) VALUES (1, 'Nové hodnotenie', 0, 0, '[]')")
    try:
        cursor.execute('ALTER TABLE evaluation_settings ADD COLUMN session_winner TEXT')
    except sqlite3.OperationalError: pass
    conn.commit()
    conn.close()

# --- Overovanie a správa session ---
ADMIN_PASSWORD_MD5 = hashlib.md5("consumervote24".encode()).hexdigest()

def get_client_info():
    try:
        from streamlit.web.server.server import Server
        session_info = Server.get_current()._get_session_info_for_client(st.session_state.session_id)
        headers = session_info.headers
        ip = headers.get('x-forwarded-for', '').split(',')[0].strip() or headers.get('x-real-ip', '') or "unknown"
        ua = headers.get('user-agent', 'unknown')
        return ip, ua
    except Exception: return "unknown", "unknown"

def verify_admin_session(token):
    if not token: return False
    with sqlite3.connect("consumervote.db") as conn:
        cursor = conn.cursor()
        res = cursor.execute("SELECT id FROM admin_sessions WHERE session_token = ? AND expires_at > datetime('now')", (token,)).fetchone()
        if res:
            cursor.execute("UPDATE admin_sessions SET last_activity = datetime('now') WHERE session_token = ?", (token,))
            conn.commit()
            return True
    return False

def authenticate_admin():
    token = st.session_state.get('admin_session_token')
    st.session_state.admin_authenticated = verify_admin_session(token)

# --- Získavanie a ukladanie dát ---
def get_state():
    with sqlite3.connect("consumervote.db") as conn:
        conn.row_factory = sqlite3.Row
        state = conn.execute('SELECT * FROM evaluation_settings ORDER BY id DESC LIMIT 1').fetchone()
        evaluations = conn.execute('SELECT * FROM evaluations WHERE session_name = ?', (state['session_name'],)).fetchall()
        return dict(state), [dict(e) for e in evaluations]

def save_settings(name, count, names, active):
    with sqlite3.connect("consumervote.db") as conn:
        conn.execute('UPDATE evaluation_settings SET session_name=?, samples_count=?, samples_names=?, session_active=?, session_winner=NULL WHERE id=1', (name, count, json.dumps(names), active))
        conn.commit()

def save_evaluation(session_name, evaluator, data, comment):
    with sqlite3.connect("consumervote.db") as conn:
        conn.execute('INSERT INTO evaluations (session_name, evaluator_name, evaluation_data, comment) VALUES (?, ?, ?, ?)', (session_name, evaluator, json.dumps(data), comment))
        conn.commit()

def save_winner(session_name, winner):
    with sqlite3.connect("consumervote.db") as conn:
        conn.execute('UPDATE evaluation_settings SET session_winner = ? WHERE session_name = ?', (winner, session_name))
        conn.commit()

# --- CSS a pomocné UI funkcie ---
def render_css():
    st.markdown("""<style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap'); body {font-family: 'Inter', sans-serif;} .main-title {text-align: center;} .stButton>button {border-radius: 0.5rem;} .stTabs [data-baseweb="tab-list"] {gap: 24px;} .stTabs [data-baseweb="tab"] {font-size: 1.1rem; padding: 10px 16px;}</style>""", unsafe_allow_html=True)

# --- Komponenty a "Stránky" Aplikácie ---

def render_login_page():
    st.markdown('<h1 class="main-title">🔐 Administrácia</h1>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        with st.form("login_form"):
            password = st.text_input("Heslo", type="password", label_visibility="collapsed", placeholder="Zadajte heslo")
            submitted = st.form_submit_button("Prihlásiť sa", use_container_width=True, type="primary")
            if submitted:
                if hashlib.md5(password.encode()).hexdigest() == ADMIN_PASSWORD_MD5:
                    ip, ua = get_client_info()
                    token = hashlib.md5(f"{ip}_{ua}_{datetime.now().timestamp()}".encode()).hexdigest()
                    with sqlite3.connect("consumervote.db") as conn:
                        conn.execute("INSERT INTO admin_sessions (session_token, ip_address, user_agent, expires_at) VALUES (?, ?, ?, datetime('now', '+24 hours'))", (token, ip, ua))
                    st.session_state.admin_session_token = token
                    st.rerun()
                else:
                    st.error("Nesprávne heslo.")

def render_admin_dashboard():
    state, evaluations = get_state()
    st.markdown(f'<h1 class="main-title">{state["session_name"]}</h1>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["📊 Prehľad", "⚙️ Nastavenia", "🏆 Výsledky a losovanie"])

    with tab1: # Prehľad
        status_text = "🟢 AKTÍVNE" if state['session_active'] else "🔴 NEAKTÍVNE"
        st.header(f"Status: {status_text}")
        
        c1, c2 = st.columns(2)
        c1.metric("Počet hodnotení", len(evaluations))
        c2.metric("Počet vzoriek", state['samples_count'])
        
        st.divider()

        if state['session_active']:
            st.subheader("QR kód pre hodnotenie")
            app_url = "https://consumervote.streamlit.app"
            evaluator_url = f"{app_url}/?mode=evaluator"
            encoded_url = urllib.parse.quote(evaluator_url)
            qr_html = f'<html><body style="margin:0;display:flex;justify-content:center;"><img src="https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded_url}"></body></html>'
            components.html(qr_html, height=310)
            
            st.link_button("Zobraziť QR na celej obrazovke", f"/?mode=qr", use_container_width=True)

    with tab2: # Nastavenia
        st.header("Nastavenia hodnotenia")
        with st.form("settings_form"):
            session_name = st.text_input("Názov hodnotenia", value=state['session_name'])
            samples_count = st.number_input("Počet vzoriek", min_value=2, max_value=20, value=max(2, state['samples_count']))
            samples_names_json = json.loads(state['samples_names']) if state.get('samples_names') else []
            sample_names = [st.text_input(f"Vzorka {i+1}", value=samples_names_json[i] if i < len(samples_names_json) else f"Vzorka {i+1}", key=f"s_{i}") for i in range(samples_count)]
            
            c1, c2, c3 = st.columns([2,2,1])
            if c1.form_submit_button("Uložiť a spustiť", use_container_width=True, type="primary"):
                save_settings(session_name, samples_count, sample_names, True)
                st.success("Hodnotenie bolo spustené!")
                st.rerun()
            if c2.form_submit_button("Zastaviť hodnotenie", use_container_width=True):
                save_settings(state['session_name'], state['samples_count'], json.loads(state['samples_names']), False)
                st.warning("Hodnotenie bolo zastavené.")
                st.rerun()
            if c3.form_submit_button("Reset", use_container_width=True):
                 with sqlite3.connect("consumervote.db") as conn:
                    conn.execute('DELETE FROM evaluations WHERE session_name = ?', (state['session_name'],))
                    conn.execute('DELETE FROM device_tracking WHERE session_name = ?', (state['session_name'],))
                    conn.execute('UPDATE evaluation_settings SET session_winner = NULL WHERE session_name = ?', (state['session_name'],))
                 st.success("Všetky hodnotenia a výherca pre túto session boli vymazané.")
                 st.rerun()

    with tab3: # Výsledky
        st.header("Výsledky a export")
        if not evaluations:
            st.info("Zatiaľ žiadne hodnotenia na zobrazenie.")
        else:
            # --- FIX: Pridaná kontrola, či kľúč existuje, aby sa predišlo KeyError ---
            current_sample_names = json.loads(state['samples_names'])
            scores = {name: 0 for name in current_sample_names}
            
            for ev in evaluations:
                data = json.loads(ev['evaluation_data'])
                for name, rank in data.items():
                    if name in scores: # Táto kontrola zabráni pádu aplikácie
                        if rank == 1: scores[name] += 3
                        elif rank == 2: scores[name] += 2
                        elif rank == 3: scores[name] += 1

            sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
            results_df = pd.DataFrame(sorted_scores, columns=['Vzorka', 'Body'])
            results_df.index += 1
            st.dataframe(results_df, use_container_width=True)

            st.divider()
            st.subheader("Losovanie výhercu")
            if state.get('winner'):
                st.success(f"**Vylosovaný výherca je: {state['winner']}**")
            else:
                if st.button("🎲 Vylosovať výhercu", use_container_width=True):
                    evaluators = list(set(e['evaluator_name'] for e in evaluations))
                    if evaluators:
                        winner = random.choice(evaluators)
                        save_winner(state['session_name'], winner)
                        st.balloons()
                        st.rerun()

            st.divider()
            st.subheader("Export dát")
            export_df = pd.DataFrame([{'hodnotiteľ': e['evaluator_name'], 'komentár': e['comment'], 'čas': e['created_at'], **json.loads(e['evaluation_data'])} for e in evaluations])
            st.download_button("Stiahnuť CSV", export_df.to_csv(index=False).encode('utf-8'), f"export_{state['session_name']}.csv", "text/csv", use_container_width=True)
    
    with st.sidebar:
        st.title("Admin Menu")
        if st.button("Odhlásiť sa", use_container_width=True):
            token = st.session_state.get('admin_session_token')
            if token:
                with sqlite3.connect("consumervote.db") as conn: conn.execute("DELETE FROM admin_sessions WHERE session_token = ?", (token,))
            st.session_state.admin_authenticated = False
            if 'admin_session_token' in st.session_state: del st.session_state['admin_session_token']
            st.rerun()

def render_evaluator_interface():
    state, _ = get_state()
    st.markdown(f'<h1 class="main-title">{state["session_name"]}</h1>', unsafe_allow_html=True)
    
    if not state['session_active']:
        st.error("Hodnotenie momentálne nie je aktívne.")
        return
        
    fingerprint, ip, ua = get_client_info()
    with sqlite3.connect("consumervote.db") as conn:
        res = conn.execute('SELECT last_evaluation FROM device_tracking WHERE device_fingerprint = ? AND session_name = ?', (fingerprint, state['session_name'])).fetchone()
    
    if res:
        last_eval = datetime.strptime(res[0], '%Y-%m-%d %H:%M:%S')
        if (datetime.now() - last_eval).total_seconds() < 3600:
            rem_min = int(60 - (datetime.now() - last_eval).total_seconds() / 60)
            st.warning(f"Z tohto zariadenia už bolo hodnotené. Skúste znova o {rem_min} minút.")
            return

    if st.session_state.get('evaluation_submitted'):
        st.success("Ďakujeme za hodnotenie!")
        if st.button("Odoslať ďalšie hodnotenie", use_container_width=True):
            st.session_state.evaluation_submitted = False
            st.rerun()
        return

    with st.form("evaluation_form"):
        evaluator_name = st.text_input("Vaše meno alebo prezývka")
        samples = json.loads(state['samples_names'])
        options = [''] + samples
        first = st.selectbox("1. miesto (najlepšia)", options, format_func=lambda x: "Vyberte..." if x == '' else x)
        second = st.selectbox("2. miesto", [o for o in options if o != first], format_func=lambda x: "Vyberte..." if x == '' else x)
        third = st.selectbox("3. miesto", [o for o in options if o not in [first, second]], format_func=lambda x: "Vyberte..." if x == '' else x)
        comment = st.text_area("Komentár (voliteľný)")
        
        if st.form_submit_button("Odoslať hodnotenie", type="primary", use_container_width=True):
            if not evaluator_name.strip() or not first:
                st.error("Meno a aspoň 1. miesto sú povinné.")
            else:
                eval_data = {s: 999 for s in samples}
                if first: eval_data[first] = 1
                if second: eval_data[second] = 2
                if third: eval_data[third] = 3
                
                save_evaluation(state['session_name'], evaluator_name.strip(), eval_data, comment.strip())
                with sqlite3.connect("consumervote.db") as conn:
                    conn.execute('INSERT OR REPLACE INTO device_tracking (device_fingerprint, session_name, last_evaluation, ip_address, user_agent) VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?)', (fingerprint, state['session_name'], ip, ua))
                
                st.session_state.evaluation_submitted = True
                st.rerun()

def qr_display_page():
    # Táto funkcia je v poriadku
    st.markdown("<style>.stSidebar, .stHeader, footer { display: none !important; } .main .block-container { max-width: 100% !important; padding: 0 !important; margin: 0 !important; }</style>", unsafe_allow_html=True)
    state, _ = get_state()
    if not state['session_active']:
        error_html = "<html><head><style>body { margin: 0; display: flex; justify-content: center; align-items: center; height: 100vh; font-family: sans-serif; background-color: #f0f2f6; } .msg { padding: 2rem; background: white; border-radius: 1rem; box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center; } h2 { color: #ef4444; }</style></head><body><div class='msg'><h2>Hodnotenie nie je aktívne</h2></div></body></html>"
        components.html(error_html, height=600)
        return
    app_url = "https://consumervote.streamlit.app"
    evaluator_url = f"{app_url}/?mode=evaluator"
    encoded_url = urllib.parse.quote(evaluator_url)
    qr_page_html = f"""<!DOCTYPE html><html><head><style>body {{margin: 0; padding: 0; display: flex; justify-content: center; align-items: center; height: 100vh; font-family: sans-serif; background-color: #f0f2f6;}} .container {{text-align: center; background-color: white; padding: 2rem 3rem 3rem 3rem; border-radius: 1.5rem; box-shadow: 0 10px 30px rgba(0,0,0,0.1);}} h1 {{font-size: 2.2rem; color: #111827;}} p {{font-size: 1.2rem; color: #4b5563;}}</style></head><body><div class="container"><h1>{state['session_name']}</h1><p>Naskenujte kód a začnite hodnotiť</p><img src="https://api.qrserver.com/v1/create-qr-code/?size=400x400&ecc=H&data={encoded_url}" alt="QR Code"></div></body></html>"""
    components.html(qr_page_html, height=800, scrolling=True)

# --- Hlavná funkcia a smerovač (Router) ---
def main():
    """Hlavná funkcia, ktorá riadi, čo sa používateľovi zobrazí."""
    init_database()
    render_css()
    authenticate_admin()
    
    mode = st.query_params.get('mode', '').lower()

    if mode == 'evaluator':
        render_evaluator_interface()
    elif mode == 'qr':
        qr_display_page()
    else:
        if st.session_state.get('admin_authenticated'):
            render_admin_dashboard()
        else:
            render_login_page()

if __name__ == "__main__":
    if 'session_id' not in st.session_state:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        st.session_state.session_id = get_script_run_ctx().session_id
    
    main()