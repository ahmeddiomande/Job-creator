import openai
import streamlit as st
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Authentification API
openai.api_key = st.secrets["openai"]["api_key"]
google_api_key = st.secrets["google"]["google_api_key"]
google_credentials_dict = json.loads(google_api_key)
credentials = service_account.Credentials.from_service_account_info(google_credentials_dict)

SPREADSHEET_ID = '1wl_OvLv7c8iN8Z40Xutu7CyrN9rTIQeKgpkDJFtyKIU'
RANGE_NAME = 'Besoins ASI!A1:Z1000'
service = build('sheets', 'v4', credentials=credentials)

def recuperer_donnees_google_sheet():
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    return result.get('values', [])

# Initialisation état session
if 'onglet_actif' not in st.session_state:
    st.session_state['onglet_actif'] = 0
if 'fiche_selectionnee' not in st.session_state:
    st.session_state['fiche_selectionnee'] = None

# Onglets
tabs = st.tabs(["🏠 Générateur de Fiche", "🔎 TROUVE UN CANDIDAT"])

# Onglet 1 : Générateur
with tabs[0]:
    st.image("assets/logo.png", width=400)
    st.title('🎯 IDEALMATCH JOB CREATOR')

    st.markdown("""
    Bienvenue dans l'outil **IDEALMATCH JOB CREATOR** !

    ### Instructions :
    - Personnalisez vos fiches de postes dans la zone de texte ci-dessous.
    - Cliquez sur "Générer la Fiche de Poste".
    - Puis cliquez sur "Trouver le candidat idéal" pour lancer la recherche associée.

    📝 **Astuces** : Soyez précis dans votre description.
    """)

    # Fiche manuelle
    user_prompt = st.text_area("Écrivez ici votre prompt :", "Entrez ici le prompt pour ChatGPT...")

    if st.button('Générer la Fiche de Poste', key="btn_manual"):
        if user_prompt:
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Tu es un assistant RH."},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=500
                )
                fiche = response['choices'][0]['message']['content'].strip()
                st.subheader("Fiche générée :")
                st.write(fiche)
                with st.form(key="form_prompt"):
                    submit = st.form_submit_button("Trouver le candidat idéal")
                    if submit:
                        st.session_state['fiche_selectionnee'] = fiche
                        st.session_state['onglet_actif'] = 1
                        st.experimental_rerun()
            except Exception as e:
                st.error(f"Erreur : {e}")
        else:
            st.warning("Veuillez entrer un prompt.")

    # Fiches depuis RPO
    if st.button("Générer à partir du fichier RPO"):
        try:
            donnees = recuperer_donnees_google_sheet()
            for i, ligne in enumerate(donnees[1:]):
                titre = ligne[5] if len(ligne) > 5 else 'Titre non spécifié'
                prompt = f"- Titre : {titre}\n"
                prompt += f"- Durée : {ligne[13]}\n" if len(ligne) > 13 else ""
                prompt += f"- Projet : {ligne[15]}\n" if len(ligne) > 15 else ""
                prompt += f"- Compétences : {ligne[17]}\n" if len(ligne) > 17 else ""
                prompt += f"- Salaire : {ligne[14]}\n" if len(ligne) > 14 else ""
                prompt += f"- Télétravail : {ligne[18]}\n" if len(ligne) > 18 else ""
                prompt += f"- Lieu : {ligne[10]}\n" if len(ligne) > 10 else ""

                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Tu es un assistant RH."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=500
                )
                fiche = response['choices'][0]['message']['content'].strip()
                with st.container():
                    st.subheader(f"Fiche : {titre}")
                    st.write(fiche)
                    with st.form(key=f"form_rpo_{i}"):
                        submit = st.form_submit_button("Trouver le candidat idéal")
                        if submit:
                            st.session_state['fiche_selectionnee'] = fiche
                            st.session_state['onglet_actif'] = 1
                            st.experimental_rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

# Onglet 2 : Recherche Candidat
with tabs[1]:
    st.title("🔎 TROUVE UN CANDIDAT")

    if st.session_state.get('fiche_selectionnee'):
        st.markdown("### 📄 Fiche de poste sélectionnée :")
        st.write(st.session_state['fiche_selectionnee'])
    else:
        st.info("Cliquez sur un bouton 'Trouver le candidat idéal' pour charger une fiche.")
