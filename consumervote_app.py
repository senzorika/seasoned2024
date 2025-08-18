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

# Databázové funkcie
def init_database():
    """Inicializuje SQLite databázu"""
    db_path = "consumervote.db"
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Tabuľka pre nastavenia hodnotenia
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS evaluation_settings (
            id INTEGER PRIMARY KEY,
            session_name TEXT DEFAULT 'Hodnotenie vzoriek',
            session_active BOOLEAN DEFAULT 0,
            samples_count INTEGER DEFAULT 0,
            samples_names TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabuľka pre hodnotenia
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_name TEXT,
            evaluator_name TEXT NOT NULL,
            evaluation_data TEXT NOT NULL,
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabuľka pre tracking zariadení
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS device_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_fingerprint TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            session_name TEXT,
            last_evaluation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            evaluation_count INTEGER DEFAULT 1,
            UNIQUE(device_fingerprint, session_name)
        )
    ''')
    
    # Tabuľka pre audit log
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            admin_session_id TEXT,
            admin_ip TEXT,
            action_type TEXT NOT NULL,
            action_description TEXT NOT NULL,
            session_name TEXT,
            old_values TEXT,
            new_values TEXT,
            affected_records INTEGER DEFAULT 1,
            success BOOLEAN DEFAULT 1,
            error_message TEXT
        )
    ''')
    
    # Tabuľka pre admin sessions (pre persistence)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_token TEXT UNIQUE NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP
        )
    ''')
    
    # Vloženie základného záznamu ak neexistuje
    cursor.execute('SELECT COUNT(*) FROM evaluation_settings')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO evaluation_settings (session_name, session_active, samples_count, samples_names)
            VALUES ('Hodnotenie vzoriek', 0, 0, '[]')
        ''')
    
    # Pridanie stĺpcov ak neexistujú (pre existujúce databázy)
    try:
        cursor.execute('ALTER TABLE evaluation_settings ADD COLUMN session_name TEXT DEFAULT "Hodnotenie vzoriek"')
    except sqlite3.OperationalError:
        pass
    
    try:
        cursor.execute('ALTER TABLE evaluations ADD COLUMN session_name TEXT')
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    conn.close()

def get_client_info():
    """Získa informácie o klientovi"""
    try:
        # Nový spôsob prístupu k hlavičkám v Streamlit
        from streamlit.web.server.server import Server
        session_info = Server.get_current()._get_session_info_for_client(st.session_state.session_id)
        if session_info:
            headers = session_info.headers
            ip_address = (
                headers.get('x-forwarded-for', '').split(',')[0].strip() or
                headers.get('x-real-ip', '') or
                "unknown"
            )
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
        cursor.execute('''
            INSERT INTO admin_sessions (session_token, ip_address, user_agent, expires_at)
            VALUES (?, ?, ?, datetime('now', '+24 hours'))
        ''', (session_token, ip_address, user_agent))
        conn.commit()
        return session_token
    except Exception as e:
        print(f"Error creating admin session: {e}")
        return None
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
    except Exception as e:
        print(f"Error verifying admin session: {e}")
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
    except Exception as e:
        print(f"Error destroying admin session: {e}")
    finally:
        conn.close()

def get_admin_session_info():
    """Získa informácie o admin session pre audit"""
    try:
        ip_address, _ = get_client_info()
        session_id = f"admin_{hashlib.md5(f'{ip_address}_{datetime.now().date()}'.encode()).hexdigest()[:8]}"
        return session_id, ip_address
    except:
        return "admin_unknown", "unknown"

def log_audit_action(action_type, action_description, **kwargs):
    """Zaznamená audit akciu do databázy"""
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        admin_session_id, admin_ip = get_admin_session_info()
        cursor.execute('''
            INSERT INTO audit_log 
            (admin_session_id, admin_ip, action_type, action_description, session_name, old_values, new_values, affected_records, success, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (admin_session_id, admin_ip, action_type, action_description, kwargs.get('session_name'),
              json.dumps(kwargs.get('old_values')), json.dumps(kwargs.get('new_values')),
              kwargs.get('affected_records', 1), kwargs.get('success', True), kwargs.get('error_message')))
        conn.commit()
    except Exception as e:
        print(f"Audit log error: {e}")
    finally:
        conn.close()

def get_current_state():
    """Získa aktuálny stav z databázy"""
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT session_name, session_active, samples_count, samples_names FROM evaluation_settings ORDER BY id DESC LIMIT 1')
        settings = cursor.fetchone()
        if settings:
            session_name = settings[0] or 'Hodnotenie vzoriek'
            samples_names = json.loads(settings[3]) if settings[3] else []
            cursor.execute('SELECT evaluator_name, evaluation_data, comment, created_at FROM evaluations WHERE session_name = ?', (session_name,))
            evaluations_raw = cursor.fetchall()
            evaluations = []
            for eval_row in evaluations_raw:
                eval_data = json.loads(eval_row[1])
                evaluations.append({
                    'hodnotiteľ': eval_row[0], 'čas': eval_row[3], 'komentár': eval_row[2] or '',
                    'id': str(uuid.uuid4())[:8], **eval_data
                })
            return {'session_name': session_name, 'session_active': bool(settings[1]), 'samples_count': settings[2],
                    'samples_names': samples_names, 'evaluations': evaluations}
    except Exception as e:
        st.error(f"Chyba pri čítaní z databázy: {e}")
    finally:
        conn.close()
    return {'session_name': 'Hodnotenie vzoriek', 'session_active': False, 'samples_count': 0, 'samples_names': [], 'evaluations': []}

def save_evaluation_settings(session_name, samples_count, samples_names, session_active):
    """Uloží nastavenia hodnotenia"""
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE evaluation_settings 
            SET session_name = ?, samples_count = ?, samples_names = ?, session_active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        ''', (session_name, samples_count, json.dumps(samples_names), int(session_active)))
        conn.commit()
        log_audit_action("SETTINGS_UPDATE", f"Nastavenia aktualizované pre session '{session_name}'",
                         session_name=session_name, new_values={"samples_count": samples_count, "session_active": session_active})
        return True
    except Exception as e:
        st.error(f"Chyba pri ukladaní nastavení: {e}")
        return False
    finally:
        conn.close()

def save_evaluation(session_name, evaluator_name, evaluation_data, comment=""):
    """Uloží nové hodnotenie"""
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO evaluations (session_name, evaluator_name, evaluation_data, comment)
            VALUES (?, ?, ?, ?)
        ''', (session_name, evaluator_name, json.dumps(evaluation_data), comment))
        conn.commit()
        log_audit_action("EVALUATION_SUBMIT", f"Nové hodnotenie odoslané pre session '{session_name}'", session_name=session_name,
                         new_values={"evaluator_type": "anonymous", "has_comment": bool(comment)})
        return True
    except Exception as e:
        log_audit_action("EVALUATION_SUBMIT", f"Chyba pri ukladaní hodnotenia pre session '{session_name}'",
                         session_name=session_name, success=False, error_message=str(e))
        st.error(f"Chyba pri ukladaní hodnotenia: {e}")
        return False
    finally:
        conn.close()

def get_device_fingerprint():
    """Vytvorí fingerprint zariadenia na základe IP a user agent"""
    try:
        ip_address, user_agent = get_client_info()
        fingerprint_data = f"{ip_address}:{user_agent}"
        return hashlib.md5(fingerprint_data.encode()).hexdigest(), ip_address, user_agent
    except:
        import time
        fallback = f"fallback_{int(time.time())}"
        return hashlib.md5(fallback.encode()).hexdigest(), "unknown", "unknown"

def check_device_limit(session_name, device_fingerprint, ip_address, user_agent):
    """Skontroluje či zariadenie môže hodnotiť (limit 1x za hodinu)"""
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT last_evaluation, evaluation_count FROM device_tracking WHERE device_fingerprint = ? AND session_name = ?',
                       (device_fingerprint, session_name))
        result = cursor.fetchone()
        if not result: return True, "OK", 0
        last_evaluation_str, eval_count = result
        try:
            last_evaluation = datetime.strptime(last_evaluation_str, '%Y-%m-%d %H:%M:%S')
            time_diff_hours = (datetime.now() - last_evaluation).total_seconds() / 3600
            if time_diff_hours >= 1.0: return True, "OK", eval_count
            remaining_minutes = int((1.0 - time_diff_hours) * 60)
            return False, f"Musíte počkať ešte {remaining_minutes} minút", eval_count
        except:
            return True, "OK", eval_count
    except Exception as e:
        st.error(f"Chyba pri kontrole zariadenia: {e}")
        return True, "OK", 0
    finally:
        conn.close()

def clear_evaluations_for_session(session_name):
    """Vymaže hodnotenia pre aktuálnu session"""
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM evaluations WHERE session_name = ?', (session_name,))
        deleted_evals = cursor.rowcount
        cursor.execute('DELETE FROM device_tracking WHERE session_name = ?', (session_name,))
        deleted_devs = cursor.rowcount
        conn.commit()
        log_audit_action("DATA_DELETE", f"Vymazané hodnotenia a zariadenia pre session '{session_name}'",
                         session_name=session_name, affected_records=deleted_evals + deleted_devs)
        return True
    except Exception as e:
        st.error(f"Chyba pri mazaní hodnotení: {e}")
        return False
    finally:
        conn.close()

def update_device_tracking(session_name, device_fingerprint, ip_address, user_agent):
    """Aktualizuje tracking zariadenia po hodnotení"""
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE device_tracking SET last_evaluation = CURRENT_TIMESTAMP, evaluation_count = evaluation_count + 1,
            ip_address = ?, user_agent = ? WHERE device_fingerprint = ? AND session_name = ?
        ''', (ip_address, user_agent, device_fingerprint, session_name))
        if cursor.rowcount == 0:
            cursor.execute('''
                INSERT INTO device_tracking (device_fingerprint, ip_address, user_agent, session_name, evaluation_count)
                VALUES (?, ?, ?, ?, 1)
            ''', (device_fingerprint, ip_address, user_agent, session_name))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Chyba pri aktualizácii tracking: {e}")
        return False
    finally:
        conn.close()

def get_device_stats(session_name):
    """Získa štatistiky zariadení pre session"""
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT COUNT(*), SUM(evaluation_count), MAX(last_evaluation) FROM device_tracking WHERE session_name = ?', (session_name,))
        res = cursor.fetchone()
        return {'unique_devices': res[0] or 0, 'total_evaluations': res[1] or 0, 'last_activity': res[2]} if res else \
               {'unique_devices': 0, 'total_evaluations': 0, 'last_activity': None}
    except Exception as e:
        st.error(f"Chyba pri získavaní device stats: {e}")
        return {'unique_devices': 0, 'total_evaluations': 0, 'last_activity': None}
    finally:
        conn.close()

def get_professional_css():
    """Profesionálne CSS štýly optimalizované pre mobilné zariadenia"""
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    .stApp { font-family: 'Inter', sans-serif; }
    @media screen and (max-width: 768px) { .main .block-container { padding: 1rem !important; } }
    .stButton > button { font-family: 'Inter', sans-serif !important; min-height: 48px !important; font-size: 16px !important; font-weight: 500 !important; border-radius: 8px !important; border: 1px solid #e1e5e9 !important; transition: all 0.2s ease-in-out !important; background: #ffffff !important; color: #374151 !important; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important; }
    .stButton > button:hover { transform: translateY(-1px) !important; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important; border-color: #d1d5db !important; }
    .stButton > button[kind="primary"] { background: linear-gradient(135deg, #3b82f6, #1d4ed8) !important; color: white !important; border: none !important; }
    .stButton > button[kind="primary"]:hover { background: linear-gradient(135deg, #2563eb, #1e40af) !important; }
    .stSelectbox > div > div > div, .stTextInput > div > div > input, .stTextArea > div > div > textarea { min-height: 48px !important; font-size: 16px !important; border: 1px solid #d1d5db !important; border-radius: 8px !important; }
    .professional-card { background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.5rem; margin: 1rem 0; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1); }
    .main-title { font-size: 1.875rem; font-weight: 700; color: #111827; text-align: center; margin-bottom: 1.5rem; }
    .section-title { font-size: 1.25rem; font-weight: 600; color: #374151; margin: 1.5rem 0 1rem 0; }
    .status-active { color: #10b981; font-weight: 600; }
    .status-inactive { color: #ef4444; font-weight: 600; }
    .ranking-item { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1rem; margin: 0.5rem 0; }
    .ranking-item.first { background: linear-gradient(135deg, #fef3c7, #fbbf24); border-color: #f59e0b; color: #92400e; }
    </style>
    """

def export_evaluations_to_csv(session_name=None):
    """Exportuje hodnotenia do CSV"""
    conn = sqlite3.connect("consumervote.db")
    try:
        query = 'SELECT session_name as "Session", evaluator_name as "Hodnotiteľ", evaluation_data as "Hodnotenia", comment as "Komentár", created_at as "Čas" FROM evaluations'
        params = ()
        if session_name:
            query += ' WHERE session_name = ?'
            params = (session_name,)
        query += ' ORDER BY created_at DESC'
        return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.error(f"Chyba pri exporte: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

# Inicializácia session state
if 'admin_mode' not in st.session_state: st.session_state.admin_mode = True
if 'admin_authenticated' not in st.session_state: st.session_state.admin_authenticated = False
if 'admin_session_token' not in st.session_state: st.session_state.admin_session_token = None
if 'session_id' not in st.session_state:
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    st.session_state.session_id = get_script_run_ctx().session_id

ADMIN_PASSWORD_MD5 = hashlib.md5("consumervote24".encode()).hexdigest()

def verify_password(password, stored_hash):
    return hashlib.md5(password.encode()).hexdigest() == stored_hash

def simple_landing_page():
    """Minimalistická landing page"""
    st.markdown("""
    <style>
    .stSidebar { display: none; } .main > div { padding-top: 0rem; } body { background-color: #f8fafc; }
    .landing-container { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 2rem; text-align: center; }
    .landing-title { font-family: 'Inter', sans-serif; font-size: 2.5rem; font-weight: 700; color: #111827; margin-bottom: 3rem; }
    .qr-box { background: white; padding: 2rem; border-radius: 16px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1); border: 1px solid #e5e7eb; margin-bottom: 2rem; }
    .instructions { background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.2); border-radius: 12px; padding: 1.5rem; margin-top: 2rem; }
    </style>
    """, unsafe_allow_html=True)
    
    current_state = get_current_state()
    if not current_state['session_active']:
        st.markdown('<div class="landing-container"><h1 class="landing-title">Hodnotenie nie je aktívne</h1></div>', unsafe_allow_html=True)
        return

    st.markdown(f'<div class="landing-container"><h1 class="landing-title">{current_state["session_name"]}</h1>', unsafe_allow_html=True)
    
    with st.container():
        st.markdown('<div class="qr-box">', unsafe_allow_html=True)
        app_url = "https://consumervote.streamlit.app"
        evaluator_url = f"{app_url}/?mode=evaluator"
        encoded_url = urllib.parse.quote(evaluator_url)
        qr_services = [
            f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded_url}",
            f"https://quickchart.io/qr?text={encoded_url}&size=300"
        ]
        
        qr_html = f"""
        <html><head><style>body {{ margin: 0; }} .qr-image {{ width: 280px; height: 280px; }}</style></head>
        <body>
            <div id="qr-0" style="display:block;"><img class="qr-image" src="{qr_services[0]}" onerror="this.parentElement.style.display='none'; document.getElementById('qr-1').style.display='block';"></div>
            <div id="qr-1" style="display:none;"><img class="qr-image" src="{qr_services[1]}" onerror="this.parentElement.style.display='none'; document.getElementById('qr-final').style.display='block';"></div>
            <div id="qr-final" style="display:none; padding: 2rem; text-align: center;">
                <p>QR kód sa nepodarilo načítať.</p>
                <a href="{evaluator_url}" target="_parent">Prejsť na hodnotenie</a>
            </div>
        </body></html>
        """
        components.html(qr_html, height=280)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("""
        <div class="instructions">
            <h3>Ako hodnotiť:</h3>
            <p>1. Naskenujte QR kód fotoaparátom telefónu</p>
            <p>2. Otvorte odkaz v prehliadači a hodnoťte</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

def admin_login():
    """Login formulár pre admin"""
    if st.session_state.admin_session_token and verify_admin_session(st.session_state.admin_session_token):
        st.session_state.admin_authenticated = True
        st.rerun()
    
    st.markdown('<h1 class="main-title">Administrácia</h1>', unsafe_allow_html=True)
    with st.form("admin_login_form"):
        password = st.text_input("Heslo:", type="password")
        if st.form_submit_button("Prihlásiť sa", type="primary"):
            if verify_password(password, ADMIN_PASSWORD_MD5):
                session_token = create_admin_session()
                if session_token:
                    st.session_state.admin_session_token = session_token
                    st.session_state.admin_authenticated = True
                    log_audit_action("AUTH_LOGIN", "Admin úspešne prihlásený")
                    st.rerun()
                else: st.error("Chyba pri vytváraní session!")
            else:
                log_audit_action("AUTH_LOGIN_FAILED", "Neúspešný pokus o prihlásenie")
                st.error("Nesprávne heslo!")

def admin_dashboard():
    """Admin dashboard rozhranie"""
    st.markdown(get_professional_css(), unsafe_allow_html=True)
    if not st.session_state.get('admin_authenticated', False) or not verify_admin_session(st.session_state.admin_session_token):
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
    
    # Metriky
    device_stats = get_device_stats(current_state['session_name'])
    c1, c2, c3, c4 = st.columns(4)
    status_class = "status-active" if current_state['session_active'] else "status-inactive"
    c1.markdown(f"<div class='professional-card'><h4>Status</h4><p class='{status_class}'>{'AKTÍVNA' if current_state['session_active'] else 'NEAKTÍVNA'}</p></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='professional-card'><h4>Vzorky</h4><p style='font-size: 1.5rem; font-weight: 600;'>{current_state['samples_count']}</p></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='professional-card'><h4>Hodnotenia</h4><p style='font-size: 1.5rem; font-weight: 600;'>{len(current_state['evaluations'])}</p></div>", unsafe_allow_html=True)
    c4.markdown(f"<div class='professional-card'><h4>Zariadenia</h4><p style='font-size: 1.5rem; font-weight: 600;'>{device_stats['unique_devices']}</p></div>", unsafe_allow_html=True)
    
    st.divider()

    if current_state['session_active']:
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown('<h2 class="section-title">QR kód pre hodnotiteľov</h2>', unsafe_allow_html=True)
            
            # --- START FIX: Robustné generovanie QR kódu pomocou components.html ---
            app_url = "https://consumervote.streamlit.app"
            landing_url = f"{app_url}/?mode=landing"
            encoded_url = urllib.parse.quote(landing_url)
            qr_services = [
                f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded_url}",
                f"https://quickchart.io/qr?text={encoded_url}&size=300"
            ]
            
            # Vytvorenie sebestačného HTML pre komponent
            qr_html = f"""
            <html>
            <head>
                <style>
                    body {{ margin: 0; display: flex; justify-content: center; align-items: center; }}
                    .qr-image {{ max-width: 100%; height: auto; }}
                </style>
            </head>
            <body>
                <div id="qr-container-0" style="display: block;">
                    <img class="qr-image" src="{qr_services[0]}" alt="QR Code" onerror="this.parentElement.style.display='none'; document.getElementById('qr-container-1').style.display='block';">
                </div>
                <div id="qr-container-1" style="display: none;">
                    <img class="qr-image" src="{qr_services[1]}" alt="QR Code" onerror="this.parentElement.style.display='none'; document.getElementById('qr-fallback-final').style.display='block';">
                </div>
                <div id="qr-fallback-final" style="display: none; padding: 2rem; text-align:center; font-family: sans-serif;">
                    <p style="color: #ef4444;"><b>Chyba pri načítaní QR kódu.</b></p>
                    <p>Použite odkaz:</p>
                    <a href="{landing_url}" target="_blank">{landing_url}</a>
                </div>
            </body>
            </html>
            """
            with st.container():
                st.markdown('<div class="professional-card">', unsafe_allow_html=True)
                components.html(qr_html, height=310) # Renderovanie komponentu
                st.markdown('</div>', unsafe_allow_html=True)
            # --- END FIX ---

        with col2:
            st.markdown('<h2 class="section-title">Rýchle akcie</h2>', unsafe_allow_html=True)
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
    """Sekcia nastavení v dashboarde"""
    with st.form("settings_form"):
        session_name = st.text_input("Názov hodnotenia:", value=current_state['session_name'])
        samples_count = st.number_input("Počet vzoriek:", min_value=2, max_value=20, value=max(2, current_state['samples_count']))
        
        sample_names = []
        for i in range(samples_count):
            default_name = current_state['samples_names'][i] if i < len(current_state['samples_names']) else f"Vzorka {i+1}"
            sample_names.append(st.text_input(f"Vzorka {i+1}:", value=default_name, key=f"sample_{i}"))
        
        c1, c2 = st.columns(2)
        if c1.form_submit_button("Uložiť a Spustiť", type="primary", use_container_width=True):
            if save_evaluation_settings(session_name, samples_count, sample_names, True): st.success("Hodnotenie spustené!")
            st.rerun()
        if c2.form_submit_button("Uložiť bez spustenia", use_container_width=True):
            if save_evaluation_settings(session_name, samples_count, sample_names, False): st.success("Nastavenia uložené!")
            st.rerun()

def admin_results_section(current_state):
    """Sekcia výsledkov v dashboarde"""
    if not current_state['evaluations']:
        st.info("Zatiaľ žiadne hodnotenia.")
        return
        
    df = export_evaluations_to_csv(current_state['session_name'])
    st.download_button("Exportovať do CSV", df.to_csv(index=False).encode('utf-8'),
                        f"hodnotenia_{current_state['session_name']}.csv", "text/csv", use_container_width=True)
    st.dataframe(df)

def evaluator_interface():
    """Rozhranie pre hodnotiteľov"""
    st.markdown(get_professional_css(), unsafe_allow_html=True)
    if 'mode' in st.query_params and st.query_params['mode'] == 'evaluator':
        st.markdown("<style>.stSidebar { display: none !important; }</style>", unsafe_allow_html=True)

    current_state = get_current_state()
    st.markdown(f'<h1 class="main-title">{current_state["session_name"]}</h1>', unsafe_allow_html=True)
    if not current_state['session_active']:
        st.error("Hodnotenie momentálne nie je aktívne.")
        return

    fingerprint, ip, ua = get_device_fingerprint()
    can_eval, msg, _ = check_device_limit(current_state['session_name'], fingerprint, ip, ua)
    if not can_eval:
        st.warning(msg)
        return

    if st.session_state.get('evaluation_submitted', False):
        st.success("Ďakujeme za hodnotenie!")
        st.balloons()
        if st.button("Nové hodnotenie", type="primary"):
            st.session_state.evaluation_submitted = False
            st.rerun()
        return

    with st.form("evaluation_form"):
        st.info("Vyberte TOP 3 vzorky v poradí od najlepšej.")
        evaluator_name = st.text_input("Vaše meno alebo prezývka:", key="eval_name")
        
        options = [''] + current_state['samples_names']
        format_func = lambda x: "Vyberte..." if x == '' else x
        
        first = st.selectbox("1. miesto (najlepšia):", options, format_func=format_func, key="first")
        second = st.selectbox("2. miesto:", [o for o in options if o != first], format_func=format_func, key="second")
        third = st.selectbox("3. miesto:", [o for o in options if o not in [first, second]], format_func=format_func, key="third")
        
        comment = st.text_area("Komentár (voliteľný):", key="comment")
        
        if st.form_submit_button("Odoslať hodnotenie", type="primary", use_container_width=True):
            if not evaluator_name.strip(): st.error("Zadajte prosím meno."); return
            if not first: st.error("Vyberte aspoň 1. miesto."); return

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
    mode = st.query_params.get('mode', '').lower()

    if mode == 'landing':
        simple_landing_page()
        return
    
    if mode == 'evaluator' and st.session_state.get('admin_mode', True):
        st.session_state.admin_mode = False
        st.rerun()

    with st.sidebar:
        st.title("Menu")
        if 'admin_mode' in st.session_state:
            st.session_state.admin_mode = (st.radio("Režim:", ["Admin Dashboard", "Hodnotiteľ"],
                                                     index=0 if st.session_state.admin_mode else 1) == "Admin Dashboard")

    if st.session_state.get('admin_mode', True):
        admin_dashboard()
    else:
        evaluator_interface()

if __name__ == "__main__":
    main()