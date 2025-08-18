import streamlit as st
import pandas as pd
import json
from datetime import datetime
import uuid
import urllib.parse
import sqlite3
import os
import hashlib
import streamlit.components.v1 as components

# Nastavenie stránky
st.set_page_config(
    page_title="Hodnotenie vzoriek",
    page_icon="🧪",
    layout="wide"
)

# --- Databázové funkcie (bez zmien) ---
def init_database():
    """Inicializuje SQLite databázu"""
    db_path = "consumervote.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS evaluation_settings (id INTEGER PRIMARY KEY, session_name TEXT, session_active BOOLEAN, samples_count INTEGER, samples_names TEXT, created_at TIMESTAMP, updated_at TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS evaluations (id INTEGER PRIMARY KEY AUTOINCREMENT, session_name TEXT, evaluator_name TEXT NOT NULL, evaluation_data TEXT NOT NULL, comment TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS device_tracking (id INTEGER PRIMARY KEY AUTOINCREMENT, device_fingerprint TEXT NOT NULL, ip_address TEXT, user_agent TEXT, session_name TEXT, last_evaluation TIMESTAMP, evaluation_count INTEGER, UNIQUE(device_fingerprint, session_name))')
    cursor.execute('CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TIMESTAMP, admin_session_id TEXT, admin_ip TEXT, action_type TEXT, action_description TEXT, session_name TEXT, old_values TEXT, new_values TEXT, affected_records INTEGER, success BOOLEAN, error_message TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS admin_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, session_token TEXT UNIQUE NOT NULL, ip_address TEXT, user_agent TEXT, created_at TIMESTAMP, last_activity TIMESTAMP, expires_at TIMESTAMP)')
    cursor.execute('SELECT COUNT(*) FROM evaluation_settings')
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO evaluation_settings (session_name, session_active, samples_count, samples_names) VALUES ('Hodnotenie vzoriek', 0, 0, '[]')")
    conn.commit()
    conn.close()

def get_client_info():
    """Získa informácie o klientovi"""
    try:
        from streamlit.web.server.server import Server
        session_info = Server.get_current()._get_session_info_for_client(st.session_state.session_id)
        if session_info:
            headers = session_info.headers
            ip_address = headers.get('x-forwarded-for', '').split(',')[0].strip() or headers.get('x-real-ip', '') or "unknown"
            user_agent = headers.get('user-agent', 'unknown')
            return ip_address, user_agent
        return "unknown", "unknown"
    except Exception:
        return "unknown", "unknown"

def create_admin_session():
    """Vytvorí admin session token"""
    ip_address, user_agent = get_client_info()
    session_token = hashlib.md5(f"{ip_address}_{user_agent}_{datetime.now().timestamp()}".encode()).hexdigest()
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM admin_sessions WHERE expires_at < datetime('now')")
        cursor.execute("INSERT INTO admin_sessions (session_token, ip_address, user_agent, expires_at) VALUES (?, ?, ?, datetime('now', '+24 hours'))", (session_token, ip_address, user_agent))
        conn.commit()
        return session_token
    finally:
        conn.close()

def verify_admin_session(session_token):
    """Overí admin session token"""
    if not session_token: return False
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM admin_sessions WHERE session_token = ? AND expires_at > datetime('now')", (session_token,))
        if cursor.fetchone():
            cursor.execute("UPDATE admin_sessions SET last_activity = datetime('now') WHERE session_token = ?", (session_token,))
            conn.commit()
            return True
        return False
    finally:
        conn.close()

def destroy_admin_session(session_token):
    """Zruší admin session"""
    if not session_token: return
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM admin_sessions WHERE session_token = ?", (session_token,))
        conn.commit()
    finally:
        conn.close()

def get_admin_session_info():
    try:
        ip, _ = get_client_info()
        return f"admin_{hashlib.md5(f'{ip}_{datetime.now().date()}'.encode()).hexdigest()[:8]}", ip
    except:
        return "admin_unknown", "unknown"

def log_audit_action(action_type, action_description, **kwargs):
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        sid, ip = get_admin_session_info()
        cursor.execute('INSERT INTO audit_log (admin_session_id, admin_ip, action_type, action_description, session_name, old_values, new_values, affected_records, success, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                       (sid, ip, action_type, action_description, kwargs.get('session_name'), json.dumps(kwargs.get('new_values')), json.dumps(kwargs.get('new_values')), kwargs.get('affected_records', 1), kwargs.get('success', True), kwargs.get('error_message')))
        conn.commit()
    finally:
        conn.close()

def get_current_state():
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT session_name, session_active, samples_count, samples_names FROM evaluation_settings ORDER BY id DESC LIMIT 1')
        settings = cursor.fetchone()
        if settings:
            session_name, is_active, s_count, s_names_json = settings
            s_names = json.loads(s_names_json) if s_names_json else []
            cursor.execute('SELECT evaluator_name, evaluation_data, comment, created_at FROM evaluations WHERE session_name = ?', (session_name,))
            evaluations = [{'hodnotiteľ': r[0], 'čas': r[3], 'komentár': r[2] or '', 'id': str(uuid.uuid4())[:8], **json.loads(r[1])} for r in cursor.fetchall()]
            return {'session_name': session_name, 'session_active': bool(is_active), 'samples_count': s_count, 'samples_names': s_names, 'evaluations': evaluations}
    finally:
        conn.close()
    return {'session_name': 'Hodnotenie vzoriek', 'session_active': False, 'samples_count': 0, 'samples_names': [], 'evaluations': []}

def save_evaluation_settings(session_name, samples_count, samples_names, session_active):
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE evaluation_settings SET session_name = ?, samples_count = ?, samples_names = ?, session_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1',
                       (session_name, samples_count, json.dumps(samples_names), int(session_active)))
        conn.commit()
        log_audit_action("SETTINGS_UPDATE", f"Nastavenia aktualizované pre '{session_name}'", session_name=session_name, new_values={"samples": samples_count, "active": session_active})
        return True
    finally:
        conn.close()

def save_evaluation(session_name, evaluator_name, evaluation_data, comment=""):
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO evaluations (session_name, evaluator_name, evaluation_data, comment) VALUES (?, ?, ?, ?)',
                       (session_name, evaluator_name, json.dumps(evaluation_data), comment))
        conn.commit()
        return True
    finally:
        conn.close()

def get_device_fingerprint():
    ip, ua = get_client_info()
    return hashlib.md5(f"{ip}:{ua}".encode()).hexdigest(), ip, ua

def check_device_limit(session_name, device_fingerprint):
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT last_evaluation FROM device_tracking WHERE device_fingerprint = ? AND session_name = ?', (device_fingerprint, session_name))
        res = cursor.fetchone()
        if not res: return True, ""
        last_eval = datetime.strptime(res[0], '%Y-%m-%d %H:%M:%S')
        if (datetime.now() - last_eval).total_seconds() / 3600 >= 1: return True, ""
        rem_min = int(60 - (datetime.now() - last_eval).total_seconds() / 60)
        return False, f"Z tohto zariadenia už bolo hodnotené. Skúste znova o {rem_min} minút."
    finally:
        conn.close()

def update_device_tracking(session_name, device_fingerprint, ip_address, user_agent):
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE device_tracking SET last_evaluation = CURRENT_TIMESTAMP, evaluation_count = evaluation_count + 1 WHERE device_fingerprint = ? AND session_name = ?', (device_fingerprint, session_name))
        if cursor.rowcount == 0:
            cursor.execute('INSERT INTO device_tracking (device_fingerprint, ip_address, user_agent, session_name, last_evaluation, evaluation_count) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 1)',
                           (device_fingerprint, ip_address, user_agent, session_name))
        conn.commit()
    finally:
        conn.close()

def clear_evaluations_for_session(session_name):
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM evaluations WHERE session_name = ?', (session_name,))
        cursor.execute('DELETE FROM device_tracking WHERE session_name = ?', (session_name,))
        conn.commit()
        log_audit_action("DATA_DELETE", f"Dáta pre session '{session_name}' boli vymazané.", session_name=session_name)
        return True
    finally:
        conn.close()

# --- CSS a pomocné funkcie (bez zmien) ---
def get_professional_css():
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    .stApp { font-family: 'Inter', sans-serif; }
    .stButton > button { font-family: 'Inter', sans-serif !important; min-height: 48px !important; font-size: 16px !important; font-weight: 500 !important; border-radius: 8px !important; border: 1px solid #e1e5e9 !important; transition: all 0.2s ease-in-out !important; background: #ffffff !important; color: #374151 !important; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important; }
    .stButton > button:hover { transform: translateY(-1px) !important; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important; }
    .stButton > button[kind="primary"] { background: linear-gradient(135deg, #3b82f6, #1d4ed8) !important; color: white !important; border: none !important; }
    .professional-card { background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.5rem; margin: 1rem 0; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1); }
    .main-title { font-size: 1.875rem; font-weight: 700; text-align: center; margin-bottom: 1.5rem; }
    .section-title { font-size: 1.25rem; font-weight: 600; margin: 1.5rem 0 1rem 0; }
    .status-active { color: #10b981; font-weight: 600; }
    .status-inactive { color: #ef4444; font-weight: 600; }
    </style>
    """
ADMIN_PASSWORD_MD5 = hashlib.md5("consumervote24".encode()).hexdigest()

def verify_password(password):
    return hashlib.md5(password.encode()).hexdigest() == ADMIN_PASSWORD_MD5

# --- NOVÁ STRÁNKA PRE ZOBRAZENIE IBA QR KÓDU ---
def qr_display_page():
    """Zobrazí čistú stránku iba s QR kódom, ideálnu pre verejný monitor."""
    st.markdown("""
    <style>
        .stSidebar, .stHeader, footer { display: none !important; }
        .main .block-container { padding: 1rem !important; }
        body { background-color: #f0f2f6; }
        .qr-display-container {
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            height: 95vh;
            text-align: center;
        }
        .qr-card {
            background: white;
            padding: 2rem;
            border-radius: 1rem;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
    </style>
    """, unsafe_allow_html=True)

    current_state = get_current_state()
    st.markdown('<div class="qr-display-container">', unsafe_allow_html=True)

    if not current_state['session_active']:
        st.error("Hodnotenie nie je aktívne.")
    else:
        st.markdown(f'<h2>{current_state["session_name"]}</h2>', unsafe_allow_html=True)
        st.write("Naskenujte kód pre hodnotenie:")
        
        app_url = "https://consumervote.streamlit.app"
        evaluator_url = f"{app_url}/?mode=evaluator"
        encoded_url = urllib.parse.quote(evaluator_url)
        qr_services = [
            f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={encoded_url}",
            f"https://quickchart.io/qr?text={encoded_url}&size=400"
        ]
        
        qr_html = f"""
        <html><head><style>body {{ margin: 0; }}</style></head><body>
            <div id="qr-0"><img src="{qr_services[0]}" alt="QR Code" onerror="this.parentElement.style.display='none'; document.getElementById('qr-1').style.display='block';"></div>
            <div id="qr-1" style="display:none;"><img src="{qr_services[1]}" alt="QR Code" onerror="this.parentElement.style.display='none'; document.getElementById('qr-final').style.display='block';"></div>
            <div id="qr-final" style="display:none;"><p>Chyba pri načítaní QR kódu.</p><a href="{evaluator_url}" target="_blank">Otvoriť hodnotenie manuálne</a></div>
        </body></html>
        """
        with st.container():
            st.markdown('<div class="qr-card">', unsafe_allow_html=True)
            components.html(qr_html, height=410, width=410)
            st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# --- Admin a Evaluator rozhrania ---
def admin_login():
    """Login formulár pre admin"""
    st.markdown('<h1 class="main-title">Administrácia</h1>', unsafe_allow_html=True)
    with st.form("admin_login_form"):
        password = st.text_input("Heslo:", type="password")
        if st.form_submit_button("Prihlásiť sa", type="primary"):
            if verify_password(password):
                session_token = create_admin_session()
                if session_token:
                    st.session_state.admin_session_token = session_token
                    st.session_state.admin_authenticated = True
                    log_audit_action("AUTH_LOGIN", "Admin úspešne prihlásený")
                    st.rerun()
            else:
                log_audit_action("AUTH_LOGIN_FAILED", "Neúspešný pokus o prihlásenie")
                st.error("Nesprávne heslo!")

def admin_dashboard():
    """Admin dashboard rozhranie"""
    st.markdown(get_professional_css(), unsafe_allow_html=True)
    
    # --- FIX: Zjednodušená a spoľahlivá kontrola prihlásenia ---
    if not st.session_state.get('admin_authenticated', False):
        admin_login()
        return

    current_state = get_current_state()
    
    col1, col2 = st.columns([4, 1])
    with col1: st.markdown('<h1 class="main-title">Dashboard</h1>', unsafe_allow_html=True)
    with col2:
        if st.button("Odhlásiť"):
            destroy_admin_session(st.session_state.admin_session_token)
            st.session_state.admin_authenticated = False
            st.session_state.admin_session_token = None
            st.rerun()
    
    c1, c2, c3 = st.columns(3)
    status_class = "status-active" if current_state['session_active'] else "status-inactive"
    c1.markdown(f"<div class='professional-card'><h4>Status</h4><p class='{status_class}'>{'AKTÍVNA' if current_state['session_active'] else 'NEAKTÍVNA'}</p></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='professional-card'><h4>Vzorky</h4><p style='font-size: 1.5rem; font-weight: 600;'>{current_state['samples_count']}</p></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='professional-card'><h4>Hodnotenia</h4><p style='font-size: 1.5rem; font-weight: 600;'>{len(current_state['evaluations'])}</p></div>", unsafe_allow_html=True)
    
    st.divider()

    if current_state['session_active']:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown('<h2 class="section-title">QR kód pre priame hodnotenie</h2>', unsafe_allow_html=True)
            app_url = "https://consumervote.streamlit.app"
            evaluator_url = f"{app_url}/?mode=evaluator"
            encoded_url = urllib.parse.quote(evaluator_url)
            qr_html = f"""
            <html><head><style>body {{ margin: 0; }}</style></head><body>
                <div id="qr-0"><img src="https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded_url}" onerror="this.parentElement.style.display='none'; document.getElementById('qr-1').style.display='block';"></div>
                <div id="qr-1" style="display:none;"><img src="https://quickchart.io/qr?text={encoded_url}&size=300" onerror="this.parentElement.style.display='none';"></div>
            </body></html>"""
            with st.container():
                st.markdown('<div class="professional-card">', unsafe_allow_html=True)
                components.html(qr_html, height=310)
                st.markdown('</div>', unsafe_allow_html=True)

        with col2:
            st.markdown('<h2 class="section-title">Rýchle akcie</h2>', unsafe_allow_html=True)
            
            # --- NOVÝ ODKAZ PRE ZOBRAZENIE QR KÓDU NA CELEJ OBRAZOVKE ---
            qr_page_url = f"{app_url}/?mode=qr"
            st.link_button("Zobraziť QR na celej obrazovke", qr_page_url, use_container_width=True)
            st.write("") # Pridanie medzery
            
            if st.button("Reset hodnotení", use_container_width=True):
                if clear_evaluations_for_session(current_state['session_name']): st.success("Hodnotenia vymazané!")
                st.rerun()
            if st.button("Zastaviť hodnotenie", use_container_width=True):
                if save_evaluation_settings(current_state['session_name'], current_state['samples_count'], current_state['samples_names'], False): st.success("Hodnotenie zastavené!")
                st.rerun()
    else:
        st.warning("Hodnotenie nie je aktívne. Nastavte ho nižšie.")

    with st.expander("Nastavenia hodnotenia", expanded=not current_state['session_active']):
        admin_settings_section(current_state)
    with st.expander("Výsledky a export"):
        admin_results_section(current_state)

def admin_settings_section(current_state):
    with st.form("settings_form"):
        session_name = st.text_input("Názov hodnotenia:", value=current_state['session_name'])
        samples_count = st.number_input("Počet vzoriek:", min_value=2, max_value=20, value=max(2, current_state['samples_count']))
        sample_names = [st.text_input(f"Vzorka {i+1}:", value=current_state['samples_names'][i] if i < len(current_state['samples_names']) else f"Vzorka {i+1}", key=f"s_{i}") for i in range(samples_count)]
        c1, c2 = st.columns(2)
        if c1.form_submit_button("Uložiť a Spustiť", type="primary", use_container_width=True):
            if save_evaluation_settings(session_name, samples_count, sample_names, True): st.success("Hodnotenie spustené!")
            st.rerun()
        if c2.form_submit_button("Uložiť bez spustenia", use_container_width=True):
            if save_evaluation_settings(session_name, samples_count, sample_names, False): st.success("Nastavenia uložené!")
            st.rerun()

def admin_results_section(current_state):
    if not current_state['evaluations']:
        st.info("Zatiaľ žiadne hodnotenia.")
        return
    df = pd.DataFrame(current_state['evaluations'])
    st.download_button("Exportovať do CSV", df.to_csv(index=False).encode('utf-8'), f"hodnotenia.csv", "text/csv", use_container_width=True)
    st.dataframe(df)

def evaluator_interface():
    st.markdown(get_professional_css(), unsafe_allow_html=True)
    if 'mode' in st.query_params and st.query_params['mode'] == 'evaluator':
        st.markdown("<style>.stSidebar { display: none !important; }</style>", unsafe_allow_html=True)

    current_state = get_current_state()
    st.markdown(f'<h1 class="main-title">{current_state["session_name"]}</h1>', unsafe_allow_html=True)
    if not current_state['session_active']:
        st.error("Hodnotenie momentálne nie je aktívne.")
        return

    fingerprint, ip, ua = get_device_fingerprint()
    can_eval, msg = check_device_limit(fingerprint, current_state['session_name'])
    if not can_eval:
        st.warning(msg)
        return

    if st.session_state.get('evaluation_submitted', False):
        st.success("Ďakujeme za hodnotenie!")
        if st.button("Nové hodnotenie", type="primary"): st.session_state.evaluation_submitted = False; st.rerun()
        return

    with st.form("evaluation_form"):
        evaluator_name = st.text_input("Vaše meno alebo prezývka:")
        options = [''] + current_state['samples_names']
        first = st.selectbox("1. miesto (najlepšia):", options, format_func=lambda x: "Vyberte..." if x == '' else x)
        second_options = [o for o in options if o != first] if first else options
        second = st.selectbox("2. miesto:", second_options, format_func=lambda x: "Vyberte..." if x == '' else x)
        third_options = [o for o in second_options if o != second] if second else second_options
        third = st.selectbox("3. miesto:", third_options, format_func=lambda x: "Vyberte..." if x == '' else x)
        comment = st.text_area("Komentár (voliteľný):")
        
        if st.form_submit_button("Odoslať hodnotenie", type="primary", use_container_width=True):
            if not evaluator_name.strip() or not first:
                st.error("Meno a aspoň 1. miesto sú povinné.")
                return
            eval_data = {f"poradie_{s}": 999 for s in current_state['samples_names']}
            if first: eval_data[f"poradie_{first}"] = 1
            if second: eval_data[f"poradie_{second}"] = 2
            if third: eval_data[f"poradie_{third}"] = 3
            if save_evaluation(current_state['session_name'], evaluator_name, eval_data, comment):
                update_device_tracking(current_state['session_name'], fingerprint, ip, ua)
                st.session_state.evaluation_submitted = True
                st.rerun()

def main():
    """Hlavná funkcia aplikácie"""
    init_database()
    
    # --- FIX: Overenie session hneď na začiatku pre perzistenciu ---
    if 'admin_session_token' in st.session_state and not st.session_state.get('admin_authenticated', False):
        if verify_admin_session(st.session_state.admin_session_token):
            st.session_state.admin_authenticated = True
        else:
            # Token je neplatný/expirovaný, vyčistíme ho
            del st.session_state.admin_session_token
            st.session_state.admin_authenticated = False

    mode = st.query_params.get('mode', '').lower()

    # Smerovanie na základe URL parametra
    if mode == 'qr':
        qr_display_page()
        return
    
    if mode == 'evaluator':
        st.session_state.admin_mode = False
    
    # Zobrazenie sidebaru (okrem qr stránky)
    with st.sidebar:
        st.title("Menu")
        st.session_state.admin_mode = (st.radio("Režim:", ["Admin Dashboard", "Hodnotiteľ"],
                                                 index=0 if st.session_state.get('admin_mode', True) else 1) == "Admin Dashboard")

    # Zobrazenie hlavného obsahu
    if st.session_state.admin_mode:
        admin_dashboard()
    else:
        evaluator_interface()

if __name__ == "__main__":
    # Inicializácia session state premenných
    if 'session_id' not in st.session_state:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        st.session_state.session_id = get_script_run_ctx().session_id
    if 'admin_mode' not in st.session_state: st.session_state.admin_mode = True
    if 'admin_authenticated' not in st.session_state: st.session_state.admin_authenticated = False
    
    main()