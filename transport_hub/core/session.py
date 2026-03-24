# core/session.py
# Gère l'état partagé entre les pages Streamlit

import streamlit as st

def init_session():
    """Initialise les variables de session au démarrage."""
    
    defaults = {
        "uploaded_files" : {},   # fichiers chargés par module
        "last_analysis"  : None, # dernière analyse effectuée
        "alerts"         : [],   # alertes actives
        "user_prefs"     : {},   # préférences utilisateur futures
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def get(key: str):
    """Lecture propre d'une variable de session."""
    return st.session_state.get(key)

def set(key: str, value):
    """Écriture propre d'une variable de session."""
    st.session_state[key] = value
