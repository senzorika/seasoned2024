import streamlit as st
import pandas as pd
import json
from datetime import datetime
import uuid

# Nastavenie stránky
st.set_page_config(
    page_title="Hodnotenie vzoriek",
    page_icon="🧪",
    layout="wide"
)

# Inicializácia session state
if 'admin_mode' not in st.session_state:
    st.session_state.admin_mode = False
if 'samples_count' not in st.session_state:
    st.session_state.samples_count = 0
if 'samples_names' not in st.session_state:
    st.session_state.samples_names = []
if 'evaluations' not in st.session_state:
    st.session_state.evaluations = []
if 'session_active' not in st.session_state:
    st.session_state.session_active = False



def admin_interface():
    """Admin rozhranie pre nastavenie hodnotenia"""
    st.title("🔧 Admin Panel - Nastavenie hodnotenia vzoriek")
    
    with st.container():
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader("Nastavenie vzoriek")
            
            # Počet vzoriek
            samples_count = st.number_input(
                "Počet vzoriek na hodnotenie:",
                min_value=2,
                max_value=20,
                value=st.session_state.samples_count if st.session_state.samples_count > 0 else 3
            )
            
            # Názvy vzoriek
            st.write("**Názvy vzoriek:**")
            sample_names = []
            
            for i in range(samples_count):
                name = st.text_input(
                    f"Vzorka {i+1}:",
                    value=st.session_state.samples_names[i] if i < len(st.session_state.samples_names) else f"Vzorka {i+1}",
                    key=f"sample_name_{i}"
                )
                sample_names.append(name)
            
            # Tlačidlá
            col_btn1, col_btn2, col_btn3 = st.columns(3)
            
            with col_btn1:
                if st.button("💾 Uložiť nastavenia", type="primary"):
                    st.session_state.samples_count = samples_count
                    st.session_state.samples_names = sample_names
                    st.session_state.session_active = True
                    st.success("✅ Nastavenia uložené!")
                    st.rerun()
            
            with col_btn2:
                if st.button("🔄 Reset hodnotení"):
                    st.session_state.evaluations = []
                    st.success("✅ Hodnotenia resetované!")
                    st.rerun()
            
            with col_btn3:
                if st.button("👥 Prepnúť na hodnotenie"):
                    st.session_state.admin_mode = False
                    st.rerun()
        
        with col2:
            if st.session_state.session_active:
                st.subheader("🔗 Odkaz pre hodnotiteľov")
                
                # Generovanie URL pre hodnotiteľov
                # V skutočnej aplikácii by ste použili skutočnú URL
                current_url = "http://localhost:8501"  # Zmeňte na vašu skutočnú URL
                evaluator_url = f"{current_url}?mode=evaluator"
                
                # Zobrazenie odkazu
                st.code(evaluator_url, language="text")
                st.caption("💡 Hodnotitelia môžu použiť tento odkaz")
                
                if st.button("📋 Kopírovať odkaz"):
                    st.write("Odkaz skopírovaný do schránky!")
                    st.balloons()
    
    # Zobrazenie aktuálnych nastavení
    if st.session_state.session_active:
        st.divider()
        st.subheader("📊 Aktuálne nastavenia")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Počet vzoriek", st.session_state.samples_count)
        with col2:
            st.metric("Počet hodnotení", len(st.session_state.evaluations))
        
        # Zoznam vzoriek
        st.write("**Vzorky na hodnotenie:**")
        for i, name in enumerate(st.session_state.samples_names):
            st.write(f"{i+1}. {name}")
    
    # Zobrazenie výsledkov
    if st.session_state.evaluations:
        st.divider()
        st.subheader("📈 Výsledky hodnotenia")
        
        # Konverzia na DataFrame
        df = pd.DataFrame(st.session_state.evaluations)
        
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
    st.title("🧪 Hodnotenie vzoriek")
    
    if not st.session_state.session_active:
        st.error("❌ Hodnotenie nie je aktívne. Kontaktujte administrátora.")
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
        
        for i, sample_name in enumerate(st.session_state.samples_names):
            ranking = st.selectbox(
                f"Poradie pre {sample_name}:",
                options=list(range(1, st.session_state.samples_count + 1)),
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
                    
                    st.session_state.evaluations.append(evaluation)
                    
                    st.success("✅ Hodnotenie bolo úspešne odoslané!")
                    st.balloons()
                    
                    # Zobrazenie súhrnu
                    st.subheader("📋 Vaše hodnotenie:")
                    for sample_name, ranking in rankings.items():
                        st.write(f"**{sample_name}**: {ranking}. miesto")
                    
                    if comment:
                        st.write(f"**Komentár**: {comment}")
    
    # Tlačidlo pre admin
    st.divider()
    if st.button("🔧 Admin panel"):
        st.session_state.admin_mode = True
        st.rerun()

def main():
    """Hlavná funkcia aplikácie"""
    
    # Kontrola URL parametrov
    query_params = st.query_params
    if 'mode' in query_params and query_params['mode'] == 'evaluator':
        st.session_state.admin_mode = False
    
    # Sidebar pre navigáciu
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
        
        if st.session_state.session_active:
            st.success(f"✅ Aktívne hodnotenie\n{st.session_state.samples_count} vzoriek")
        else:
            st.warning("⚠️ Hodnotenie nie je nastavené")
    
    # Zobrazenie príslušného rozhrania
    if st.session_state.admin_mode:
        admin_interface()
    else:
        evaluator_interface()

if __name__ == "__main__":
    main()