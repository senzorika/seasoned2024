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

def get_admin_session_info():
    """Získa informácie o admin session pre audit"""
    try:
        # Získanie IP adresy
        headers = st.context.headers if hasattr(st.context, 'headers') else {}
        ip_address = (
            headers.get('x-forwarded-for', '').split(',')[0].strip() or
            headers.get('x-real-ip', '') or
            headers.get('remote-addr', 'unknown')
        )
        
        # Vytvorenie session ID
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

def get_audit_logs(limit=50, action_type=None, session_name=None):
    """Získa audit logy z databázy"""
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    
    try:
        query = '''
            SELECT timestamp, admin_session_id, admin_ip, action_type, action_description,
                   session_name, old_values, new_values, affected_records, success, error_message
            FROM audit_log
        '''
        params = []
        
        conditions = []
        if action_type:
            conditions.append("action_type = ?")
            params.append(action_type)
        if session_name:
            conditions.append("session_name = ?")
            params.append(session_name)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        return cursor.fetchall()
    except Exception as e:
        st.error(f"Chyba pri načítaní audit logov: {e}")
        return []
    finally:
        conn.close()

def get_audit_statistics():
    """Získa základné štatistiky auditov"""
    conn = sqlite3.connect("consumervote.db")
    cursor = conn.cursor()
    
    try:
        # Celkový počet akcií
        cursor.execute('SELECT COUNT(*) FROM audit_log')
        total_actions = cursor.fetchone()[0]
        
        # Posledná aktivita
        cursor.execute('SELECT MAX(timestamp) FROM audit_log')
        last_activity = cursor.fetchone()[0]
        
        # Najpopulárnejšie akcie
        cursor.execute('''
            SELECT action_type, COUNT(*) as count 
            FROM audit_log 
            GROUP BY action_type 
            ORDER BY count DESC 
            LIMIT 5
        ''')
        popular_actions = cursor.fetchall()
        
        # Úspešnosť akcií
        cursor.execute('SELECT success, COUNT(*) FROM audit_log GROUP BY success')
        success_stats = dict(cursor.fetchall())
        
        return {
            'total_actions': total_actions,
            'last_activity': last_activity,
            'popular_actions': popular_actions,
            'success_rate': success_stats.get(1, 0) / max(total_actions, 1) * 100
        }
    except Exception as e:
        st.error(f"Chyba pri získavaní audit štatistík: {e}")
        return {'total_actions': 0, 'last_activity': None, 'popular_actions': [], 'success_rate': 0}
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
        # Získanie IP adresy
        headers = st.context.headers if hasattr(st.context, 'headers') else {}
        ip_address = (
            headers.get('x-forwarded-for', '').split(',')[0].strip() or
            headers.get('x-real-ip', '') or
            headers.get('remote-addr', 'unknown')
        )
        
        # User agent
        user_agent = headers.get('user-agent', 'unknown')
        
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
        # Vymaž aj device tracking pre túto session
        cursor.execute('DELETE FROM device_tracking WHERE session_name = ?', (session_name,))
        conn.commit()
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
    
    /* Medaily pre mobile */
    .medal-card {
        background: white;
        border-radius: 16px;
        padding: 1.5rem;
        margin: 0.5rem 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        border: 2px solid transparent;
        transition: all 0.3s ease;
    }
    
    .medal-card.selected-1 {
        background: linear-gradient(135deg, #ffd700, #ffed4e);
        border-color: #f39c12;
        transform: scale(1.02);
    }
    
    .medal-card.selected-2 {
        background: linear-gradient(135deg, #c0c0c0, #ecf0f1);
        border-color: #95a5a6;
        transform: scale(1.02);
    }
    
    .medal-card.selected-3 {
        background: linear-gradient(135deg, #cd7f32, #d35400);
        border-color: #e67e22;
        color: white;
        transform: scale(1.02);
    }
    
    /* Alert komponenty */
    .stAlert {
        border-radius: 12px !important;
        border: none !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
    }
    
    /* Spacing pre mobile */
    .mobile-spacing {
        margin: 1.5rem 0;
    }
    
    .mobile-title {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
        text-align: center !important;
        margin-bottom: 1rem !important;
        color: #2c3e50 !important;
    }
    
    .mobile-subtitle {
        font-size: 1.3rem !important;
        font-weight: 600 !important;
        margin: 1.5rem 0 1rem 0 !important;
        color: #34495e !important;
    }
    
    /* Responsívne stĺpce */
    @media screen and (max-width: 768px) {
        .stColumns {
            flex-direction: column !important;
        }
        
        .stColumn {
            width: 100% !important;
            margin-bottom: 1rem !important;
        }
    }
    
    /* Loading spinner */
    .loading-spinner {
        display: inline-block;
        width: 20px;
        height: 20px;
        border: 3px solid rgba(255,255,255,.3);
        border-radius: 50%;
        border-top-color: #fff;
        animation: spin 1s ease-in-out infinite;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    /* Mobile info box */
    .mobile-info {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 16px;
        margin: 1rem 0;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
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
    st.session_state.admin_mode = False
if 'admin_authenticated' not in st.session_state:
    st.session_state.admin_authenticated = False

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
    # Použitie väčšieho QR kódu s vyššou error correction pre lepšiu čitateľnosť vonku
    qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size={size}&ecc={error_correction}&color=000000&bgcolor=ffffff&margin=2&data={encoded_url}"
    return qr_api_url

def get_landing_page_css():
    """CSS pre landing page s QR kódom"""
    return """
    <style>
    .landing-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        min-height: 100vh;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 2rem;
        color: white;
        text-align: center;
    }
    
    .landing-title {
        font-size: 2.5rem;
        font-weight: 800;
        margin-bottom: 1rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    
    .landing-subtitle {
        font-size: 1.3rem;
        margin-bottom: 2rem;
        opacity: 0.9;
    }
    
    .qr-container {
        background: white;
        padding: 2rem;
        border-radius: 20px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        margin: 2rem 0;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.05); }
        100% { transform: scale(1); }
    }
    
    .qr-instructions {
        background: rgba(255,255,255,0.1);
        backdrop-filter: blur(10px);
        border-radius: 15px;
        padding: 1.5rem;
        margin-top: 2rem;
        border: 1px solid rgba(255,255,255,0.2);
    }
    
    .feature-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 1.5rem;
        margin-top: 2rem;
        width: 100%;
        max-width: 800px;
    }
    
    .feature-card {
        background: rgba(255,255,255,0.1);
        backdrop-filter: blur(10px);
        border-radius: 15px;
        padding: 1.5rem;
        border: 1px solid rgba(255,255,255,0.2);
        transition: transform 0.3s ease;
    }
    
    .feature-card:hover {
        transform: translateY(-5px);
    }
    
    .action-button {
        background: linear-gradient(135deg, #ff6b6b, #ee5a24);
        color: white;
        padding: 1rem 2rem;
        border: none;
        border-radius: 50px;
        font-size: 1.2rem;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        text-decoration: none;
        display: inline-block;
        margin: 1rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    
    .action-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0,0,0,0.3);
    }
    
    @media (max-width: 768px) {
        .landing-title {
            font-size: 2rem;
        }
        
        .landing-subtitle {
            font-size: 1.1rem;
        }
        
        .qr-container {
            padding: 1.5rem;
            margin: 1.5rem 0;
        }
        
        .feature-grid {
            grid-template-columns: 1fr;
            gap: 1rem;
        }
    }
    </style>
    """

def landing_page_interface():
    """Dedikovaná landing page pre QR kód"""
    
    # Skryť sidebar úplne pre čistý vzhľad
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
    
    # Aplikuj CSS pre landing page
    st.markdown(get_landing_page_css(), unsafe_allow_html=True)
    
    # Získanie aktuálneho stavu
    current_state = get_current_state()
    
    if not current_state['session_active']:
        st.markdown("""
        <div class="landing-container">
            <h1 class="landing-title">❌ Hodnotenie nie je aktívne</h1>
            <p class="landing-subtitle">Kontaktujte administrátora pre aktiváciu</p>
        </div>
        """, unsafe_allow_html=True)
        return
    
    # Hlavná landing page
    st.markdown(f"""
    <div class="landing-container">
        <h1 class="landing-title">🧪 {current_state['session_name']}</h1>
        <p class="landing-subtitle">Naskenujte QR kód pre začiatok hodnotenia</p>
    """, unsafe_allow_html=True)
    
    # Veľký QR kód optimalizovaný pre vonkajšie podmienky
    app_url = "https://consumervote.streamlit.app"
    evaluator_url = f"{app_url}?mode=evaluator&hide_sidebar=true"
    
    # Veľký QR kód s vysokou error correction
    large_qr_url = generate_qr_code_url(evaluator_url, size="400x400", error_correction="H")
    
    st.markdown(f"""
        <div class="qr-container">
            <img src="{large_qr_url}" alt="QR kód pre hodnotenie" style="max-width: 100%; height: auto;" />
        </div>
        
        <div class="qr-instructions">
            <h3>📱 Ako hodnotiť:</h3>
            <p>1. Naskenujte QR kód fotoaparátom</p>
            <p>2. Otvorte odkaz v prehliadači</p>
            <p>3. Vyberte TOP 3 vzorky</p>
            <p>4. Odošlite hodnotenie</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Funkcie hodnotenia
    st.markdown(f"""
        <div class="feature-grid">
            <div class="feature-card">
                <h4>🏆 TOP 3 hodnotenie</h4>
                <p>Vyberte len 3 najlepšie vzorky zo {current_state['samples_count']} možností</p>
            </div>
            
            <div class="feature-card">
                <h4>📱 Mobile optimalizované</h4>
                <p>Perfektne funguje na mobilných zariadeniach</p>
            </div>
            
            <div class="feature-card">
                <h4>⚡ Rýchle hodnotenie</h4>
                <p>Hodnotenie trvá len 2-3 minúty</p>
            </div>
            
            <div class="feature-card">
                <h4>🔒 Anonymné</h4>
                <p>Zadáte len meno alebo prezývku</p>
            </div>
        </div>
        
        <a href="{evaluator_url}" class="action-button" target="_blank">
            🔗 Alebo kliknite pre hodnotenie
        </a>
        
    </div>
    """, unsafe_allow_html=True)

def get_sharing_qr_css():
    """CSS pre sharing QR kód po hodnotení"""
    return """
    <style>
    .sharing-container {
        background: linear-gradient(135deg, #2ecc71, #27ae60);
        color: white;
        padding: 2rem;
        border-radius: 20px;
        text-align: center;
        margin: 2rem 0;
        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
    }
    
    .sharing-title {
        font-size: 1.8rem;
        font-weight: 700;
        margin-bottom: 1rem;
    }
    
    .sharing-qr {
        background: white;
        padding: 1.5rem;
        border-radius: 15px;
        display: inline-block;
        margin: 1rem 0;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    
    .sharing-instructions {
        background: rgba(255,255,255,0.1);
        backdrop-filter: blur(10px);
        border-radius: 12px;
        padding: 1.5rem;
        margin-top: 1rem;
        border: 1px solid rgba(255,255,255,0.2);
    }
    
    .pulse-animation {
        animation: qr-pulse 3s infinite;
    }
    
    @keyframes qr-pulse {
        0% { transform: scale(1); box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
        50% { transform: scale(1.05); box-shadow: 0 6px 20px rgba(0,0,0,0.2); }
        100% { transform: scale(1); box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
    }
    
    .thank-you-emojis {
        font-size: 3rem;
        margin: 1rem 0;
        animation: bounce 2s infinite;
    }
    
    @keyframes bounce {
        0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
        40% { transform: translateY(-10px); }
        60% { transform: translateY(-5px); }
    }
    </style>
    """

def admin_login():
    """Login formulár pre admin"""
    st.title("🔐 Admin Login")
    st.write("Zadajte heslo pre prístup k admin panelu:")
    
    with st.form("admin_login_form"):
        password = st.text_input("Heslo:", type="password", placeholder="Zadajte admin heslo")
        submitted = st.form_submit_button("🔓 Prihlásiť sa", type="primary")
        
        if submitted:
            if verify_password(password, ADMIN_PASSWORD_MD5):
                st.session_state.admin_authenticated = True
                st.success("✅ Úspešne prihlásený!")
                st.rerun()
            else:
                st.error("❌ Nesprávne heslo!")
                
    # Debug info pre admin (odkomentuj ak potrebuješ)
    with st.expander("🔧 Debug Info (len pre testovanie)"):
        st.write("**Heslo:** consumertest24")
        if st.button("Zobraziť MD5 hashe"):
            st.code(f"Uložený MD5 hash: {ADMIN_PASSWORD_MD5}")
            if 'password' in locals() and password:
                st.code(f"Zadaný hash: {hash_password(password)}")
    
    st.divider()
    if st.button("👥 Prejsť na hodnotenie"):
        st.session_state.admin_mode = False
        st.rerun()

def admin_interface():
    """Admin rozhranie pre nastavenie hodnotenia"""
    
    # Kontrola autentifikácie
    if not st.session_state.admin_authenticated:
        admin_login()
        return
    
    # Získanie aktuálneho stavu
    current_state = get_current_state()
    
    # Header s možnosťou odhlásenia
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title(f"🔧 Admin Panel - {current_state['session_name']}")
    with col2:
        if st.button("🚪 Odhlásiť sa"):
            st.session_state.admin_authenticated = False
            st.rerun()
    
    with st.container():
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("⚙️ Nastavenie hodnotenia")
            
            # Názov session/akcie
            session_name = st.text_input(
                "📋 Názov hodnotenia/akcie:",
                value=current_state['session_name'],
                placeholder="Napr. Hodnotenie chutnôs letnej ponuky 2024",
                help="Tento názov sa zobrazí v title a pomôže identifikovať akciu"
            )
            
            st.divider()
            
            # Počet vzoriek
            samples_count = st.number_input(
                "🧪 Počet vzoriek na hodnotenie:",
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
            col_btn1, col_btn2, col_btn3 = st.columns(3)
            
            with col_btn1:
                if st.button("💾 Uložiť nastavenia", type="primary"):
                    if save_evaluation_settings(session_name, samples_count, sample_names, True):
                        st.success("✅ Nastavenia uložené do databázy!")
                        st.rerun()
                    else:
                        st.error("❌ Chyba pri ukladaní!")
            
            with col_btn2:
                if st.button("🔄 Reset hodnotení"):
                    if clear_evaluations_for_session(current_state['session_name']):
                        st.success("✅ Hodnotenia vymazané z databázy!")
                        st.rerun()
                    else:
                        st.error("❌ Chyba pri mazaní!")
            
            with col_btn3:
                if st.button("👥 Prepnúť na hodnotenie"):
                    st.session_state.admin_mode = False
                    st.rerun()
        
        with col2:
            if current_state['session_active']:
                st.subheader("📱 QR kód pre hodnotiteľov")
                
                # URL aplikácie na Streamlit Cloud - odkaz na landing page
                app_url = "https://consumervote.streamlit.app"
                landing_url = f"{app_url}?mode=landing&hide_sidebar=true"
                
                # Generovanie QR kódu s optimalizáciou pre vonkajšie podmienky
                qr_image_url = generate_qr_code_url(landing_url, size="250x250", error_correction="H")
                
                # Kontajner pre QR kód
                st.markdown("""
                <div style="background: white; padding: 1rem; border-radius: 12px; text-align: center; margin: 1rem 0; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                """, unsafe_allow_html=True)
                
                st.image(qr_image_url, caption="QR kód pre hodnotenie (optimalizovaný pre vonkajšie podmienky)", width=250)
                
                st.markdown("</div>", unsafe_allow_html=True)
                
                # Tlačidlá pre admin
                col_btn1, col_btn2 = st.columns(2)
                
                with col_btn1:
                    # Tlačidlo na otvorenie landing page
                    st.markdown(f"""
                    <a href="{landing_url}" target="_blank" style="
                        display: inline-block;
                        padding: 0.5rem 1rem;
                        background-color: #2ecc71;
                        color: white;
                        text-decoration: none;
                        border-radius: 0.5rem;
                        margin: 0.5rem 0;
                        text-align: center;
                        width: 100%;
                        box-sizing: border-box;
                    ">🖼️ Otvoriť landing page</a>
                    """, unsafe_allow_html=True)
                
                with col_btn2:
                    # Tlačidlo na priamy vstup do hodnotenia
                    evaluator_url = f"{app_url}?mode=evaluator&hide_sidebar=true"
                    st.markdown(f"""
                    <a href="{evaluator_url}" target="_blank" style="
                        display: inline-block;
                        padding: 0.5rem 1rem;
                        background-color: #ff6b6b;
                        color: white;
                        text-decoration: none;
                        border-radius: 0.5rem;
                        margin: 0.5rem 0;
                        text-align: center;
                        width: 100%;
                        box-sizing: border-box;
                    ">🔗 Priame hodnotenie</a>
                    """, unsafe_allow_html=True)
                
                # Informácie o QR kóde
                st.info("""
                **💡 QR kód vedie na landing page s:**
                - Veľký, čitateľný QR kód aj za slnka
                - Inštrukcie pre hodnotiteľov  
                - Prehľad funkcií aplikácie
                - Priamy odkaz na hodnotenie
                """)
                
                # URL pre kopírovanie
                with st.expander("📋 URL pre kopírovanie"):
                    st.code(landing_url, language="text")
                    st.caption("Landing page - ideálne pre zdieľanie")
                    st.code(evaluator_url, language="text") 
                    st.caption("Priame hodnotenie - pre pokročilých")
    
    # Zobrazenie aktuálnych nastavení
    if current_state['session_active']:
        st.divider()
        st.subheader("📊 Aktuálne nastavenia")
        
        # Session info
        st.info(f"📋 **Aktuálna session:** {current_state['session_name']}")
        
        # Získanie device stats
        device_stats = get_device_stats(current_state['session_name'])
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Počet vzoriek", current_state['samples_count'])
        with col2:
            st.metric("Počet hodnotení", len(current_state['evaluations']))
        with col3:
            st.metric("Jedinečné zariadenia", device_stats['unique_devices'])
        with col4:
            # Veľkosť databázy
            try:
                db_size = os.path.getsize("consumervote.db") / 1024  # KB
                st.metric("Veľkosť DB", f"{db_size:.1f} KB")
            except:
                st.metric("Veľkosť DB", "N/A")
        
        # Device tracking info
        if device_stats['unique_devices'] > 0:
            with st.expander("📱 Device tracking informácie"):
                st.write(f"**Jedinečné zariadenia:** {device_stats['unique_devices']}")
                st.write(f"**Celkové hodnotenia:** {device_stats['total_evaluations']}")
                if device_stats['last_activity']:
                    st.write(f"**Posledná aktivita:** {device_stats['last_activity']}")
                
                # Možnosť reset device tracking
                if st.button("🔄 Reset device tracking", help="Vymaže obmedzenia zariadení - všetky zariadenia budú môcť hodnotiť znovu"):
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
        
        # Zoznam vzoriek
        st.write("**🧪 Vzorky na hodnotenie:**")
        for i, name in enumerate(current_state['samples_names']):
            st.write(f"{i+1}. {name}")
    
    # Zobrazenie výsledkov
    if current_state['evaluations']:
        st.divider()
        st.subheader("📈 Výsledky hodnotenia")
        
        # Export tlačidlá
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📥 Exportovať aktuálnu session (CSV)"):
                df = export_evaluations_to_csv(current_state['session_name'])
                if not df.empty:
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="Stiahnuť CSV aktuálnej session",
                        data=csv,
                        file_name=f"hodnotenia_{current_state['session_name'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
        
        with col2:
            if st.button("🗄️ Exportovať všetky sessions (CSV)"):
                df = export_evaluations_to_csv()
                if not df.empty:
                    csv = df.to_csv(index=False)
                    st.download_button(
                        label="Stiahnuť CSV všetkých sessions",
                        data=csv,
                        file_name=f"hodnotenia_vsetky_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
        
        # Základné zobrazenie
        st.write("**Posledných 10 hodnotení:**")
        df_display = pd.DataFrame(current_state['evaluations'][-10:])
        st.dataframe(df_display, use_container_width=True)

def audit_interface():
    """Rozhranie pre zobrazenie audit logov"""
    
    st.subheader("📋 Audit Log - História aktivít")
    
    # Audit štatistiky
    stats = get_audit_statistics()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Celkom akcií", stats['total_actions'])
    with col2:
        st.metric("Úspešnosť", f"{stats['success_rate']:.1f}%")
    with col3:
        if stats['last_activity']:
            last_activity = datetime.strptime(stats['last_activity'], '%Y-%m-%d %H:%M:%S')
            time_ago = datetime.now() - last_activity
            if time_ago.days > 0:
                time_str = f"{time_ago.days}d"
            elif time_ago.seconds > 3600:
                time_str = f"{time_ago.seconds//3600}h"
            else:
                time_str = f"{time_ago.seconds//60}m"
            st.metric("Posledná aktivita", time_str)
        else:
            st.metric("Posledná aktivita", "N/A")
    with col4:
        admin_session_id, _ = get_admin_session_info()
        st.metric("Session ID", admin_session_id[-8:])
    
    # Filtre pre audit logy
    st.markdown("### 🔍 Filtre")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        action_filter = st.selectbox(
            "Typ akcie:",
            options=['Všetky', 'AUTH_LOGIN', 'AUTH_LOGIN_FAILED', 'SETTINGS_UPDATE', 'DATA_DELETE', 'EVALUATION_SUBMIT'],
            key="audit_action_filter"
        )
    
    with col2:
        # Získanie dostupných session names
        current_state = get_current_state()
        session_options = ['Všetky sessions']
        if current_state['session_name']:
            session_options.append(current_state['session_name'])
        
        session_filter = st.selectbox(
            "Session:",
            options=session_options,
            key="audit_session_filter"
        )
    
    with col3:
        limit = st.number_input(
            "Počet záznamov:",
            min_value=10,
            max_value=200,
            value=50,
            step=10,
            key="audit_limit"
        )
    
    # Získanie audit logov s filtrami
    action_type = None if action_filter == 'Všetky' else action_filter
    session_name = None if session_filter == 'Všetky sessions' else session_filter
    
    audit_logs = get_audit_logs(limit=limit, action_type=action_type, session_name=session_name)
    
    if audit_logs:
        st.markdown("### 📊 Audit záznamy")
        
        # Vytvorenie DataFrame pre lepšie zobrazenie
        audit_data = []
        for log in audit_logs:
            timestamp, admin_session_id, admin_ip, action_type, action_description, session_name, old_values, new_values, affected_records, success, error_message = log
            
            audit_data.append({
                'Čas': timestamp,
                'Admin Session': admin_session_id[-8:] if admin_session_id else 'N/A',
                'IP': admin_ip,
                'Akcia': action_type,
                'Popis': action_description,
                'Session': session_name or 'N/A',
                'Záznamy': affected_records,
                'Úspech': '✅' if success else '❌',
                'Chyba': error_message or ''
            })
        
        df = pd.DataFrame(audit_data)
        
        # Zobrazenie tabuľky
        st.dataframe(df, use_container_width=True, height=400)
        
        # Export audit logov
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📥 Export audit logov (CSV)"):
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Stiahnuť CSV",
                    data=csv,
                    file_name=f"audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
        
        with col2:
            if st.button("🗑️ Vyčistiť staré audit logy (>30 dní)"):
                conn = sqlite3.connect("consumervote.db")
                cursor = conn.cursor()
                try:
                    cursor.execute('''
                        DELETE FROM audit_log 
                        WHERE timestamp < datetime('now', '-30 days')
                    ''')
                    deleted_count = cursor.rowcount
                    conn.commit()
                    
                    # Log čistenia auditov
                    log_audit_action(
                        action_type="AUDIT_CLEANUP",
                        action_description=f"Vyčistené staré audit logy (vymazaných {deleted_count} záznamov)",
                        affected_records=deleted_count,
                        success=True
                    )
                    
                    st.success(f"✅ Vymazaných {deleted_count} starých audit záznamov")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Chyba pri čistení: {e}")
                finally:
                    conn.close()
        
        # Detailné zobrazenie vybraného záznamu
        if st.checkbox("🔍 Zobraziť detaily záznamov"):
            for i, log in enumerate(audit_logs[:10]):  # Zobraz len prvých 10 pre performance
                timestamp, admin_session_id, admin_ip, action_type, action_description, session_name, old_values, new_values, affected_records, success, error_message = log
                
                with st.expander(f"{timestamp} - {action_type} {'✅' if success else '❌'}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Admin Session:** {admin_session_id}")
                        st.write(f"**IP Adresa:** {admin_ip}")
                        st.write(f"**Typ akcie:** {action_type}")
                        st.write(f"**Ovplyvnené záznamy:** {affected_records}")
                    
                    with col2:
                        st.write(f"**Session:** {session_name or 'N/A'}")
                        st.write(f"**Úspech:** {'✅ Áno' if success else '❌ Nie'}")
                        if error_message:
                            st.error(f"**Chyba:** {error_message}")
                    
                    st.write(f"**Popis:** {action_description}")
                    
                    if old_values:
                        try:
                            old_data = json.loads(old_values)
                            st.json({"Staré hodnoty": old_data})
                        except:
                            st.text(f"Staré hodnoty: {old_values}")
                    
                    if new_values:
                        try:
                            new_data = json.loads(new_values)
                            st.json({"Nové hodnoty": new_data})
                        except:
                            st.text(f"Nové hodnoty: {new_values}")
    
    else:
        st.info("📝 Žiadne audit záznamy neboli nájdené pre zadané filtre")
    
    # Najpopulárnejšie akcie
    if stats['popular_actions']:
        st.markdown("### 📈 Najčastejšie akcie")
        popular_df = pd.DataFrame(stats['popular_actions'], columns=['Typ akcie', 'Počet'])
        st.bar_chart(popular_df.set_index('Typ akcie'))

def evaluator_interface():
    """Mobile-first rozhranie pre hodnotiteľov"""
    
    # Aplikuj mobile CSS
    st.markdown(get_mobile_css(), unsafe_allow_html=True)
    # Aplikuj sharing CSS
    st.markdown(get_sharing_qr_css(), unsafe_allow_html=True)
    
    # Získanie aktuálneho stavu
    current_state = get_current_state()
    
    # Mobile optimalizovaný title
    st.markdown(f'<h1 class="mobile-title">🧪 {current_state["session_name"]}</h1>', unsafe_allow_html=True)
    
    if not current_state['session_active']:
        st.markdown("""
        <div class="mobile-info">
            <h3>❌ Hodnotenie nie je aktívne</h3>
            <p>Kontaktujte administrátora pre aktiváciu hodnotenia</p>
        </div>
        """, unsafe_allow_html=True)
        return
    
    # Kontrola device limitu
    device_fingerprint, ip_address, user_agent = get_device_fingerprint()
    can_evaluate, message, eval_count = check_device_limit(
        current_state['session_name'], device_fingerprint, ip_address, user_agent
    )
    
    if not can_evaluate:
        st.markdown(f"""
        <div class="mobile-info">
            <h3>⏰ Príliš skoré hodnotenie</h3>
            <p>{message}</p>
            <small>Každé zariadenie môže hodnotiť len raz za hodinu</small>
        </div>
        """, unsafe_allow_html=True)
        
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
        
        # Aplikuj CSS pre sharing
        st.markdown(get_sharing_qr_css(), unsafe_allow_html=True)
        
        # Ďakovná správa s QR kódom pre sharing
        app_url = "https://consumervote.streamlit.app"
        landing_url = f"{app_url}?mode=landing&hide_sidebar=true"
        
        # QR kód pre sharing - stredná veľkosť, odkazuje na landing page
        sharing_qr_url = generate_qr_code_url(landing_url, size="300x300", error_correction="H")
        
        st.markdown(f"""
        <div class="sharing-container">
            <div class="thank-you-emojis">🎉 🙏 ✨</div>
            <h2 class="sharing-title">Ďakujeme za hodnotenie!</h2>
            <p>Váš názor je pre nás veľmi dôležitý</p>
            
            <div class="sharing-qr pulse-animation">
                <img src="{sharing_qr_url}" alt="QR kód pre zdieľanie" style="max-width: 100%; height: auto;" />
            </div>
            
            <div class="sharing-instructions">
                <h4>📱 Zdieľajte s priateľmi!</h4>
                <p><strong>Ukážte tento QR kód ostatným</strong> - môžu si ho naskenovať z vašej obrazovky</p>
                <p>💡 QR kód funguje aj za denného svetla</p>
                <p>🔄 Stačí jeden scan a môžu hodnotiť aj oni</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.balloons()
        
        # Tlačidlá pre akcie
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 Nové hodnotenie", type="primary", key="new_eval_btn", help="Začať nové hodnotenie"):
                st.session_state.evaluation_submitted = False
                st.session_state.show_confirmation = False
                st.rerun()
        
        with col2:
            # Odkaz na landing page
            st.markdown(f"""
            <a href="{landing_url}" target="_blank" style="
                display: inline-block;
                padding: 0.75rem 1.5rem;
                background-color: #3498db;
                color: white;
                text-decoration: none;
                border-radius: 12px;
                font-weight: 600;
                text-align: center;
                width: 100%;
                box-sizing: border-box;
                margin-top: 0.5rem;
            ">🖼️ Otvoriť landing page</a>
            """, unsafe_allow_html=True)
        
        return
    
    # Krok 1: Hlavný formulár
    if not st.session_state.show_confirmation:
        
        # Inštrukcie
        st.markdown("""
        <div class="mobile-info">
            <h4>📝 Inštrukcie</h4>
            <p>Vyberte TOP 3 vzorky v poradí od najlepšej po tretiu najlepšiu</p>
            <small>💡 Zvyšné vzorky budú automaticky označené ako neklasifikované</small>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown('<div class="mobile-spacing"></div>', unsafe_allow_html=True)
        
        # Meno hodnotiteľa
        st.markdown('<h3 class="mobile-subtitle">👤 Vaše meno</h3>', unsafe_allow_html=True)
        evaluator_name = st.text_input(
            "", 
            placeholder="Zadajte vaše meno alebo prezývku",
            key="eval_name_input",
            label_visibility="collapsed"
        )
        
        st.markdown('<div class="mobile-spacing"></div>', unsafe_allow_html=True)
        
        # TOP 3 výber s mobilnými kartami
        st.markdown('<h3 class="mobile-subtitle">🏆 TOP 3 vzorky</h3>', unsafe_allow_html=True)
        
        # 1. miesto
        st.markdown("### 🥇 1. miesto - Najlepšia vzorka")
        first_place = st.selectbox(
            "",
            options=['Vyberte vzorku...'] + current_state['samples_names'],
            key="first_place_select",
            label_visibility="collapsed"
        )
        if first_place == 'Vyberte vzorku...':
            first_place = None
        
        st.markdown('<div class="mobile-spacing"></div>', unsafe_allow_html=True)
        
        # 2. miesto
        st.markdown("### 🥈 2. miesto - Druhá najlepšia")
        available_for_second = [s for s in current_state['samples_names'] if s != first_place]
        second_place = st.selectbox(
            "",
            options=['Vyberte vzorku...'] + available_for_second,
            key="second_place_select",
            label_visibility="collapsed"
        )
        if second_place == 'Vyberte vzorku...':
            second_place = None
        
        st.markdown('<div class="mobile-spacing"></div>', unsafe_allow_html=True)
        
        # 3. miesto
        st.markdown("### 🥉 3. miesto - Tretia najlepšia")
        available_for_third = [s for s in current_state['samples_names'] 
                              if s != first_place and s != second_place]
        third_place = st.selectbox(
            "",
            options=['Vyberte vzorku...'] + available_for_third,
            key="third_place_select",
            label_visibility="collapsed"
        )
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
        
        # Zobrazenie súhrnu ak niečo vybral
        if selected_samples:
            st.markdown('<div class="mobile-spacing"></div>', unsafe_allow_html=True)
            st.markdown('<h3 class="mobile-subtitle">📋 Váš aktuálny výber</h3>', unsafe_allow_html=True)
            
            for place, sample in selected_samples.items():
                medal = "🥇" if place == "1" else "🥈" if place == "2" else "🥉"
                st.success(f"{medal} **{place}. miesto**: {sample}")
            
            # Zostávajúce vzorky
            remaining = [s for s in current_state['samples_names'] 
                        if s not in selected_samples.values()]
            if remaining:
                with st.expander("📝 Neklasifikované vzorky"):
                    for sample in remaining:
                        st.write(f"• {sample}")
        
        st.markdown('<div class="mobile-spacing"></div>', unsafe_allow_html=True)
        
        # Komentár
        st.markdown('<h3 class="mobile-subtitle">💬 Komentár (voliteľný)</h3>', unsafe_allow_html=True)
        comment = st.text_area(
            "", 
            placeholder="Váš komentár k hodnoteniu, poznámky, návrhy na zlepšenie...",
            key="eval_comment_input",
            label_visibility="collapsed",
            height=120
        )
        
        st.markdown('<div class="mobile-spacing"></div>', unsafe_allow_html=True)
        
        # Tlačidlo pokračovať
        if st.button("📤 Pokračovať na kontrolu", type="primary", key="continue_btn", use_container_width=True):
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
        st.markdown('<h3 class="mobile-subtitle">✅ Kontrola hodnotenia</h3>', unsafe_allow_html=True)
        
        temp_eval = st.session_state.temp_evaluation
        
        # Prehľadné zobrazenie pre mobile
        st.markdown(f"""
        <div class="mobile-info">
            <h4>👤 {temp_eval['evaluator_name']}</h4>
            <p><strong>Session:</strong> {temp_eval['session_name']}</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown('<div class="mobile-spacing"></div>', unsafe_allow_html=True)
        
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
            st.markdown('<div class="mobile-spacing"></div>', unsafe_allow_html=True)
            st.info(f"**Komentár:** {temp_eval['comment']}")
        
        st.markdown('<div class="mobile-spacing"></div>', unsafe_allow_html=True)
        
        # Akčné tlačidlá pre mobile
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("✅ Potvrdiť", type="primary", key="confirm_btn", use_container_width=True):
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
                if save_evaluation(
                    temp_eval['session_name'],
                    temp_eval['evaluator_name'], 
                    evaluation_data, 
                    temp_eval['comment']
                ):
                    # Aktualizácia device tracking
                    update_device_tracking(
                        temp_eval['session_name'],
                        temp_eval['device_fingerprint'],
                        temp_eval['ip_address'],
                        temp_eval['user_agent']
                    )
                    
                    st.session_state.evaluation_submitted = True
                    st.session_state.show_confirmation = False
                    if 'temp_evaluation' in st.session_state:
                        del st.session_state.temp_evaluation
                    st.rerun()
                else:
                    st.error("❌ Chyba pri ukladaní do databázy!")
        
        with col2:
            if st.button("❌ Späť", key="back_btn", use_container_width=True):
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
    
    # Získanie aktuálneho stavu
    current_state = get_current_state()
    
    # Ak je force landing mode, zobraz landing page
    if force_landing:
        landing_page_interface()
        return
    
    # Ak je evaluator mode alebo hide_sidebar, zobraz evaluator
    if hide_sidebar or force_evaluator:
        st.session_state.admin_mode = False
        evaluator_interface()
        return
    
    # Sidebar pre navigáciu
    with st.sidebar:
        st.title("🧪 Hodnotenie vzoriek")
        
        # Zobrazenie aktuálnej session
        if current_state['session_active']:
            st.success(f"📋 **{current_state['session_name']}**")
        
        if st.session_state.admin_authenticated:
            st.success("✅ Admin prihlásený")
        else:
            st.info("🔐 Admin neprihlásený")
        
        mode = st.radio(
            "Vyberte režim:",
            ["👥 Hodnotiteľ", "🔧 Administrátor"],
            index=1 if st.session_state.admin_mode else 0
        )
        
        st.session_state.admin_mode = (mode == "🔧 Administrátor")
        
        st.divider()
        
        # Informácie o aktuálnej session
        if current_state['session_active']:
            st.subheader("📊 Aktuálna session")
            st.metric("Vzorky", current_state['samples_count'])
            st.metric("Hodnotenia", len(current_state['evaluations']))
            
            # Rýchly prístup k landing page
            app_url = "https://consumervote.streamlit.app"
            landing_url = f"{app_url}?mode=landing&hide_sidebar=true"
            
            st.markdown("**🔗 Rýchly prístup:**")
            st.markdown(f"""
            <a href="{landing_url}" target="_blank" style="
                display: inline-block;
                padding: 0.4rem 0.8rem;
                background-color: #3498db;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-size: 0.9rem;
                margin: 0.2rem 0;
                text-align: center;
                width: 100%;
                box-sizing: border-box;
            ">🖼️ Landing page</a>
            """, unsafe_allow_html=True)
            
        else:
            st.warning("⚠️ Hodnotenie nie je nastavené")
        
        # Database info
        st.divider()
        st.subheader("🗄️ Databáza")
        try:
            if os.path.exists("consumervote.db"):
                db_size = os.path.getsize("consumervote.db") / 1024
                st.write(f"📊 Veľkosť: {db_size:.1f} KB")
                st.success("✅ SQLite pripojená")
            else:
                st.warning("⚠️ DB sa inicializuje...")
        except:
            st.error("❌ Problém s DB")
        
        if st.session_state.admin_authenticated:
            st.divider()
            if st.button("🚪 Rýchle odhlásenie", use_container_width=True):
                st.session_state.admin_authenticated = False
                st.session_state.admin_mode = False
                st.rerun()
    
    if st.session_state.admin_mode:
        admin_interface()
    else:
        evaluator_interface()

if __name__ == "__main__":
    main()