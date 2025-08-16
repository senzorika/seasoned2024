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
    
    # CSS pre popup styling
    st.markdown("""
    <style>
    .sample-button {
        display: inline-block;
        padding: 1rem;
        margin: 0.5rem;
        background-color: #f0f2f6;
        border: 2px solid #ddd;
        border-radius: 10px;
        text-align: center;
        cursor: pointer;
        transition: all 0.3s;
        min-width: 150px;
    }
    .sample-button:hover {
        background-color: #e1e5eb;
        border-color: #ff4b4b;
    }
    .selected-1 {
        background-color: #ffd700 !important;
        border-color: #ffb000 !important;
        color: #000;
    }
    .selected-2 {
        background-color: #c0c0c0 !important;
        border-color: #a0a0a0 !important;
        color: #000;
    }
    .selected-3 {
        background-color: #cd7f32 !important;
        border-color: #b8722c !important;
        color: #fff;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Inicializácia stavu pre výber
    if 'selected_samples' not in st.session_state:
        st.session_state.selected_samples = {'1': None, '2': None, '3': None}
    if 'evaluator_name' not in st.session_state:
        st.session_state.evaluator_name = ''
    if 'evaluator_comment' not in st.session_state:
        st.session_state.evaluator_comment = ''
    
    # Formulár pre meno hodnotiteľa
    with st.container():
        st.subheader("👤 Informácie o hodnotiteľovi")
        evaluator_name = st.text_input(
            "Meno hodnotiteľa:", 
            value=st.session_state.evaluator_name,
            placeholder="Zadajte vaše meno",
            key="eval_name_input"
        )
        st.session_state.evaluator_name = evaluator_name
    
    # Výber TOP 3 vzoriek
    st.subheader("🏆 Vyberte TOP 3 vzorky")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("### 🥇 1. miesto")
        first_place = st.selectbox(
            "Najlepšia vzorka:",
            options=[''] + current_state['samples_names'],
            index=0 if st.session_state.selected_samples['1'] is None else current_state['samples_names'].index(st.session_state.selected_samples['1']) + 1,
            key="first_place_select"
        )
        if first_place:
            st.session_state.selected_samples['1'] = first_place
        else:
            st.session_state.selected_samples['1'] = None
    
    with col2:
        st.markdown("### 🥈 2. miesto")
        available_for_second = [s for s in current_state['samples_names'] if s != st.session_state.selected_samples['1']]
        second_place = st.selectbox(
            "Druhá najlepšia vzorka:",
            options=[''] + available_for_second,
            index=0 if st.session_state.selected_samples['2'] is None or st.session_state.selected_samples['2'] not in available_for_second 
            else available_for_second.index(st.session_state.selected_samples['2']) + 1,
            key="second_place_select"
        )
        if second_place:
            st.session_state.selected_samples['2'] = second_place
        else:
            st.session_state.selected_samples['2'] = None
    
    with col3:
        st.markdown("### 🥉 3. miesto")
        available_for_third = [s for s in current_state['samples_names'] 
                              if s != st.session_state.selected_samples['1'] and s != st.session_state.selected_samples['2']]
        third_place = st.selectbox(
            "Tretia najlepšia vzorka:",
            options=[''] + available_for_third,
            index=0 if st.session_state.selected_samples['3'] is None or st.session_state.selected_samples['3'] not in available_for_third
            else available_for_third.index(st.session_state.selected_samples['3']) + 1,
            key="third_place_select"
        )
        if third_place:
            st.session_state.selected_samples['3'] = third_place
        else:
            st.session_state.selected_samples['3'] = None
    
    # Zobrazenie súhrnu výberu
    if any(st.session_state.selected_samples.values()):
        st.divider()
        st.subheader("📋 Vaš výber:")
        
        for place, sample in st.session_state.selected_samples.items():
            if sample:
                medal = "🥇" if place == "1" else "🥈" if place == "2" else "🥉"
                st.write(f"{medal} **{place}. miesto**: {sample}")
        
        # Zostávajúce vzorky
        remaining = [s for s in current_state['samples_names'] 
                    if s not in st.session_state.selected_samples.values()]
        if remaining:
            st.write(f"📝 **Neklasifikované vzorky**: {', '.join(remaining)}")
    
    # Komentár
    st.divider()
    comment = st.text_area(
        "💬 Komentár (voliteľný):", 
        value=st.session_state.evaluator_comment,
        placeholder="Váš komentár k hodnoteniu...",
        key="eval_comment_input"
    )
    st.session_state.evaluator_comment = comment
    
    # Modal dialog pre potvrdenie
    if st.button("📤 Odoslať hodnotenie", type="primary", use_container_width=True):
        # Validácia
        if not evaluator_name.strip():
            st.error("❌ Prosím zadajte vaše meno!")
        elif not any(st.session_state.selected_samples.values()):
            st.error("❌ Prosím vyberte aspoň jednu vzorku!")
        else:
            # Modal pre potvrdenie
            with st.container():
                st.markdown("---")
                st.markdown("### ✅ Potvrdenie hodnotenia")
                st.write(f"**Hodnotiteľ**: {evaluator_name}")
                
                for place, sample in st.session_state.selected_samples.items():
                    if sample:
                        medal = "🥇" if place == "1" else "🥈" if place == "2" else "🥉"
                        st.write(f"{medal} **{place}. miesto**: {sample}")
                
                if comment:
                    st.write(f"**Komentár**: {comment}")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("✅ Potvrdiť a odoslať", type="primary", use_container_width=True):
                        # Uloženie hodnotenia
                        evaluation = {
                            'hodnotiteľ': evaluator_name,
                            'čas': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'komentár': comment,
                            'id': str(uuid.uuid4())[:8]
                        }
                        
                        # Pridanie hodnotení pre všetky vzorky
                        for sample_name in current_state['samples_names']:
                            if sample_name == st.session_state.selected_samples['1']:
                                evaluation[f'poradie_{sample_name}'] = 1
                            elif sample_name == st.session_state.selected_samples['2']:
                                evaluation[f'poradie_{sample_name}'] = 2
                            elif sample_name == st.session_state.selected_samples['3']:
                                evaluation[f'poradie_{sample_name}'] = 3
                            else:
                                evaluation[f'poradie_{sample_name}'] = 999  # Neklasifikované
                        
                        # Aktualizácia globálneho stavu
                        new_state = current_state.copy()
                        new_state['evaluations'].append(evaluation)
                        save_global_state(new_state)
                        
                        # Reset formulára
                        st.session_state.selected_samples = {'1': None, '2': None, '3': None}
                        st.session_state.evaluator_name = ''
                        st.session_state.evaluator_comment = ''
                        
                        st.success("✅ Hodnotenie bolo úspešne odoslané!")
                        st.balloons()
                        st.rerun()
                
                with col2:
                    if st.button("❌ Zrušiť", use_container_width=True):
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
    
    # Ak je sidebar skrytý, force evaluator mode a nie je možné prepnúť
    if hide_sidebar:
        st.session_state.admin_mode = False
        evaluator_interface()
        return
    
    # Sidebar pre navigáciu (len pre admin)
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
    
    # Zobrazenie príslušného rozhrania
    if st.session_state.admin_mode:
        admin_interface()
    else:
        evaluator_interface()

if __name__ == "__main__":
    main()