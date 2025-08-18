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
    with sqlite3.connect("consumervote.db") as conn:
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, session_name TEXT NOT NULL, is_active BOOLEAN DEFAULT 0, samples_count INTEGER, samples_names TEXT, winner TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        cursor.execute('CREATE TABLE IF NOT EXISTS evaluations (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, evaluator_name TEXT NOT NULL, evaluation_data TEXT NOT NULL, comment TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(session_id) REFERENCES sessions(id))')
        cursor.execute('CREATE TABLE IF NOT EXISTS device_tracking (id INTEGER PRIMARY KEY AUTOINCREMENT, device_fingerprint TEXT NOT NULL, session_id INTEGER, last_evaluation TIMESTAMP, UNIQUE(device_fingerprint, session_id))')
        cursor.execute('CREATE TABLE IF NOT EXISTS admin_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, session_token TEXT UNIQUE NOT NULL, ip_address TEXT, user_agent TEXT, created_at TIMESTAMP, expires_at TIMESTAMP)')
        if cursor.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0:
            cursor.execute("INSERT INTO sessions (session_name, is_active, samples_count, samples_names) VALUES ('Moje prvé hodnotenie', 0, 3, '[\"Vzorka 1\", \"Vzorka 2\", \"Vzorka 3\"]')")

# --- Overovanie a správa session ---
ADMIN_PASSWORD_MD5 = hashlib.md5("consumervote24".encode()).hexdigest()

def get_client_info():
    try:
        from streamlit.web.server.server import Server
        session_info = Server.get_current()._get_session_info_for_client(st.session_state.session_id)
        if session_info and hasattr(session_info, 'headers'):
            headers = session_info.headers
            ip = headers.get('x-forwarded-for', '').split(',')[0].strip() or headers.get('x-real-ip', '') or "unknown"
            ua = headers.get('user-agent', 'unknown')
            return ip if ip else "unknown", ua if ua else "unknown"
    except Exception: return "unknown", "unknown"

def verify_admin_session(token):
    if not token: return False
    with sqlite3.connect("consumervote.db") as conn:
        return conn.execute("SELECT id FROM admin_sessions WHERE session_token = ? AND expires_at > datetime('now')", (token,)).fetchone() is not None

def authenticate_admin():
    st.session_state.admin_authenticated = verify_admin_session(st.session_state.get('admin_session_token'))

# --- Získavanie a ukladanie dát ---
def get_all_sessions():
    with sqlite3.connect("consumervote.db") as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute('SELECT * FROM sessions ORDER BY created_at DESC').fetchall()]

def get_active_session():
    with sqlite3.connect("consumervote.db") as conn:
        conn.row_factory = sqlite3.Row
        active_session = conn.execute('SELECT * FROM sessions WHERE is_active = 1').fetchone()
        if not active_session: return None, []
        evaluations = [dict(row) for row in conn.execute('SELECT * FROM evaluations WHERE session_id = ?', (active_session['id'],)).fetchall()]
        return dict(active_session), evaluations

def get_session_by_id(session_id):
    with sqlite3.connect("consumervote.db") as conn:
        conn.row_factory = sqlite3.Row
        session = conn.execute('SELECT * FROM sessions WHERE id = ?', (session_id,)).fetchone()
        if not session: return None, []
        evaluations = [dict(row) for row in conn.execute('SELECT * FROM evaluations WHERE session_id = ?', (session_id,)).fetchall()]
        return dict(session), evaluations

def save_winner(session_id, winner):
    with sqlite3.connect("consumervote.db") as conn:
        conn.execute('UPDATE sessions SET winner = ? WHERE id = ?', (winner, session_id))

# --- CSS ---
def render_css():
    st.markdown("""<style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap'); body {font-family: 'Inter', sans-serif;} .main-title {text-align: center;} .stButton>button {border-radius: 0.5rem;} .stTabs [data-baseweb="tab-list"] {gap: 24px;} .stTabs [data-baseweb="tab"] {font-size: 1.1rem; padding: 10px 16px;}</style>""", unsafe_allow_html=True)

# --- Komponenty a "Stránky" Aplikácie ---

def render_login_page():
    st.markdown('<h1 class="main-title">🔐 Administrácia</h1>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        with st.form("login_form"):
            password = st.text_input("Heslo", type="password", label_visibility="collapsed", placeholder="Zadajte heslo")
            if st.form_submit_button("Prihlásiť sa", use_container_width=True, type="primary"):
                if hashlib.md5(password.encode()).hexdigest() == ADMIN_PASSWORD_MD5:
                    ip, ua = get_client_info()
                    token = hashlib.md5(f"{ip}_{ua}_{datetime.now().timestamp()}".encode()).hexdigest()
                    with sqlite3.connect("consumervote.db") as conn:
                        conn.execute("INSERT INTO admin_sessions (session_token, ip_address, user_agent, expires_at) VALUES (?, ?, ?, datetime('now', '+24 hours'))", (token, ip, ua))
                    st.session_state.admin_session_token = token
                    st.rerun()
                else: st.error("Nesprávne heslo.")

def render_results_component(session, evaluations):
    """Zobrazí výsledky, losovanie a export pre danú session."""
    if not evaluations:
        st.info("Táto session zatiaľ nemá žiadne hodnotenia.")
        return

    # --- FIX: Nová logika pre "ligovú tabuľku" s bodovaním 5-3-1 ---
    st.subheader(f"Ligová tabuľka pre '{session['session_name']}'")
    
    POINTS = {1: 5, 2: 3, 3: 1}
    sample_names = json.loads(session['samples_names'])
    
    # Inicializácia štruktúry pre výsledky
    results_data = {name: {"points": 0, "1st": 0, "2nd": 0, "3rd": 0} for name in sample_names}

    # Spracovanie každého hodnotenia
    for ev in evaluations:
        data = json.loads(ev['evaluation_data'])
        for name, rank in data.items():
            if name in results_data:
                if rank in POINTS:
                    results_data[name]["points"] += POINTS[rank]
                    if rank == 1: results_data[name]["1st"] += 1
                    elif rank == 2: results_data[name]["2nd"] += 1
                    elif rank == 3: results_data[name]["3rd"] += 1

    # Konverzia na DataFrame pre zobrazenie
    table_data = []
    for name, stats in results_data.items():
        table_data.append({
            "Vzorka": name,
            "Body": stats["points"],
            "1. miesta": stats["1st"],
            "2. miesta": stats["2nd"],
            "3. miesta": stats["3rd"],
            "Celkovo v TOP3": stats["1st"] + stats["2nd"] + stats["3rd"]
        })
    
    results_df = pd.DataFrame(table_data)
    # Triedenie podľa bodov, potom podľa počtu 1. miest
    results_df = results_df.sort_values(by=["Body", "1. miesta"], ascending=[False, False]).reset_index(drop=True)
    results_df.index += 1
    results_df.index.name = "Poz."
    
    st.dataframe(results_df, use_container_width=True)
    st.divider()

    # Losovanie a export zostávajú rovnaké
    st.subheader("Losovanie výhercu")
    if session.get('winner'):
        st.success(f"**Vylosovaný výherca: {session['winner']}**")
    else:
        if st.button("🎲 Vylosovať výhercu z tejto session", use_container_width=True, key=f"draw_{session['id']}"):
            evaluators = list(set(e['evaluator_name'] for e in evaluations))
            if evaluators:
                winner = random.choice(evaluators)
                save_winner(session['id'], winner)
                st.balloons()
                st.rerun()
    st.divider()
    
    st.subheader("Export dát")
    export_df = pd.DataFrame([{'hodnotiteľ': e['evaluator_name'], 'komentár': e['comment'], 'čas': e['created_at'], **json.loads(e['evaluation_data'])} for e in evaluations])
    st.download_button("Stiahnuť CSV", export_df.to_csv(index=False).encode('utf-8'), f"export_{session['session_name']}.csv", "text/csv", use_container_width=True)

def render_admin_dashboard():
    st.markdown('<h1 class="main-title">Administrátorský panel</h1>', unsafe_allow_html=True)
    tab1, tab2, tab3 = st.tabs(["📊 Aktívna Session", "🗂️ Manažment Sessions", "🏆 Výsledky"])

    with tab1:
        active_session, evaluations = get_active_session()
        if not active_session:
            st.warning("Žiadna session nie je aktívna. Prejdite do 'Manažment Sessions' a jednu aktivujte.")
        else:
            st.header(f"Aktívne hodnotenie: {active_session['session_name']}")
            c1, c2 = st.columns(2)
            c1.metric("Počet hodnotení", len(evaluations))
            c2.metric("Počet vzoriek", active_session['samples_count'])
            st.divider()
            st.subheader("QR kód pre hodnotenie")
            app_url = "https://consumervote.streamlit.app"
            evaluator_url = f"{app_url}/?mode=evaluator"
            encoded_url = urllib.parse.quote(evaluator_url)
            qr_html = f'<html><body style="margin:0;display:flex;justify-content:center;"><img src="https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded_url}"></body></html>'
            components.html(qr_html, height=310)
            st.link_button("Zobraziť QR na celej obrazovke", "/?mode=qr", use_container_width=True)
            st.divider()
            if st.button("Zastaviť túto session", use_container_width=True):
                with sqlite3.connect("consumervote.db") as conn:
                    conn.execute("UPDATE sessions SET is_active = 0 WHERE id = ?", (active_session['id'],))
                st.success("Session bola zastavená."); st.rerun()

    with tab2:
        st.header("Vytvoriť novú session")
        with st.form("new_session_form"):
            session_name = st.text_input("Názov novej session")
            samples_count = st.number_input("Počet vzoriek", min_value=2, max_value=20, value=3)
            sample_names = [st.text_input(f"Vzorka {i+1}", key=f"new_s_{i}") for i in range(samples_count)]
            if st.form_submit_button("Vytvoriť", type="primary"):
                if session_name and all(sample_names):
                    with sqlite3.connect("consumervote.db") as conn:
                        conn.execute("INSERT INTO sessions (session_name, samples_count, samples_names) VALUES (?, ?, ?)", (session_name, samples_count, json.dumps(sample_names)))
                    st.success(f"Session '{session_name}' vytvorená."); st.rerun()
                else: st.error("Vyplňte všetky polia.")

        st.divider()
        st.header("Zoznam všetkých sessions")
        for session in get_all_sessions():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.subheader(session['session_name'])
                c1.caption(f"Vytvorené: {datetime.fromisoformat(session['created_at']).strftime('%d.%m.%Y %H:%M')}")
                if session['is_active']:
                    c2.success("AKTÍVNA")
                else:
                    if c2.button("Aktivovať", key=f"act_{session['id']}", use_container_width=True):
                        with sqlite3.connect("consumervote.db") as conn:
                            conn.execute("UPDATE sessions SET is_active = 0")
                            conn.execute("UPDATE sessions SET is_active = 1 WHERE id = ?", (session['id'],))
                        st.rerun()
                if c3.button("Vymazať", key=f"del_{session['id']}", type="secondary", use_container_width=True):
                    st.session_state.session_to_delete = session['id']
                if st.session_state.get('session_to_delete') == session['id']:
                    st.warning(f"Naozaj chcete zmazať session '{session['session_name']}'?")
                    cc1, cc2 = st.columns(2)
                    if cc1.button("Áno, zmazať", key=f"conf_del_{session['id']}", type="primary"):
                        with sqlite3.connect("consumervote.db") as conn:
                            conn.execute("DELETE FROM evaluations WHERE session_id = ?", (session['id'],))
                            conn.execute("DELETE FROM sessions WHERE id = ?", (session['id'],))
                        del st.session_state.session_to_delete; st.rerun()
                    if cc2.button("Zrušiť", key=f"canc_del_{session['id']}"):
                        del st.session_state.session_to_delete; st.rerun()

    with tab3:
        all_sessions = get_all_sessions()
        if not all_sessions:
            st.info("Najprv vytvorte session v 'Manažment Sessions'.")
        else:
            session_dict = {s['session_name']: s['id'] for s in all_sessions}
            selected_name = st.selectbox("Vyberte session pre zobrazenie výsledkov", options=session_dict.keys())
            session, evaluations = get_session_by_id(session_dict[selected_name])
            render_results_component(session, evaluations)
    
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
    st.markdown("""<style>[data-testid="stHeader"], footer, [data-testid="stSidebar"] {display: none; visibility: hidden;}</style>""", unsafe_allow_html=True)
    active_session, _ = get_active_session()

    if not active_session:
        st.error("Momentálne nie je aktívne žiadne hodnotenie.")
        return

    st.markdown(f'<h1 class="main-title">{active_session["session_name"]}</h1>', unsafe_allow_html=True)
    fingerprint, ip, ua = get_client_info()
    with sqlite3.connect("consumervote.db") as conn:
        res = conn.execute('SELECT last_evaluation FROM device_tracking WHERE device_fingerprint = ? AND session_id = ?', (fingerprint, active_session['id'])).fetchone()
    if res and (datetime.now() - datetime.strptime(res[0], '%Y-%m-%d %H:%M:%S')).total_seconds() < 3600:
        rem_min = int(60 - (datetime.now() - datetime.strptime(res[0], '%Y-%m-%d %H:%M:%S')).total_seconds() / 60)
        st.warning(f"Z tohto zariadenia už bolo hodnotené. Skúste znova o {rem_min} minút.")
        return
    if st.session_state.get('evaluation_submitted'):
        st.success("Ďakujeme za hodnotenie!")
        if st.button("Odoslať ďalšie hodnotenie", use_container_width=True):
            st.session_state.evaluation_submitted = False; st.rerun()
        return
    with st.form("evaluation_form"):
        evaluator_name = st.text_input("Vaše meno alebo prezývka")
        samples = json.loads(active_session['samples_names'])
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
                with sqlite3.connect("consumervote.db") as conn:
                    conn.execute('INSERT INTO evaluations (session_id, evaluator_name, evaluation_data, comment) VALUES (?, ?, ?, ?)', (active_session['id'], evaluator_name.strip(), json.dumps(eval_data), comment.strip()))
                    conn.execute('INSERT OR REPLACE INTO device_tracking (device_fingerprint, session_id, last_evaluation) VALUES (?, ?, CURRENT_TIMESTAMP)', (fingerprint, active_session['id']))
                st.session_state.evaluation_submitted = True; st.rerun()

def qr_display_page():
    st.markdown("<style>.stSidebar, .stHeader, footer { display: none !important; } .main .block-container { max-width: 100% !important; padding: 0 !important; margin: 0 !important; }</style>", unsafe_allow_html=True)
    active_session, _ = get_active_session()
    if not active_session:
        error_html = "<html><head><style>body { margin: 0; display: flex; justify-content: center; align-items: center; height: 100vh; font-family: sans-serif; background-color: #f0f2f6; } .msg { padding: 2rem; background: white; border-radius: 1rem; box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center; } h2 { color: #ef4444; }</style></head><body><div class='msg'><h2>Hodnotenie nie je aktívne</h2></div></body></html>"
        components.html(error_html, height=600)
        return
    app_url = "https://consumervote.streamlit.app"
    evaluator_url = f"{app_url}/?mode=evaluator"
    encoded_url = urllib.parse.quote(evaluator_url)
    qr_page_html = f"""<!DOCTYPE html><html><head><style>body {{margin: 0; padding: 0; display: flex; justify-content: center; align-items: center; height: 100vh; font-family: sans-serif; background-color: #f0f2f6;}} .container {{text-align: center; background-color: white; padding: 2rem 3rem 3rem 3rem; border-radius: 1.5rem; box-shadow: 0 10px 30px rgba(0,0,0,0.1);}} h1 {{font-size: 2.2rem; color: #111827;}} p {{font-size: 1.2rem; color: #4b5563;}}</style></head><body><div class="container"><h1>{active_session['session_name']}</h1><p>Naskenujte kód a začnite hodnotiť</p><img src="https://api.qrserver.com/v1/create-qr-code/?size=400x400&ecc=H&data={encoded_url}" alt="QR Code"></div></body></html>"""
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
        try:
            from streamlit.runtime.scriptrunner import get_script_run_ctx
            st.session_state.session_id = get_script_run_ctx().session_id
        except Exception:
            st.session_state.session_id = str(random.randint(1, 1000000))
    
    main()