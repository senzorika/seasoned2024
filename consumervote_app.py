import streamlit as st
import pandas as pd
import json
from datetime import datetime
import uuid
import urllib.parse

# Nastavenie stránky
st.set_page_config(
    page_title="Hodnotenie vzoriek",
    page_icon="🧪",
    layout="wide"
)

# Jednoduchší globálny stav pomocou st.cache_data
@st.cache_data
def init_global_state():
    """Inicializuje globálny stav"""
    return {
        'session_active': False,
        'samples_count': 0,
        'samples_names': [],
        'evaluations': [],
        'session_id': str(uuid.uuid4())[:8]
    }

def get_current_state():
    """Získa aktuálny stav"""
    if 'global_state' not in st.session_state:
        st.session_state.global_state = init_global_state()
    return st.session_state.global_state

def update_global_state(new_state):
    """Aktualizuje globálny stav"""
    st.session_state.global_state = new_state
    # Vyčistenie cache aby sa načítal nový stav
    init_global_state.clear()

# Inicializácia session state pre admin mode
if 'admin_mode' not in st.session_state:
    st.session_state.admin_mode = False
if 'admin_authenticated' not in st.session_state:
    st.session_state.admin_authenticated = False

# Admin heslo
ADMIN_PASSWORD = "consumertest24"

def get_query_params():
    """Získa URL parametre kompatibilne s rôznymi verziami Streamlit"""
    try:
        # Nová verzia Streamlit
        return st.query_params
    except:
        try:
            # Stará verzia Streamlit
            return st.experimental_get_query_params()
        except:
            return {}

def admin_login():
    """Login formulár pre admin"""
    st.title("🔐 Admin Login")
    st.write("Zadajte heslo pre prístup k admin panelu:")
    
    with st.form("admin_login_form"):
        password = st.text_input("Heslo:", type="password", placeholder="Zadajte admin heslo")
        submitted = st.form_submit_button("🔓 Prihlásiť sa", type="primary")
        
        if submitted:
            if password == ADMIN_PASSWORD:
                st.session_state.admin_authenticated = True
                st.success("✅ Úspešne prihlásený!")
                st.rerun()
            else:
                st.error("❌ Nesprávne heslo!")
    
    st.divider()
    if st.button("👥 Prejsť na hodnotenie"):
        st.session_state.admin_mode = False
        st.rerun()

def generate_qr_code_url(url):
    """Generuje URL pre QR kód pomocou online služby"""
    # Enkódovanie URL pre QR kód
    encoded_url = urllib.parse.quote(url, safe='')
    # Použitie bezplatnej QR kód služby
    qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={encoded_url}"
    return qr_api_url



def admin_interface():
    """Admin rozhranie pre nastavenie hodnotenia"""
    
    # Kontrola autentifikácie
    if not st.session_state.admin_authenticated:
        admin_login()
        return
    
    # Header s možnosťou odhlásenia
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("🔧 Admin Panel - Nastavenie hodnotenia vzoriek")
    with col2:
        if st.button("🚪 Odhlásiť sa"):
            st.session_state.admin_authenticated = False
            st.rerun()
    
    # Získanie aktuálneho stavu
    current_state = get_current_state()
    
    with st.container():
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("Nastavenie vzoriek")
            
            # Počet vzoriek
            samples_count = st.number_input(
                "Počet vzoriek na hodnotenie:",
                min_value=2,
                max_value=20,
                value=current_state['samples_count'] if current_state['samples_count'] > 0 else 3
            )
            
            # Názvy vzoriek
            st.write("**Názvy vzoriek:**")
            sample_names = []
            
            for i in range(samples_count):
                name = st.text_input(
                    f"Vzorka {i+1}:",
                    value=current_state['samples_names'][i] if i < len(current_state['samples_names']) else f"Vzorka {i+1}",
                    key=f"sample_name_{i}"
                )
                sample_names.append(name)
            
            # Tlačidlá
            col_btn1, col_btn2, col_btn3 = st.columns(3)
            
            with col_btn1:
                if st.button("💾 Uložiť nastavenia", type="primary"):
                    new_state = current_state.copy()
                    new_state['samples_count'] = samples_count
                    new_state['samples_names'] = sample_names
                    new_state['session_active'] = True
                    update_global_state(new_state)
                    st.success("✅ Nastavenia uložené!")
                    st.rerun()
            
            with col_btn2:
                if st.button("🔄 Reset hodnotení"):
                    new_state = current_state.copy()
                    new_state['evaluations'] = []
                    update_global_state(new_state)
                    st.success("✅ Hodnotenia resetované!")
                    st.rerun()
            
            with col_btn3:
                if st.button("👥 Prepnúť na hodnotenie"):
                    st.session_state.admin_mode = False
                    st.rerun()
        
        with col2:
            if current_state['session_active']:
                st.subheader("📱 QR kód pre hodnotiteľov")
                
                # Fixná URL aplikácie na Streamlit Cloud
                app_url = "https://consumervote.streamlit.app"
                evaluator_url = f"{app_url}/?mode=evaluator&hide_sidebar=true"
                
                # Generovanie a zobrazenie QR kódu
                qr_image_url = generate_qr_code_url(evaluator_url)
                st.image(qr_image_url, caption="Naskenujte pre hodnotenie", width=200)
                
                # Tlačidlo na otvorenie v novom okne
                st.markdown(f"""
                <a href="{evaluator_url}" target="_blank" style="
                    display: inline-block;
                    padding: 0.5rem 1rem;
                    background-color: #ff4b4b;
                    color: white;
                    text-decoration: none;
                    border-radius: 0.5rem;
                    margin: 0.5rem 0;
                ">🔗 Otvoriť hodnotenie v novom okne</a>
                """, unsafe_allow_html=True)
                
                st.code(evaluator_url, language="text")
                st.caption("💡 Hodnotitelia môžu použiť QR kód alebo odkaz")
    
    # Zobrazenie aktuálnych nastavení
    if current_state['session_active']:
        st.divider()
        st.subheader("📊 Aktuálne nastavenia")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Počet vzoriek", current_state['samples_count'])
        with col2:
            st.metric("Počet hodnotení", len(current_state['evaluations']))
        
        # Zoznam vzoriek
        st.write("**Vzorky na hodnotenie:**")
        for i, name in enumerate(current_state['samples_names']):
            st.write(f"{i+1}. {name}")
    
    # Zobrazenie výsledkov
    if current_state['evaluations']:
        st.divider()
        st.subheader("📈 Výsledky hodnotenia")
        
        # Konverzia na DataFrame s popisnými hodnotami
        df_raw = pd.DataFrame(current_state['evaluations'])
        df_display = df_raw.copy()
        
        # Nahradenie číselných hodnôt popisnými pre lepšie zobrazenie
        for col in df_display.columns:
            if col.startswith('poradie_'):
                df_display[col] = df_display[col].replace({
                    1: '🥇 1. miesto',
                    2: '🥈 2. miesto', 
                    3: '🥉 3. miesto',
                    999: '❌ Neklasifikované'
                })
        
        # Základné štatistiky
        st.write("**Prehľad hodnotení:**")
        st.dataframe(df_display, use_container_width=True)
        
        # Súhrn výsledkov
        st.subheader("🏆 Súhrn výsledkov")
        
        # Analýza pre každú vzorku
        summary_data = []
        for sample_name in current_state['samples_names']:
            col_name = f'poradie_{sample_name}'
            if col_name in df_raw.columns:
                rankings = df_raw[col_name].tolist()
                first_places = rankings.count(1)
                second_places = rankings.count(2)
                third_places = rankings.count(3)
                unranked = rankings.count(999)
                
                summary_data.append({
                    'Vzorka': sample_name,
                    '🥇 1. miesta': first_places,
                    '🥈 2. miesta': second_places,
                    '🥉 3. miesta': third_places,
                    '❌ Neklasifikované': unranked
                })
        
        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df, use_container_width=True)
        
        # Export
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📥 Exportovať podrobné výsledky (CSV)"):
                csv = df_raw.to_csv(index=False)
                st.download_button(
                    label="Stiahnuť podrobné CSV",
                    data=csv,
                    file_name=f"hodnotenia_podrobne_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
        
        with col2:
            if st.button("📊 Exportovať súhrn (CSV)"):
                csv_summary = summary_df.to_csv(index=False)
                st.download_button(
                    label="Stiahnuť súhrn CSV",
                    data=csv_summary,
                    file_name=f"hodnotenia_suhrn_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )

def evaluator_interface():
    """Rozhranie pre hodnotiteľov"""
    
    # Získanie aktuálneho stavu
    current_state = get_current_state()
    
    st.title("🧪 Hodnotenie vzoriek")
    
    if not current_state['session_active']:
        st.error("❌ Hodnotenie nie je aktívne. Kontaktujte administrátora.")
        return
    
    st.write("**Vyberte TOP 3 vzorky v poradí od najlepšej po tretiu najlepšiu**")
    st.info("💡 Vyberte len 3 najlepšie vzorky - zostatok bude automaticky označený ako neklasifikovaný")
    
    # Inicializácia stavu
    if 'show_confirmation' not in st.session_state:
        st.session_state.show_confirmation = False
    if 'evaluation_submitted' not in st.session_state:
        st.session_state.evaluation_submitted = False
    
    # Ak bolo hodnotenie úspešne odoslané, zobraz správu a reset
    if st.session_state.evaluation_submitted:
        st.success("✅ Hodnotenie bolo úspešne odoslané!")
        st.balloons()
        
        if st.button("🔄 Nové hodnotenie", type="primary"):
            st.session_state.evaluation_submitted = False
            st.session_state.show_confirmation = False
            st.rerun()
        return
    
    # Hlavný formulár (zobrazuje sa len ak nie je potvrdzovacie okno)
    if not st.session_state.show_confirmation:
        
        # Formulár pre meno hodnotiteľa
        with st.container():
            st.subheader("👤 Informácie o hodnotiteľovi")
            evaluator_name = st.text_input(
                "Meno hodnotiteľa:", 
                placeholder="Zadajte vaše meno",
                key="eval_name_input"
            )
        
        # Výber TOP 3 vzoriek
        st.subheader("🏆 Vyberte TOP 3 vzorky")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("### 🥇 1. miesto")
            first_place = st.selectbox(
                "Najlepšia vzorka:",
                options=[''] + current_state['samples_names'],
                key="first_place_select"
            )
        
        with col2:
            st.markdown("### 🥈 2. miesto")
            available_for_second = [s for s in current_state['samples_names'] if s != first_place]
            second_place = st.selectbox(
                "Druhá najlepšia vzorka:",
                options=[''] + available_for_second,
                key="second_place_select"
            )
        
        with col3:
            st.markdown("### 🥉 3. miesto")
            available_for_third = [s for s in current_state['samples_names'] 
                                  if s != first_place and s != second_place]
            third_place = st.selectbox(
                "Tretia najlepšia vzorka:",
                options=[''] + available_for_third,
                key="third_place_select"
            )
        
        # Zobrazenie súhrnu výberu
        selected_samples = {}
        if first_place:
            selected_samples['1'] = first_place
        if second_place:
            selected_samples['2'] = second_place
        if third_place:
            selected_samples['3'] = third_place
            
        if selected_samples:
            st.divider()
            st.subheader("📋 Váš výber:")
            
            for place, sample in selected_samples.items():
                medal = "🥇" if place == "1" else "🥈" if place == "2" else "🥉"
                st.write(f"{medal} **{place}. miesto**: {sample}")
            
            # Zostávajúce vzorky
            remaining = [s for s in current_state['samples_names'] 
                        if s not in selected_samples.values()]
            if remaining:
                st.write(f"📝 **Neklasifikované vzorky**: {', '.join(remaining)}")
        
        # Komentár
        st.divider()
        comment = st.text_area(
            "💬 Komentár (voliteľný):", 
            placeholder="Váš komentár k hodnoteniu...",
            key="eval_comment_input"
        )
        
        # Tlačidlo na pokračovanie
        if st.button("📤 Pokračovať na potvrdenie", type="primary", use_container_width=True):
            # Validácia
            if not evaluator_name.strip():
                st.error("❌ Prosím zadajte vaše meno!")
            elif not selected_samples:
                st.error("❌ Prosím vyberte aspoň jednu vzorku!")
            else:
                # Uloženie do session state
                st.session_state.temp_evaluation = {
                    'evaluator_name': evaluator_name,
                    'selected_samples': selected_samples,
                    'comment': comment
                }
                st.session_state.show_confirmation = True
                st.rerun()
    
    # Potvrdzovacie okno
    else:
        st.markdown("---")
        st.markdown("### ✅ Potvrdenie hodnotenia")
        
        temp_eval = st.session_state.temp_evaluation
        
        st.write(f"**Hodnotiteľ**: {temp_eval['evaluator_name']}")
        
        for place, sample in temp_eval['selected_samples'].items():
            medal = "🥇" if place == "1" else "🥈" if place == "2" else "🥉"
            st.write(f"{medal} **{place}. miesto**: {sample}")
        
        if temp_eval['comment']:
            st.write(f"**Komentár**: {temp_eval['comment']}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("✅ Potvrdiť a odoslať", type="primary", use_container_width=True):
                # Uloženie hodnotenia
                evaluation = {
                    'hodnotiteľ': temp_eval['evaluator_name'],
                    'čas': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'komentár': temp_eval['comment'],
                    'id': str(uuid.uuid4())[:8]
                }
                
                # Pridanie hodnotení pre všetky vzorky
                for sample_name in current_state['samples_names']:
                    if sample_name == temp_eval['selected_samples'].get('1'):
                        evaluation[f'poradie_{sample_name}'] = 1
                    elif sample_name == temp_eval['selected_samples'].get('2'):
                        evaluation[f'poradie_{sample_name}'] = 2
                    elif sample_name == temp_eval['selected_samples'].get('3'):
                        evaluation[f'poradie_{sample_name}'] = 3
                    else:
                        evaluation[f'poradie_{sample_name}'] = 999  # Neklasifikované
                
                # Aktualizácia globálneho stavu
                new_state = current_state.copy()
                new_state['evaluations'].append(evaluation)
                update_global_state(new_state)
                
                # Nastavenie príznaku úspešného odoslania
                st.session_state.evaluation_submitted = True
                st.session_state.show_confirmation = False
                
                # Vyčistenie dočasných dát
                if 'temp_evaluation' in st.session_state:
                    del st.session_state.temp_evaluation
                
                st.rerun()
        
        with col2:
            if st.button("❌ Späť na formulár", use_container_width=True):
                st.session_state.show_confirmation = False
                st.rerun()

def main():
    """Hlavná funkcia aplikácie"""
    
    # Kontrola URL parametrov s kompatibilitou
    query_params = get_query_params()
    
    # Spracovanie parametrov pre rôzne formáty
    hide_sidebar = False
    if 'hide_sidebar' in query_params:
        hide_sidebar_value = query_params['hide_sidebar']
        if isinstance(hide_sidebar_value, list):
            hide_sidebar = hide_sidebar_value[0] == 'true'
        else:
            hide_sidebar = hide_sidebar_value == 'true'
    
    # Nastavenie evaluator mode ak je v URL
    if 'mode' in query_params:
        mode_value = query_params['mode']
        if isinstance(mode_value, list):
            mode_value = mode_value[0]
        if mode_value == 'evaluator':
            st.session_state.admin_mode = False
    
    # Debug info pre testovanie
    if query_params:
        st.sidebar.write("🔍 Debug URL params:", query_params)
    
    # Získanie aktuálneho stavu
    current_state = get_current_state()
    
    # Ak je sidebar skrytý, force evaluator mode a nie je možné prepnúť
    if hide_sidebar:
        st.session_state.admin_mode = False
        # Skryť sidebar CSS
        st.markdown("""
        <style>
        .css-1d391kg {display: none}
        .css-1rs6os {display: none}
        .css-17eq0hr {display: none}
        </style>
        """, unsafe_allow_html=True)
        evaluator_interface()
        return
    
    # Sidebar pre navigáciu (len pre admin)
    with st.sidebar:
        st.title("🧪 Hodnotenie vzoriek")
        
        # Zobrazenie stavu autentifikácie
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
        
        # Informácie o aplikácii
        st.subheader("ℹ️ O aplikácii")
        st.write("Aplikácia na hodnotenie vzoriek v poradí.")
        
        if current_state['session_active']:
            st.success(f"✅ Aktívne hodnotenie\n{current_state['samples_count']} vzoriek")
            st.success(f"📊 {len(current_state['evaluations'])} hodnotení")
        else:
            st.warning("⚠️ Hodnotenie nie je nastavené")
        
        # Rýchle odhlásenie ak je prihlásený
        if st.session_state.admin_authenticated:
            st.divider()
            if st.button("🚪 Rýchle odhlásenie", use_container_width=True):
                st.session_state.admin_authenticated = False
                st.session_state.admin_mode = False
                st.rerun()
    
    # Zobrazenie príslušného rozhrania
    if st.session_state.admin_mode:
        admin_interface()
    else:
        evaluator_interface()

if __name__ == "__main__":
    main()