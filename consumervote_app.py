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

# Globálne cache pre zdieľanie dát medzi sessions
@st.cache_data
def get_global_state():
    """Získa globálny stav aplikácie"""
    return {
        'session_active': False,
        'samples_count': 0,
        'samples_names': [],
        'evaluations': [],
        'session_id': str(uuid.uuid4())[:8]
    }

@st.cache_data
def update_global_state(new_state):
    """Aktualizuje globálny stav aplikácie"""
    return new_state

def get_current_state():
    """Získa aktuálny stav - buď z cache alebo vytvorí nový"""
    try:
        return st.session_state.global_state
    except:
        st.session_state.global_state = get_global_state()
        return st.session_state.global_state

def save_global_state(state):
    """Uloží stav globálne"""
    st.session_state.global_state = state
    # Clear cache a nastaviť nový
    get_global_state.clear()
    update_global_state.clear()
    update_global_state(state)

# Inicializácia session state pre admin mode
if 'admin_mode' not in st.session_state:
    st.session_state.admin_mode = False

def generate_qr_code_url(url):
    """Generuje URL pre QR kód pomocou online služby"""
    # Enkódovanie URL pre QR kód
    encoded_url = urllib.parse.quote(url, safe='')
    # Použitie bezplatnej QR kód služby
    qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={encoded_url}"
    return qr_api_url



def admin_interface():
    """Admin rozhranie pre nastavenie hodnotenia"""
    st.title("🔧 Admin Panel - Nastavenie hodnotenia vzoriek")
    
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
                    save_global_state(new_state)
                    st.success("✅ Nastavenia uložené!")
                    st.rerun()
            
            with col_btn2:
                if st.button("🔄 Reset hodnotení"):
                    new_state = current_state.copy()
                    new_state['evaluations'] = []
                    save_global_state(new_state)
                    st.success("✅ Hodnotenia resetované!")
                    st.rerun()
            
            with col_btn3:
                if st.button("👥 Prepnúť na hodnotenie"):
                    st.session_state.admin_mode = False
                    st.rerun()
        
        with col2:
            if current_state['session_active']:
                st.subheader("📱 QR kód pre hodnotiteľov")
                
                # URL aplikácie na Streamlit Cloud
                app_url = "https://consumervote.streamlit.app"
                evaluator_url = f"{app_url}?mode=evaluator&hide_sidebar=true"
                
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
        
        # Konverzia na DataFrame
        df = pd.DataFrame(current_state['evaluations'])
        
        # Základné štatistiky
        st.write("**Prehľad hodnotení:**")
        st.dataframe(df)
        
        # Export
        if st.button("📥 Exportovať výsledky (CSV)"):
            csv = df.to_csv(index=False)
            st.download_button(
                label="Stiahnuť CSV",
                data=csv,
                file_name=f"hodnotenia_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )

def evaluator_interface():
    """Rozhranie pre hodnotiteľov"""
    
    # Skontrolovať či sa má skryť sidebar
    query_params = st.query_params
    hide_sidebar = 'hide_sidebar' in query_params and query_params['hide_sidebar'] == 'true'
    
    # Získanie aktuálneho stavu
    current_state = get_current_state()
    
    st.title("🧪 Hodnotenie vzoriek")
    
    if not current_state['session_active']:
        st.error("❌ Hodnotenie nie je aktívne. Kontaktujte administrátora.")
        if not hide_sidebar:
            if st.button("🔧 Prejsť na admin panel"):
                st.session_state.admin_mode = True
                st.rerun()
        return
    
    st.write("Usporiadajte vzorky podľa vašich preferencií (1 = najlepšia, 2 = druhá najlepšia, atď.)")
    
    with st.form("evaluation_form"):
        st.subheader("📝 Hodnotenie")
        
        # Informácie o hodnotiteľovi
        evaluator_name = st.text_input("Meno hodnotiteľa:", placeholder="Zadajte vaše meno")
        
        # Hodnotenie vzoriek
        rankings = {}
        
        for i, sample_name in enumerate(current_state['samples_names']):
            ranking = st.selectbox(
                f"Poradie pre {sample_name}:",
                options=list(range(1, current_state['samples_count'] + 1)),
                key=f"ranking_{i}"
            )
            rankings[sample_name] = ranking
        
        # Voliteľný komentár
        comment = st.text_area("Komentár (voliteľný):", placeholder="Váš komentár k hodnoteniu...")
        
        # Tlačidlo na odoslanie
        submitted = st.form_submit_button("📤 Odoslať hodnotenie", type="primary")
        
        if submitted:
            if not evaluator_name.strip():
                st.error("❌ Prosím zadajte vaše meno!")
            else:
                # Kontrola, že každé poradie je jedinečné
                ranking_values = list(rankings.values())
                if len(set(ranking_values)) != len(ranking_values):
                    st.error("❌ Každá vzorka musí mať jedinečné poradie!")
                else:
                    # Uloženie hodnotenia
                    evaluation = {
                        'hodnotiteľ': evaluator_name,
                        'čas': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'komentár': comment,
                        'id': str(uuid.uuid4())[:8]
                    }
                    
                    # Pridanie hodnotení pre jednotlivé vzorky
                    for sample_name, ranking in rankings.items():
                        evaluation[f'poradie_{sample_name}'] = ranking
                    
                    # Aktualizácia globálneho stavu
                    new_state = current_state.copy()
                    new_state['evaluations'].append(evaluation)
                    save_global_state(new_state)
                    
                    st.success("✅ Hodnotenie bolo úspešne odoslané!")
                    st.balloons()
                    
                    # Zobrazenie súhrnu
                    st.subheader("📋 Vaše hodnotenie:")
                    for sample_name, ranking in rankings.items():
                        st.write(f"**{sample_name}**: {ranking}. miesto")
                    
                    if comment:
                        st.write(f"**Komentár**: {comment}")
    
    # Tlačidlo pre admin len ak nie je skrytý sidebar
    if not hide_sidebar:
        st.divider()
        if st.button("🔧 Admin panel"):
            st.session_state.admin_mode = True
            st.rerun()

def main():
    """Hlavná funkcia aplikácie"""
    
    # Kontrola URL parametrov
    query_params = st.query_params
    hide_sidebar = 'hide_sidebar' in query_params and query_params['hide_sidebar'] == 'true'
    
    if 'mode' in query_params and query_params['mode'] == 'evaluator':
        st.session_state.admin_mode = False
    
    # Získanie aktuálneho stavu
    current_state = get_current_state()
    
    # Sidebar pre navigáciu (len ak nie je skrytý)
    if not hide_sidebar:
        with st.sidebar:
            st.title("🧪 Hodnotenie vzoriek")
            
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
    
    # Ak je sidebar skrytý, force evaluator mode
    if hide_sidebar:
        st.session_state.admin_mode = False
    
    # Zobrazenie príslušného rozhrania
    if st.session_state.admin_mode:
        admin_interface()
    else:
        evaluator_interface()

if __name__ == "__main__":
    main()