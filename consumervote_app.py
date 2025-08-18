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
import random

# Nastavenie stránky
st.set_page_config(
    page_title="Hodnotenie vzoriek",
    page_icon="🧪",
    layout="wide"
)

# --- Databázové funkcie (bez zmien) ---
def init_database():
    db_path = "consumervote.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS evaluation_settings (id INTEGER PRIMARY KEY, session_name TEXT, session_active BOOLEAN, samples_count INTEGER, samples_names TEXT, created_at TIMESTAMP, updated_at TIMESTAMP, session_winner TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS evaluations (id INTEGER PRIMARY KEY AUTOINCREMENT, session_name TEXT, evaluator_name TEXT NOT NULL, evaluation_data TEXT NOT NULL, comment TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS device_tracking (id INTEGER PRIMARY KEY AUTOINCREMENT, device_fingerprint TEXT NOT NULL, ip_address TEXT, user_agent TEXT, session_name TEXT, last_evaluation TIMESTAMP, evaluation_count INTEGER, UNIQUE(device_fingerprint, session_name))')
    cursor.execute('CREATE TABLE IF NOT EXISTS admin_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, session_token TEXT UNIQUE NOT NULL, ip_address TEXT, user_agent TEXT, created_at TIMESTAMP, last_activity TIMESTAMP, expires_at TIMESTAMP)')
    cursor.execute('SELECT COUNT(*) FROM evaluation_settings')
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO evaluation_settings (id, session_name, session_active, samples_count, samples_names) VALUES (1, 'Hodnotenie vzoriek', 0, 0, '[]')")
    try:
        cursor.execute('ALTER TABLE evaluation_settings ADD COLUMN session_winner TEXT')
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

def get_client_info():
    try:
        from streamlit.web.server.server import Server
        session_info = Server.get_current()._get_session_info_for_client(st.session_state.session_id)
        if session_info:
            headers = session_info.headers
            ip = headers.get('x-forwarded-for', '').split(',')[0].strip() or headers.get('x-real-ip', '') or "unknown"
            ua = headers.get('user-agent', 'unknown')
            return ip, ua
        return "unknown", "unknown"
    except Exception:
        return "unknown", "unknown"

def create_admin_session():
    ip, ua = get_client_info()
    token = hashlib.md5(f"{ip}_{ua}_{datetime.now().timestamp()}".encode()).hexdigest()
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM admin_sessions WHERE expires_at < datetime('now')")
        cursor.execute("INSERT INTO admin_sessions (session_token, ip_address, user_agent, expires_at) VALUES (?, ?, ?, datetime('now', '+24 hours'))", (token, ip, ua))
        conn.commit()
        return token
    finally:
        conn.close()

def verify_admin_session(token):
    if not token: return False
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM admin_sessions WHERE session_token = ? AND expires_at > datetime('now')", (token,))
        if cursor.fetchone():
            cursor.execute("UPDATE admin_sessions SET last_activity = datetime('now') WHERE session_token = ?", (token,))
            conn.commit()
            return True
        return False
    finally:
        conn.close()

def destroy_admin_session(token):
    if not token: return
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM admin_sessions WHERE session_token = ?", (token,))
        conn.commit()
    finally:
        conn.close()

def get_current_state():
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT session_name, session_active, samples_count, samples_names, session_winner FROM evaluation_settings ORDER BY id DESC LIMIT 1')
        settings = cursor.fetchone()
        if settings:
            session_name, is_active, s_count, s_names_json, winner = settings
            s_names = json.loads(s_names_json) if s_names_json else []
            cursor.execute('SELECT evaluator_name, evaluation_data FROM evaluations WHERE session_name = ?', (session_name,))
            evaluations = [{'hodnotiteľ': r[0], **json.loads(r[1])} for r in cursor.fetchall()]
            return {'session_name': session_name, 'session_active': bool(is_active), 'samples_count': s_count, 'samples_names': s_names, 'evaluations': evaluations, 'winner': winner}
    finally:
        conn.close()
    return {'session_name': 'Nové hodnotenie', 'session_active': False, 'samples_count': 0, 'samples_names': [], 'evaluations': [], 'winner': None}

def save_evaluation_settings(session_name, samples_count, samples_names, session_active):
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE evaluation_settings SET session_name = ?, samples_count = ?, samples_names = ?, session_active = ?, updated_at = CURRENT_TIMESTAMP, session_winner = NULL WHERE id = 1',
                       (session_name, samples_count, json.dumps(samples_names), int(session_active)))
        conn.commit()
        return True
    finally:
        conn.close()

def save_evaluation(session_name, evaluator_name, evaluation_data, comment=""):
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO evaluations (session_name, evaluator_name, evaluation_data, comment) VALUES (?, ?, ?, ?)', (session_name, evaluator_name, json.dumps(evaluation_data), comment))
        conn.commit()
        return True
    finally:
        conn.close()

def get_device_fingerprint():
    ip, ua = get_client_info()
    return hashlib.md5(f"{ip}:{ua}".encode()).hexdigest(), ip, ua

def check_device_limit(fingerprint, session_name):
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT last_evaluation FROM device_tracking WHERE device_fingerprint = ? AND session_name = ?', (fingerprint, session_name))
        res = cursor.fetchone()
        if not res: return True, ""
        last_eval = datetime.strptime(res[0], '%Y-%m-%d %H:%M:%S')
        if (datetime.now() - last_eval).total_seconds() / 3600 >= 1: return True, ""
        rem_min = int(60 - (datetime.now() - last_eval).total_seconds() / 60)
        return False, f"Z tohto zariadenia už bolo hodnotené. Skúste znova o {rem_min} minút."
    finally:
        conn.close()

def update_device_tracking(session_name, fingerprint, ip, ua):
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE device_tracking SET last_evaluation = CURRENT_TIMESTAMP, evaluation_count = evaluation_count + 1 WHERE device_fingerprint = ? AND session_name = ?', (fingerprint, session_name))
        if cursor.rowcount == 0:
            cursor.execute('INSERT INTO device_tracking (device_fingerprint, ip_address, user_agent, session_name, last_evaluation, evaluation_count) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 1)', (fingerprint, ip, ua, session_name))
        conn.commit()
    finally:
        conn.close()
        
def clear_evaluations_for_session(session_name):
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM evaluations WHERE session_name = ?', (session_name,))
        cursor.execute('DELETE FROM device_tracking WHERE session_name = ?', (session_name,))
        cursor.execute('UPDATE evaluation_settings SET session_winner = NULL WHERE session_name = ?', (session_name,))
        conn.commit()
        return True
    finally:
        conn.close()

def save_winner(session_name, winner_name):
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('UPDATE evaluation_settings SET session_winner = ? WHERE session_name = ?', (winner_name, session_name))
        conn.commit()
    finally:
        conn.close()

def get_professional_css():
    return """<style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap'); .stApp { font-family: 'Inter', sans-serif; } .stButton > button { font-family: 'Inter', sans-serif !important; min-height: 48px !important; font-size: 16px !important; font-weight: 500 !important; border-radius: 8px !important; border: 1px solid #e1e5e9 !important; transition: all 0.2s ease-in-out !important; background: #ffffff !important; color: #374151 !important; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important; } .stButton > button:hover { transform: translateY(-1px) !important; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important; } .stButton > button[kind="primary"] { background: linear-gradient(135deg, #3b82f6, #1d4ed8) !important; color: white !important; border: none !important; } .professional-card { background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.5rem; margin: 1rem 0; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1); } .main-title { font-size: 1.875rem; font-weight: 700; text-align: center; margin-bottom: 1.5rem; } .section-title { font-size: 1.25rem; font-weight: 600; margin: 1.5rem 0 1rem 0; } .status-active { color: #10b981; font-weight: 600; } .status-inactive { color: #ef4444; font-weight: 600; }</style>"""
ADMIN_PASSWORD_MD5 = hashlib.md5("consumervote24".encode()).hexdigest()
def verify_password(password): return hashlib.md5(password.encode()).hexdigest() == ADMIN_PASSWORD_MD5

# --- FIX: Centrálna funkcia pre overenie prihlásenia ---
def authenticate_admin():
    """
    Overí session token pri každom behu skriptu.
    Toto je jediný zdroj pravdy o prihlásení.
    """
    token = st.session_state.get('admin_session_token')
    if token and verify_admin_session(token):
        st.session_state.admin_authenticated = True
    else:
        st.session_state.admin_authenticated = False
        if 'admin_session_token' in st.session_state:
            del st.session_state['admin_session_token']

# --- Rôzne stránky aplikácie ---
def qr_display_page():
    # Táto funkcia je už v poriadku
    st.markdown("<style>.stSidebar, .stHeader, footer { display: none !important; } .main .block-container { max-width: 100% !important; padding: 0 !important; margin: 0 !important; }</style>", unsafe_allow_html=True)
    current_state = get_current_state()
    if not current_state['session_active']:
        error_html = "<html><head><style>body { margin: 0; display: flex; justify-content: center; align-items: center; height: 100vh; font-family: sans-serif; background-color: #f0f2f6; } .msg { padding: 2rem; background: white; border-radius: 1rem; box-shadow: 0 4px 12px rgba(0,0,0,0.1); text-align: center; } h2 { color: #ef4444; }</style></head><body><div class='msg'><h2>Hodnotenie nie je aktívne</h2><p>Prosím, kontaktujte administrátora.</p></div></body></html>"
        components.html(error_html, height=600)
        return
    app_url = "https://consumervote.streamlit.app"
    evaluator_url = f"{app_url}/?mode=evaluator"
    encoded_url = urllib.parse.quote(evaluator_url)
    qr_page_html = f"""<!DOCTYPE html><html><head><style>body {{margin: 0; padding: 0; display: flex; justify-content: center; align-items: center; height: 100vh; font-family: sans-serif; background-color: #f0f2f6;}} .container {{text-align: center; background-color: white; padding: 2rem 3rem 3rem 3rem; border-radius: 1.5rem; box-shadow: 0 10px 30px rgba(0,0,0,0.1);}} h1 {{font-size: 2.2rem; color: #111827;}} p {{font-size: 1.2rem; color: #4b5563;}}</style></head><body><div class="container"><h1>{current_state['session_name']}</h1><p>Naskenujte kód a začnite hodnotiť</p><img src="https://api.qrserver.com/v1/create-qr-code/?size=400x400&ecc=H&data={encoded_url}" alt="QR Code"></div></body></html>"""
    components.html(qr_page_html, height=800, scrolling=True)

def results_page():
    st.markdown(get_professional_css(), unsafe_allow_html=True)
    # --- FIX: Použitie centrálneho overenia ---
    if not st.session_state.get('admin_authenticated', False):
        st.error("Prístup zamietnutý. Prosím, prihláste sa ako administrátor.")
        st.warning("Pre návrat na hlavnú stránku obnovte (refresh) stránku alebo použite menu vľavo.")
        return

    current_state = get_current_state()
    st.markdown(f'<h1 class="main-title">Výsledky: {current_state["session_name"]}</h1>', unsafe_allow_html=True)

    if not current_state['evaluations']:
        st.warning("Pre toto hodnotenie neboli nájdené žiadne záznamy.")
        return

    st.markdown('<h2 class="section-title">🏆 Konečné poradie podľa bodov</h2>', unsafe_allow_html=True)
    scores = {name: 0 for name in current_state['samples_names']}
    for evaluation in current_state['evaluations']:
        for sample_name in current_state['samples_names']:
            rank = evaluation.get(f'poradie_{sample_name}')
            if rank == 1: scores[sample_name] += 3
            elif rank == 2: scores[sample_name] += 2
            elif rank == 3: scores[sample_name] += 1
    
    sorted_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    results_df = pd.DataFrame(sorted_scores, columns=['Vzorka', 'Počet bodov'])
    results_df.index = results_df.index + 1
    st.dataframe(results_df, use_container_width=True)

    st.divider()
    st.markdown('<h2 class="section-title">🎉 Losovanie výhercu z hodnotiteľov</h2>', unsafe_allow_html=True)
    
    if current_state.get('winner'):
        st.success(f"**Vylosovaný výherca je: {current_state['winner']}**")
        st.info("Toto losovanie je jednorazové a výherca bol natrvalo uložený.")
    else:
        if st.button("🎲 Vylosovať výhercu", type="primary", use_container_width=True):
            evaluators = list(set(e['hodnotiteľ'] for e in current_state['evaluations']))
            if evaluators:
                winner = random.choice(evaluators)
                save_winner(current_state['session_name'], winner)
                st.session_state.drawn_winner = winner
                st.balloons()
                st.rerun()
            else:
                st.error("Nepodarilo sa nájsť žiadnych hodnotiteľov na losovanie.")
    
    if 'drawn_winner' in st.session_state:
        st.success(f"**Vylosovaný výherca je: {st.session_state.drawn_winner}**")
        del st.session_state.drawn_winner

def admin_login():
    st.markdown('<h1 class="main-title">Administrácia</h1>', unsafe_allow_html=True)
    with st.form("admin_login_form"):
        password = st.text_input("Heslo:", type="password")
        if st.form_submit_button("Prihlásiť sa", type="primary"):
            if verify_password(password):
                token = create_admin_session()
                if token:
                    st.session_state.admin_session_token = token
                    st.session_state.admin_authenticated = True
                    st.rerun()
            else:
                st.error("Nesprávne heslo!")

def admin_dashboard():
    st.markdown(get_professional_css(), unsafe_allow_html=True)
    # --- FIX: Použitie centrálneho overenia ---
    if not st.session_state.get('admin_authenticated', False):
        admin_login()
        return

    current_state = get_current_state()
    
    col1, col2 = st.columns([4, 1])
    with col1: st.markdown('<h1 class="main-title">Dashboard</h1>', unsafe_allow_html=True)
    with col2:
        if st.button("Odhlásiť"):
            destroy_admin_session(st.session_state.get('admin_session_token'))
            st.session_state.admin_authenticated = False
            if 'admin_session_token' in st.session_state:
                del st.session_state['admin_session_token']
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
            st.markdown('<h2 class="section-title">QR kód pre hodnotenie</h2>', unsafe_allow_html=True)
            app_url = "https://consumervote.streamlit.app"
            evaluator_url = f"{app_url}/?mode=evaluator"
            encoded_url = urllib.parse.quote(evaluator_url)
            qr_html = f'<html><head><style>body {{ margin: 0; }}</style></head><body><img src="https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded_url}"></body></html>'
            with st.container():
                st.markdown('<div class="professional-card">', unsafe_allow_html=True)
                components.html(qr_html, height=310)
                st.markdown('</div>', unsafe_allow_html=True)

        with col2:
            st.markdown('<h2 class="section-title">Rýchle akcie</h2>', unsafe_allow_html=True)
            st.link_button("Zobraziť QR na celej obrazovke", f"{app_url}/?mode=qr", use_container_width=True, type="secondary")
            st.write("")
            if st.button("Reset hodnotení", use_container_width=True):
                if clear_evaluations_for_session(current_state['session_name']): st.success("Hodnotenia vymazané!")
                st.rerun()
            if st.button("Zastaviť hodnotenie", use_container_width=True):
                if save_evaluation_settings(current_state['session_name'], current_state['samples_count'], current_state['samples_names'], False): st.success("Hodnotenie zastavené!")
                st.rerun()
    else:
        st.warning("Hodnotenie je neaktívne.")
        if current_state['evaluations']:
             st.link_button("🏆 Zobraziť konečné výsledky a losovanie", "/?mode=results", use_container_width=True)

    with st.expander("Nastavenia hodnotenia", expanded=not current_state['session_active']):
        admin_settings_section(current_state)

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
        second = st.selectbox("2. miesto:", [o for o in options if o != first], format_func=lambda x: "Vyberte..." if x == '' else x)
        third = st.selectbox("3. miesto:", [o for o in options if o not in [first, second]], format_func=lambda x: "Vyberte..." if x == '' else x)
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
    
    # Centrálne overenie session pri každom behu
    authenticate_admin()

    mode = st.query_params.get('mode', '').lower()

    # Smerovanie na špeciálne stránky
    if mode == 'qr':
        qr_display_page()
        return
    if mode == 'results':
        results_page()
        return
    
    # Nastavenie režimu admin/hodnotiteľ
    if mode == 'evaluator':
        st.session_state.admin_mode = False
    
    with st.sidebar:
        st.title("Menu")
        st.session_state.admin_mode = (st.radio("Režim:", ["Admin Dashboard", "Hodnotiteľ"],
                                                 index=0 if st.session_state.get('admin_mode', True) else 1) == "Admin Dashboard")

    if st.session_state.admin_mode:
        admin_dashboard()
    else:
        evaluator_interface()

if __name__ == "__main__":
    if 'session_id' not in st.session_state:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        st.session_state.session_id = get_script_run_ctx().session_id
    if 'admin_mode' not in st.session_state: st.session_state.admin_mode = True
    
    main()