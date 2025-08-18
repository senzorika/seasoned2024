import streamlit as st
import pandas as pd
import json
from datetime import datetime
import uuid
import urllib.parse
import sqlite3
import os
import hashlib

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
        headers = st.context.headers if hasattr(st.context, 'headers') else {}
        ip_address = (
            headers.get('x-forwarded-for', '').split(',')[0].strip() or
            headers.get('x-real-ip', '') or
            headers.get('remote-addr', 'unknown')
        )
        user_agent = headers.get('user-agent', 'unknown')
        return ip_address, user_agent
    except:
        return "unknown", "unknown"

def create_admin_session():
    """Vytvorí admin session token"""
    ip_address, user_agent = get_client_info()
    session_token = hashlib.md5(f"{ip_address}_{user_agent}_{datetime.now().timestamp()}".encode()).hexdigest()
    
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    
    try:
        # Vymaž staré sessions (starší ako 24 hodín)
        cursor.execute("DELETE FROM admin_sessions WHERE expires_at < datetime('now')")
        
        # Vytvor novú session (platná 24 hodín)
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
    if not session_token:
        return False
        
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT id FROM admin_sessions 
            WHERE session_token = ? AND expires_at > datetime('now')
        ''', (session_token,))
        
        result = cursor.fetchone()
        
        if result:
            # Aktualizuj last_activity
            cursor.execute('''
                UPDATE admin_sessions 
                SET last_activity = datetime('now') 
                WHERE session_token = ?
            ''', (session_token,))
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
    if not session_token:
        return
        
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
        ip_address, user_agent = get_client_info()
        session_id = f"admin_{hashlib.md5(f'{ip_address}_{datetime.now().date()}'.encode()).hexdigest()[:8]}"
        return session_id, ip_address
    except:
        return "admin_unknown", "unknown"

def log_audit_action(action_type, action_description, session_name=None, old_values=None, new_values=None, affected_records=1, success=True, error_message=None):
    """Zaznamená audit akciu do databázy"""
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    
    try:
        admin_session_id, admin_ip = get_admin_session_info()
        
        cursor.execute('''
            INSERT INTO audit_log 
            (admin_session_id, admin_ip, action_type, action_description, session_name, 
             old_values, new_values, affected_records, success, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            admin_session_id, admin_ip, action_type, action_description, session_name,
            json.dumps(old_values) if old_values else None,
            json.dumps(new_values) if new_values else None,
            affected_records, success, error_message
        ))
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Audit log error: {e}")
        return False
    finally:
        conn.close()

def get_current_state():
    """Získa aktuálny stav z databázy"""
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    
    try:
        # Získanie nastavení
        cursor.execute('SELECT session_name, session_active, samples_count, samples_names FROM evaluation_settings ORDER BY id DESC LIMIT 1')
        settings = cursor.fetchone()
        
        if settings:
            session_name = settings[0] or 'Hodnotenie vzoriek'
            samples_names = json.loads(settings[3]) if settings[3] else []
            
            # Získanie hodnotení pre aktuálnu session
            cursor.execute('SELECT evaluator_name, evaluation_data, comment, created_at FROM evaluations WHERE session_name = ? OR session_name IS NULL', (session_name,))
            evaluations_raw = cursor.fetchall()
            
            evaluations = []
            for eval_row in evaluations_raw:
                evaluation = {
                    'hodnotiteľ': eval_row[0],
                    'čas': eval_row[3],
                    'komentár': eval_row[2] or '',
                    'id': str(uuid.uuid4())[:8]
                }
                
                # Pridanie hodnotení vzoriek
                eval_data = json.loads(eval_row[1])
                evaluation.update(eval_data)
                evaluations.append(evaluation)
            
            return {
                'session_name': session_name,
                'session_active': bool(settings[1]),
                'samples_count': settings[2],
                'samples_names': samples_names,
                'evaluations': evaluations
            }
    except Exception as e:
        st.error(f"Chyba pri čítaní z databázy: {e}")
    finally:
        conn.close()
    
    # Predvolený stav
    return {
        'session_name': 'Hodnotenie vzoriek',
        'session_active': False,
        'samples_count': 0,
        'samples_names': [],
        'evaluations': []
    }

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
        
        # Audit log
        log_audit_action(
            action_type="SETTINGS_UPDATE",
            action_description=f"Nastavenia aktualizované pre session '{session_name}'",
            session_name=session_name,
            new_values={"samples_count": samples_count, "session_active": session_active},
            success=True
        )
        
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
        
        # Audit log pre nové hodnotenie (nelogujeme citlivé údaje hodnotiteľa)
        log_audit_action(
            action_type="EVALUATION_SUBMIT",
            action_description=f"Nové hodnotenie odoslané pre session '{session_name}'",
            session_name=session_name,
            new_values={"evaluator_type": "anonymous", "has_comment": bool(comment)},
            success=True
        )
        
        return True
    except Exception as e:
        log_audit_action(
            action_type="EVALUATION_SUBMIT",
            action_description=f"Chyba pri ukladaní hodnotenia pre session '{session_name}'",
            session_name=session_name,
            success=False,
            error_message=str(e)
        )
        st.error(f"Chyba pri ukladaní hodnotenia: {e}")
        return False
    finally:
        conn.close()

def get_device_fingerprint():
    """Vytvorí fingerprint zariadenia na základe IP a user agent"""
    try:
        ip_address, user_agent = get_client_info()
        
        # Vytvorenie fingerprint
        fingerprint_data = f"{ip_address}:{user_agent}"
        fingerprint = hashlib.md5(fingerprint_data.encode()).hexdigest()
        
        return fingerprint, ip_address, user_agent
    except:
        # Fallback ak sa nepodarí získať informácie
        import time
        fallback = f"fallback_{int(time.time())}"
        return hashlib.md5(fallback.encode()).hexdigest(), "unknown", "unknown"

def check_device_limit(session_name, device_fingerprint, ip_address, user_agent):
    """Skontroluje či zariadenie môže hodnotiť (limit 1x za hodinu)"""
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    
    try:
        # Kontrola posledného hodnotenia z tohto zariadenia
        cursor.execute('''
            SELECT last_evaluation, evaluation_count 
            FROM device_tracking 
            WHERE device_fingerprint = ? AND session_name = ?
        ''', (device_fingerprint, session_name))
        
        result = cursor.fetchone()
        
        if result is None:
            # Zariadenie ešte nehodnotilo
            return True, "OK", 0
        
        last_evaluation_str, eval_count = result
        
        # Parsovanie času posledného hodnotenia
        try:
            last_evaluation = datetime.strptime(last_evaluation_str, '%Y-%m-%d %H:%M:%S')
        except:
            # Ak sa nepodarí parsovať, povol hodnotenie
            return True, "OK", eval_count
        
        # Kontrola či uplynula hodina
        time_diff = datetime.now() - last_evaluation
        hours_passed = time_diff.total_seconds() / 3600
        
        if hours_passed >= 1.0:
            return True, "OK", eval_count
        else:
            remaining_minutes = int((1.0 - hours_passed) * 60)
            return False, f"Musíte počkať ešte {remaining_minutes} minút", eval_count
            
    except Exception as e:
        st.error(f"Chyba pri kontrole zariadenia: {e}")
        return True, "OK", 0  # V prípade chyby povol hodnotenie
    finally:
        conn.close()

def clear_evaluations_for_session(session_name):
    """Vymaže hodnotenia pre aktuálnu session"""
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    
    try:
        cursor.execute('DELETE FROM evaluations WHERE session_name = ? OR session_name IS NULL', (session_name,))
        deleted_evaluations = cursor.rowcount
        
        # Vymaž aj device tracking pre túto session
        cursor.execute('DELETE FROM device_tracking WHERE session_name = ?', (session_name,))
        deleted_devices = cursor.rowcount
        
        conn.commit()
        
        # Audit log
        log_audit_action(
            action_type="DATA_DELETE",
            action_description=f"Vymazané hodnotenia pre session '{session_name}' (hodnotenia: {deleted_evaluations}, zariadenia: {deleted_devices})",
            session_name=session_name,
            affected_records=deleted_evaluations + deleted_devices,
            success=True
        )
        
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
        # Pokus o update existujúceho záznamu
        cursor.execute('''
            UPDATE device_tracking 
            SET last_evaluation = CURRENT_TIMESTAMP, 
                evaluation_count = evaluation_count + 1,
                ip_address = ?,
                user_agent = ?
            WHERE device_fingerprint = ? AND session_name = ?
        ''', (ip_address, user_agent, device_fingerprint, session_name))
        
        # Ak neexistuje záznam, vytvor nový
        if cursor.rowcount == 0:
            cursor.execute('''
                INSERT INTO device_tracking 
                (device_fingerprint, ip_address, user_agent, session_name, evaluation_count)
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
        cursor.execute('''
            SELECT COUNT(*) as unique_devices,
                   SUM(evaluation_count) as total_evaluations,
                   MAX(last_evaluation) as last_activity
            FROM device_tracking 
            WHERE session_name = ?
        ''', (session_name,))
        
        result = cursor.fetchone()
        if result and result[0]:
            return {
                'unique_devices': result[0],
                'total_evaluations': result[1] or 0,
                'last_activity': result[2]
            }
        else:
            return {
                'unique_devices': 0,
                'total_evaluations': 0,
                'last_activity': None
            }
    except Exception as e:
        st.error(f"Chyba pri získavaní device stats: {e}")
        return {'unique_devices': 0, 'total_evaluations': 0, 'last_activity': None}
    finally:
        conn.close()

def get_mobile_css():
    """Vráti CSS štýly optimalizované pre mobilné zariadenia"""
    return """
    <style>
    /* Mobile-first responsive design */
    @media screen and (max-width: 768px) {
        .main .block-container {
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            max-width: 100% !important;
        }
    }
    
    /* Väčšie tlačidlá pre touch */
    .stButton > button {
        min-height: 3.5rem !important;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        border-radius: 12px !important;
        border: 2px solid transparent !important;
        transition: all 0.2s ease !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important;
    }
    
    /* Primárne tlačidlá */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #ff6b6b, #ee5a24) !important;
        color: white !important;
        border: none !important;
    }
    
    /* Selectboxy optimalizované pre mobile */
    .stSelectbox > div > div > div {
        min-height: 3.5rem !important;
        font-size: 1.1rem !important;
        border-radius: 12px !important;
        border: 2px solid #e0e0e0 !important;
    }
    
    .stSelectbox > div > div > div:focus-within {
        border-color: #ff6b6b !important;
        box-shadow: 0 0 0 3px rgba(255, 107, 107, 0.1) !important;
    }
    
    /* Text inputy */
    .stTextInput > div > div > input {
        min-height: 3.5rem !important;
        font-size: 1.1rem !important;
        border-radius: 12px !important;
        border: 2px solid #e0e0e0 !important;
        padding: 0 1rem !important;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #ff6b6b !important;
        box-shadow: 0 0 0 3px rgba(255, 107, 107, 0.1) !important;
    }
    
    /* Text area */
    .stTextArea > div > div > textarea {
        min-height: 6rem !important;
        font-size: 1.1rem !important;
        border-radius: 12px !important;
        border: 2px solid #e0e0e0 !important;
        padding: 1rem !important;
    }
    
    .stTextArea > div > div > textarea:focus {
        border-color: #ff6b6b !important;
        box-shadow: 0 0 0 3px rgba(255, 107, 107, 0.1) !important;
    }
    
    /* Progress indicator */
    .progress-steps {
        display: flex;
        justify-content: center;
        align-items: center;
        margin: 2rem 0;
        flex-wrap: wrap;
    }
    
    .progress-step {
        width: 40px;
        height: 40px;
        border-radius: 50%;
        background-color: #e0e0e0;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 0.5rem;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    
    .progress-step.active {
        background-color: #ff6b6b;
        color: white;
        transform: scale(1.1);
    }
    
    .progress-step.completed {
        background-color: #2ecc71;
        color: white;
    }
    </style>
    """

def export_evaluations_to_csv(session_name=None):
    """Exportuje hodnotenia do CSV"""
    conn = sqlite3.connect("consumervote.db")
    
    try:
        if session_name:
            df = pd.read_sql_query('''
                SELECT session_name as "Session",
                       evaluator_name as "Hodnotiteľ",
                       evaluation_data as "Hodnotenia",
                       comment as "Komentár", 
                       created_at as "Čas"
                FROM evaluations 
                WHERE session_name = ? OR session_name IS NULL
                ORDER BY created_at DESC
            ''', conn, params=(session_name,))
        else:
            df = pd.read_sql_query('''
                SELECT session_name as "Session",
                       evaluator_name as "Hodnotiteľ",
                       evaluation_data as "Hodnotenia",
                       comment as "Komentár", 
                       created_at as "Čas"
                FROM evaluations 
                ORDER BY created_at DESC
            ''', conn)
        
        return df
    except Exception as e:
        st.error(f"Chyba pri exporte: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

# Inicializácia session state pre admin mode
if 'admin_mode' not in st.session_state:
    st.session_state.admin_mode = True  # Začíname na admin

if 'admin_authenticated' not in st.session_state:
    st.session_state.admin_authenticated = False

if 'admin_session_token' not in st.session_state:
    st.session_state.admin_session_token = None

# Admin heslo v MD5 (consumertest24)
ADMIN_PASSWORD_MD5 = hashlib.md5("consumertest24".encode()).hexdigest()

def hash_password(password):
    """Vytvorí MD5 hash z hesla"""
    return hashlib.md5(password.encode()).hexdigest()

def verify_password(password, stored_hash):
    """Overí heslo proti MD5 hash"""
    return hash_password(password) == stored_hash

def generate_qr_code_url(url, size="200x200", error_correction="M"):
    """Generuje URL pre QR kód pomocou online služby s optimalizáciou pre vonkajšie podmienky"""
    encoded_url = urllib.parse.quote(url, safe='')
    
    # Skúsime viacero QR API služieb pre lepšiu dostupnosť
    qr_services = [
        f"https://api.qrserver.com/v1/create-qr-code/?size={size}&ecc={error_correction}&color=000000&bgcolor=ffffff&margin=2&data={encoded_url}",
        f"https://chart.googleapis.com/chart?chs={size}&cht=qr&chl={encoded_url}&choe=UTF-8",
        f"https://qr-code-generator24.com/qr-code-api?size={size}&data={encoded_url}"
    ]
    
    return qr_services[0]  # Začneme s prvou službou

def get_simple_landing_css():
    """Minimalistický CSS pre landing page - len názov a QR kód"""
    return """
    <style>
    .simple-landing {
        background: #ffffff;
        min-height: 100vh;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 2rem;
        text-align: center;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    .simple-title {
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 3rem;
        color: #2c3e50;
    }
    
    .simple-qr {
        background: white;
        padding: 2rem;
        border-radius: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        border: 2px solid #e0e0e0;
    }
    
    @media (max-width: 768px) {
        .simple-title {
            font-size: 2rem;
        }
        
        .simple-qr {
            padding: 1.5rem;
        }
    }
    </style>
    """

def simple_landing_page():
    """Jednoduchá landing page s len názvom a QR kódom"""
    
    # Skryť sidebar úplne
    st.markdown("""
    <style>
    .stSidebar {
        display: none;
    }
    .main > div {
        padding-top: 0rem;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Aplikuj minimalistický CSS
    st.markdown(get_simple_landing_css(), unsafe_allow_html=True)
    
    # Získanie aktuálneho stavu
    current_state = get_current_state()
    
    if not current_state['session_active']:
        st.markdown("""
        <div class="simple-landing">
            <h1 class="simple-title">❌ Hodnotenie nie je aktívne</h1>
        </div>
        """, unsafe_allow_html=True)
        return
    
    # Hlavný title
    st.markdown(f"""
    <div class="simple-landing">
        <h1 class="simple-title">{current_state['session_name']}</h1>
    </div>
    """, unsafe_allow_html=True)
    
    # QR kód pomocou Streamlit image (lepšia kompatibilita)
    app_url = "https://consumervote.streamlit.app"
    evaluator_url = f"{app_url}?mode=evaluator&hide_sidebar=true"
    
    # Skúsime viacero QR služieb
    qr_urls = [
        # Google Charts API - zvyčajne najspoľahlivejšie
        f"https://chart.googleapis.com/chart?chs=400x400&cht=qr&chl={urllib.parse.quote(evaluator_url)}&choe=UTF-8",
        # QR Server API
        f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&ecc=H&color=000000&bgcolor=ffffff&margin=2&data={urllib.parse.quote(evaluator_url)}",
        # Fallback
        f"https://qr-code-generator24.com/qr-code-api?size=400x400&data={urllib.parse.quote(evaluator_url)}"
    ]
    
    # Centrovaný QR kód pomocou Streamlit
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        qr_loaded = False
        
        for i, qr_url in enumerate(qr_urls):
            try:
                st.image(qr_url, caption="QR kód pre hodnotenie", width=400)
                qr_loaded = True
                break
            except Exception as e:
                if i == len(qr_urls) - 1:  # Posledný pokus
                    st.error("⚠️ Chyba pri načítaní QR kódu")
                continue
        
        if not qr_loaded:
            st.warning("QR kód sa nepodarilo načítať. Použite priamy odkaz:")
            st.markdown(f"""
            <div style="text-align: center; margin: 2rem 0;">
                <a href="{evaluator_url}" target="_blank" style="
                    display: inline-block;
                    padding: 1rem 2rem;
                    background-color: #007bff;
                    color: white;
                    text-decoration: none;
                    border-radius: 8px;
                    font-weight: bold;
                    font-size: 1.2rem;
                ">📱 Prejsť na hodnotenie</a>
            </div>
            """, unsafe_allow_html=True)

def admin_login():
    """Login formulár pre admin s persistent session"""
    
    # Kontrola existujúcej session
    if st.session_state.admin_session_token:
        if verify_admin_session(st.session_state.admin_session_token):
            st.session_state.admin_authenticated = True
            st.rerun()
    
    st.title("🔐 Admin Dashboard")
    st.write("Zadajte heslo pre prístup k administrácii:")
    
    with st.form("admin_login_form"):
        password = st.text_input("Heslo:", type="password", placeholder="Zadajte admin heslo")
        submitted = st.form_submit_button("🔓 Prihlásiť sa", type="primary")
        
        if submitted:
            if verify_password(password, ADMIN_PASSWORD_MD5):
                # Vytvor persistent session
                session_token = create_admin_session()
                if session_token:
                    st.session_state.admin_session_token = session_token
                    st.session_state.admin_authenticated = True
                    
                    # Audit log
                    log_audit_action(
                        action_type="AUTH_LOGIN",
                        action_description="Admin úspešne prihlásený",
                        success=True
                    )
                    
                    st.success("✅ Úspešne prihlásený!")
                    st.rerun()
                else:
                    st.error("❌ Chyba pri vytváraní session!")
            else:
                # Audit log pre neúspešné prihlásenie
                log_audit_action(
                    action_type="AUTH_LOGIN_FAILED",
                    action_description="Neúspešný pokus o prihlásenie admina",
                    success=False
                )
                st.error("❌ Nesprávne heslo!")
    
    st.divider()
    if st.button("👥 Prejsť na hodnotenie"):
        st.session_state.admin_mode = False
        st.rerun()

def admin_dashboard():
    """Admin dashboard rozhranie"""
    
    # Kontrola autentifikácie
    if not st.session_state.admin_authenticated:
        admin_login()
        return
    
    # Overenie session tokenu
    if not verify_admin_session(st.session_state.admin_session_token):
        st.session_state.admin_authenticated = False
        st.session_state.admin_session_token = None
        st.error("⚠️ Session expirovala. Prihláste sa znovu.")
        st.rerun()
    
    # Získanie aktuálneho stavu
    current_state = get_current_state()
    
    # Header s možnosťou odhlásenia
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("📊 Admin Dashboard")
    with col2:
        if st.button("🚪 Odhlásiť"):
            destroy_admin_session(st.session_state.admin_session_token)
            st.session_state.admin_authenticated = False
            st.session_state.admin_session_token = None
            st.rerun()
    
    # Dashboard metriky
    device_stats = get_device_stats(current_state['session_name'])
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "📋 Session Status", 
            "✅ Aktívna" if current_state['session_active'] else "❌ Neaktívna",
            current_state['session_name']
        )
    with col2:
        st.metric("🧪 Vzorky", current_state['samples_count'])
    with col3:
        st.metric("📝 Hodnotenia", len(current_state['evaluations']))
    with col4:
        st.metric("📱 Zariadenia", device_stats['unique_devices'])
    
    st.divider()
    
    # Hlavné ovládanie
    if current_state['session_active']:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("🔗 QR kód pre hodnotiteľov")
            
            # URL aplikácie
            app_url = "https://consumervote.streamlit.app"
            landing_url = f"{app_url}?mode=landing&hide_sidebar=true"
            
            # QR kód
            qr_image_url = generate_qr_code_url(landing_url, size="300x300", error_correction="H")
            
            col_qr1, col_qr2, col_qr3 = st.columns([1, 2, 1])
            with col_qr2:
                st.image(qr_image_url, width=300)
            
            # Akčné tlačidlá
            col_btn1, col_btn2 = st.columns(2)
            
            with col_btn1:
                st.markdown(f"""
                <a href="{landing_url}" target="_blank" style="
                    display: inline-block;
                    padding: 0.75rem 1.5rem;
                    background-color: #2ecc71;
                    color: white;
                    text-decoration: none;
                    border-radius: 8px;
                    font-weight: 600;
                    text-align: center;
                    width: 100%;
                    box-sizing: border-box;
                ">🖼️ Otvoriť Landing Page</a>
                """, unsafe_allow_html=True)
            
            with col_btn2:
                evaluator_url = f"{app_url}?mode=evaluator&hide_sidebar=true"
                st.markdown(f"""
                <a href="{evaluator_url}" target="_blank" style="
                    display: inline-block;
                    padding: 0.75rem 1.5rem;
                    background-color: #3498db;
                    color: white;
                    text-decoration: none;
                    border-radius: 8px;
                    font-weight: 600;
                    text-align: center;
                    width: 100%;
                    box-sizing: border-box;
                ">📱 Priame Hodnotenie</a>
                """, unsafe_allow_html=True)
        
        with col2:
            st.subheader("⚙️ Rýchle akcie")
            
            if st.button("🔄 Reset hodnotení", use_container_width=True):
                if clear_evaluations_for_session(current_state['session_name']):
                    st.success("✅ Hodnotenia vymazané!")
                    st.rerun()
                else:
                    st.error("❌ Chyba pri mazaní!")
            
            if st.button("⏹️ Zastaviť hodnotenie", use_container_width=True):
                if save_evaluation_settings(current_state['session_name'], current_state['samples_count'], current_state['samples_names'], False):
                    st.success("✅ Hodnotenie zastavené!")
                    st.rerun()
                else:
                    st.error("❌ Chyba!")
            
            if st.button("👥 Prejsť na hodnotenie", use_container_width=True):
                st.session_state.admin_mode = False
                st.rerun()
    
    else:
        st.warning("⚠️ Hodnotenie nie je aktívne. Nastavte ho v sekcii Nastavenia.")
    
    # Expandable sekcie
    with st.expander("⚙️ Nastavenia hodnotenia", expanded=not current_state['session_active']):
        admin_settings_section(current_state)
    
    with st.expander("📊 Výsledky a export"):
        admin_results_section(current_state)
    
    with st.expander("🔧 Systémové informácie"):
        admin_system_section(current_state, device_stats)

def admin_settings_section(current_state):
    """Sekcia nastavení v dashboarde"""
    
    # Názov session/akcie
    session_name = st.text_input(
        "📋 Názov hodnotenia/akcie:",
        value=current_state['session_name'],
        placeholder="Napr. Hodnotenie letnej ponuky 2024"
    )
    
    # Počet vzoriek
    samples_count = st.number_input(
        "🧪 Počet vzoriek:",
        min_value=2,
        max_value=20,
        value=current_state['samples_count'] if current_state['samples_count'] > 0 else 3
    )
    
    # Názvy vzoriek
    st.write("**🏷️ Názvy vzoriek:**")
    sample_names = []
    
    for i in range(samples_count):
        name = st.text_input(
            f"Vzorka {i+1}:",
            value=current_state['samples_names'][i] if i < len(current_state['samples_names']) else f"Vzorka {i+1}",
            key=f"sample_name_{i}",
            placeholder=f"Napr. Jogurt jahoda, Pivo svetlé, atď."
        )
        sample_names.append(name)
    
    # Tlačidlá
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("💾 Uložiť a Spustiť", type="primary", use_container_width=True):
            if save_evaluation_settings(session_name, samples_count, sample_names, True):
                st.success("✅ Nastavenia uložené a hodnotenie spustené!")
                st.rerun()
            else:
                st.error("❌ Chyba pri ukladaní!")
    
    with col2:
        if st.button("💾 Uložiť bez spustenia", use_container_width=True):
            if save_evaluation_settings(session_name, samples_count, sample_names, False):
                st.success("✅ Nastavenia uložené!")
                st.rerun()
            else:
                st.error("❌ Chyba pri ukladaní!")

def admin_results_section(current_state):
    """Sekcia výsledkov v dashboarde"""
    
    if not current_state['evaluations']:
        st.info("📝 Zatiaľ žiadne hodnotenia")
        return
    
    # Export tlačidlá
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 Export CSV (aktuálna session)", use_container_width=True):
            df = export_evaluations_to_csv(current_state['session_name'])
            if not df.empty:
                csv = df.to_csv(index=False)
                st.download_button(
                    label="⬇️ Stiahnuť CSV",
                    data=csv,
                    file_name=f"hodnotenia_{current_state['session_name'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
    
    with col2:
        if st.button("📥 Export CSV (všetky sessions)", use_container_width=True):
            df = export_evaluations_to_csv()
            if not df.empty:
                csv = df.to_csv(index=False)
                st.download_button(
                    label="⬇️ Stiahnuť všetky CSV",
                    data=csv,
                    file_name=f"hodnotenia_vsetky_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
    
    # Zobrazenie posledných hodnotení
    st.write("**📋 Posledných 10 hodnotení:**")
    df_display = pd.DataFrame(current_state['evaluations'][-10:])
    st.dataframe(df_display, use_container_width=True)

def admin_system_section(current_state, device_stats):
    """Sekcia systémových informácií v dashboarde"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**📊 Session informácie:**")
        st.write(f"• Názov: {current_state['session_name']}")
        st.write(f"• Status: {'✅ Aktívna' if current_state['session_active'] else '❌ Neaktívna'}")
        st.write(f"• Vzorky: {current_state['samples_count']}")
        st.write(f"• Hodnotenia: {len(current_state['evaluations'])}")
        
        if device_stats['last_activity']:
            st.write(f"• Posledná aktivita: {device_stats['last_activity']}")
    
    with col2:
        st.write("**🗄️ Databáza:**")
        try:
            if os.path.exists("consumervote.db"):
                db_size = os.path.getsize("consumervote.db") / 1024
                st.write(f"• Veľkosť: {db_size:.1f} KB")
                st.write("• Status: ✅ Pripojená")
            else:
                st.write("• Status: ⚠️ Inicializuje sa...")
        except:
            st.write("• Status: ❌ Problém")
        
        st.write(f"• Jedinečné zariadenia: {device_stats['unique_devices']}")
        st.write(f"• Celkové hodnotenia: {device_stats['total_evaluations']}")
    
    # Reset device tracking
    if device_stats['unique_devices'] > 0:
        if st.button("🔄 Reset zariadení (umožní opätovné hodnotenie)", use_container_width=True):
            conn = sqlite3.connect("consumervote.db")
            cursor = conn.cursor()
            try:
                cursor.execute('DELETE FROM device_tracking WHERE session_name = ?', (current_state['session_name'],))
                conn.commit()
                st.success("✅ Device tracking resetovaný!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Chyba: {e}")
            finally:
                conn.close()

def evaluator_interface():
    """Mobile-first rozhranie pre hodnotiteľov"""
    
    # Aplikuj mobile CSS
    st.markdown(get_mobile_css(), unsafe_allow_html=True)
    
    # Získanie aktuálneho stavu
    current_state = get_current_state()
    
    # Mobile optimalizovaný title
    st.markdown(f'<h1 style="font-size: 1.8rem; font-weight: 700; text-align: center; margin-bottom: 1rem; color: #2c3e50;">🧪 {current_state["session_name"]}</h1>', unsafe_allow_html=True)
    
    if not current_state['session_active']:
        st.error("❌ Hodnotenie nie je aktívne. Kontaktujte administrátora.")
        return
    
    # Kontrola device limitu
    device_fingerprint, ip_address, user_agent = get_device_fingerprint()
    can_evaluate, message, eval_count = check_device_limit(
        current_state['session_name'], device_fingerprint, ip_address, user_agent
    )
    
    if not can_evaluate:
        st.warning(f"⏰ {message}")
        if eval_count > 0:
            st.info(f"✅ Z tohto zariadenia už bolo odoslaných {eval_count} hodnotení")
        return
    
    # Progress indicator
    step = 1
    if 'show_confirmation' in st.session_state and st.session_state.show_confirmation:
        step = 2
    if 'evaluation_submitted' in st.session_state and st.session_state.evaluation_submitted:
        step = 3
    
    st.markdown(f"""
    <div class="progress-steps">
        <div class="progress-step {'completed' if step > 1 else 'active' if step == 1 else ''}">1</div>
        <div style="width: 20px; height: 2px; background-color: {'#2ecc71' if step > 1 else '#e0e0e0'}; margin: 0 0.5rem;"></div>
        <div class="progress-step {'completed' if step > 2 else 'active' if step == 2 else ''}">2</div>
        <div style="width: 20px; height: 2px; background-color: {'#2ecc71' if step > 2 else '#e0e0e0'}; margin: 0 0.5rem;"></div>
        <div class="progress-step {'active' if step == 3 else ''}">3</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Inicializácia stavu
    if 'show_confirmation' not in st.session_state:
        st.session_state.show_confirmation = False
    if 'evaluation_submitted' not in st.session_state:
        st.session_state.evaluation_submitted = False
    
    # Ak bolo hodnotenie úspešne odoslané
    if st.session_state.evaluation_submitted:
        st.success("🎉 Ďakujeme za hodnotenie!")
        st.balloons()
        
        if st.button("🔄 Nové hodnotenie", type="primary"):
            st.session_state.evaluation_submitted = False
            st.session_state.show_confirmation = False
            st.rerun()
        
        return
    
    # Krok 1: Hlavný formulár
    if not st.session_state.show_confirmation:
        
        st.info("📝 Vyberte TOP 3 vzorky v poradí od najlepšej po tretiu najlepšiu")
        
        # Meno hodnotiteľa
        st.subheader("👤 Vaše meno")
        evaluator_name = st.text_input("", placeholder="Zadajte vaše meno alebo prezývku", label_visibility="collapsed")
        
        st.subheader("🏆 TOP 3 vzorky")
        
        # 1. miesto
        st.markdown("### 🥇 1. miesto")
        first_place = st.selectbox("", options=['Vyberte vzorku...'] + current_state['samples_names'], key="first_place_select", label_visibility="collapsed")
        if first_place == 'Vyberte vzorku...':
            first_place = None
        
        # 2. miesto
        st.markdown("### 🥈 2. miesto")
        available_for_second = [s for s in current_state['samples_names'] if s != first_place]
        second_place = st.selectbox("", options=['Vyberte vzorku...'] + available_for_second, key="second_place_select", label_visibility="collapsed")
        if second_place == 'Vyberte vzorku...':
            second_place = None
        
        # 3. miesto
        st.markdown("### 🥉 3. miesto")
        available_for_third = [s for s in current_state['samples_names'] if s != first_place and s != second_place]
        third_place = st.selectbox("", options=['Vyberte vzorku...'] + available_for_third, key="third_place_select", label_visibility="collapsed")
        if third_place == 'Vyberte vzorku...':
            third_place = None
        
        # Zostavenie výberu
        selected_samples = {}
        if first_place:
            selected_samples['1'] = first_place
        if second_place:
            selected_samples['2'] = second_place
        if third_place:
            selected_samples['3'] = third_place
        
        # Zobrazenie súhrnu
        if selected_samples:
            st.subheader("📋 Váš výber")
            for place, sample in selected_samples.items():
                medal = "🥇" if place == "1" else "🥈" if place == "2" else "🥉"
                st.success(f"{medal} **{place}. miesto**: {sample}")
        
        # Komentár
        st.subheader("💬 Komentár (voliteľný)")
        comment = st.text_area("", placeholder="Váš komentár k hodnoteniu...", label_visibility="collapsed", height=100)
        
        # Tlačidlo pokračovať
        if st.button("📤 Pokračovať na kontrolu", type="primary", use_container_width=True):
            if not evaluator_name.strip():
                st.error("❌ Prosím zadajte vaše meno!")
            elif not selected_samples:
                st.error("❌ Prosím vyberte aspoň jednu vzorku!")
            else:
                st.session_state.temp_evaluation = {
                    'session_name': current_state['session_name'],
                    'evaluator_name': evaluator_name,
                    'selected_samples': selected_samples,
                    'comment': comment,
                    'device_fingerprint': device_fingerprint,
                    'ip_address': ip_address,
                    'user_agent': user_agent
                }
                st.session_state.show_confirmation = True
                st.rerun()
    
    # Krok 2: Potvrdzovacie okno
    else:
        st.subheader("✅ Kontrola hodnotenia")
        
        temp_eval = st.session_state.temp_evaluation
        
        st.info(f"👤 **{temp_eval['evaluator_name']}** - {temp_eval['session_name']}")
        
        # Výsledky hodnotenia
        for place, sample in temp_eval['selected_samples'].items():
            medal = "🥇" if place == "1" else "🥈" if place == "2" else "🥉"
            color = "#ffd700" if place == "1" else "#c0c0c0" if place == "2" else "#cd7f32"
            
            st.markdown(f"""
            <div style="background-color: {color}; padding: 1rem; border-radius: 12px; margin: 0.5rem 0; text-align: center; color: {'black' if place != '3' else 'white'};">
                <h4>{medal} {place}. miesto</h4>
                <p style="margin: 0; font-weight: bold;">{sample}</p>
            </div>
            """, unsafe_allow_html=True)
        
        if temp_eval['comment']:
            st.info(f"**Komentár:** {temp_eval['comment']}")
        
        # Akčné tlačidlá
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("✅ Potvrdiť", type="primary", use_container_width=True):
                # Príprava dát
                evaluation_data = {}
                for sample_name in current_state['samples_names']:
                    if sample_name == temp_eval['selected_samples'].get('1'):
                        evaluation_data[f'poradie_{sample_name}'] = 1
                    elif sample_name == temp_eval['selected_samples'].get('2'):
                        evaluation_data[f'poradie_{sample_name}'] = 2
                    elif sample_name == temp_eval['selected_samples'].get('3'):
                        evaluation_data[f'poradie_{sample_name}'] = 3
                    else:
                        evaluation_data[f'poradie_{sample_name}'] = 999
                
                # Uloženie do databázy
                if save_evaluation(temp_eval['session_name'], temp_eval['evaluator_name'], evaluation_data, temp_eval['comment']):
                    # Aktualizácia device tracking
                    update_device_tracking(temp_eval['session_name'], temp_eval['device_fingerprint'], temp_eval['ip_address'], temp_eval['user_agent'])
                    
                    st.session_state.evaluation_submitted = True
                    st.session_state.show_confirmation = False
                    if 'temp_evaluation' in st.session_state:
                        del st.session_state.temp_evaluation
                    st.rerun()
                else:
                    st.error("❌ Chyba pri ukladaní!")
        
        with col2:
            if st.button("❌ Späť", use_container_width=True):
                st.session_state.show_confirmation = False
                st.rerun()

def main():
    """Hlavná funkcia aplikácie"""
    
    # Inicializácia databázy
    init_database()
    
    try:
        query_params = st.query_params
    except:
        query_params = {}
    
    hide_sidebar = False
    force_evaluator = False
    force_landing = False
    
    if query_params:
        if 'hide_sidebar' in query_params:
            hide_sidebar = str(query_params.get('hide_sidebar', '')).lower() == 'true'
        if 'mode' in query_params:
            mode = str(query_params.get('mode', '')).lower()
            if mode == 'evaluator':
                force_evaluator = True
                st.session_state.admin_mode = False
            elif mode == 'landing':
                force_landing = True
                st.session_state.admin_mode = False
    
    # Ak je force landing mode, zobraz landing page
    if force_landing:
        simple_landing_page()
        return
    
    # Ak je evaluator mode alebo hide_sidebar, zobraz evaluator
    if hide_sidebar or force_evaluator:
        st.session_state.admin_mode = False
        evaluator_interface()
        return
    
    # Overenie admin session při štarte
    if st.session_state.admin_session_token and not st.session_state.admin_authenticated:
        if verify_admin_session(st.session_state.admin_session_token):
            st.session_state.admin_authenticated = True
    
    # Získanie aktuálneho stavu
    current_state = get_current_state()
    
    # Sidebar pre navigáciu
    with st.sidebar:
        st.title("🧪 Hodnotenie vzoriek")
        
        # Zobrazenie aktuálnej session
        if current_state['session_active']:
            st.success(f"📋 **{current_state['session_name']}**")
            st.metric("Hodnotenia", len(current_state['evaluations']))
        else:
            st.warning("⚠️ Hodnotenie neaktívne")
        
        if st.session_state.admin_authenticated:
            st.success("✅ Admin prihlásený")
        else:
            st.info("🔐 Admin neprihlásený")
        
        mode = st.radio(
            "Vyberte režim:",
            ["🔧 Admin Dashboard", "👥 Hodnotiteľ"],
            index=0 if st.session_state.admin_mode else 1
        )
        
        st.session_state.admin_mode = (mode == "🔧 Admin Dashboard")
        
        if st.session_state.admin_authenticated and st.button("🚪 Rýchle odhlásenie", use_container_width=True):
            destroy_admin_session(st.session_state.admin_session_token)
            st.session_state.admin_authenticated = False
            st.session_state.admin_session_token = None
            st.rerun()
    
    if st.session_state.admin_mode:
        admin_dashboard()
    else:
        evaluator_interface()

if __name__ == "__main__":
    main()