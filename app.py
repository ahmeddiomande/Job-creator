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

# Initialisation session
if 'fiche_selectionnee' not in st.session_state:
    st.session_state['fiche_selectionnee'] = None
if 'fiches' not in st.session_state:
    st.session_state['fiches'] = []

# Onglets
onglet1, onglet2 = st.tabs(["Générateur de Fiche", "Trouver un candidat"])

with onglet1:
    st.title('Générateur de Fiche')
    user_prompt = st.text_area("Personnalisation des fiches (style, langue, etc.)", "")

    if st.button("Générer à partir du fichier RPO"):
        try:
            donnees = recuperer_donnees_google_sheet()
            for i, ligne in enumerate(donnees[1:]):
                titre = ligne[5] if len(ligne) > 5 else 'Titre non spécifié'
                lieu = ligne[10] if len(ligne) > 10 else ''
                salaire = ligne[14] if len(ligne) > 14 else ''

                prompt = user_prompt.strip() + "\n\n"
                prompt += f"Titre : {titre}\n"
                prompt += f"Lieu : {lieu}\n" if lieu else ""
                prompt += f"Salaire : {salaire}\n" if salaire else ""

                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Tu es un assistant RH qui suit les instructions utilisateur à la lettre."},
                        {"role": "user", "content": prompt.strip()}
                    ],
                    max_tokens=500
                )

                fiche = response['choices'][0]['message']['content'].strip()
                st.session_state['fiches'].append({"titre": titre, "contenu": fiche})
        except Exception as e:
            st.error(f"Erreur : {e}")

    for i, fiche in enumerate(st.session_state['fiches']):
        if isinstance(fiche, dict) and 'titre' in fiche and 'contenu' in fiche:
            with st.container():
                st.markdown(f"**{fiche['titre']}**")
                st.markdown(fiche['contenu'], unsafe_allow_html=False)
                with st.form(key=f"form_{i}"):
                    submit = st.form_submit_button("Trouver le candidat idéal")
                    if submit:
                        st.session_state['fiche_selectionnee'] = fiche
                        st.experimental_rerun()

with onglet2:
    st.title("Trouver un candidat")
    fiche = st.session_state.get('fiche_selectionnee')
    if isinstance(fiche, dict) and 'titre' in fiche and 'contenu' in fiche:
        st.markdown(f"**{fiche['titre']}**")
        st.markdown(fiche['contenu'], unsafe_allow_html=False)
    else:
        st.info("Cliquez sur un bouton 'Trouver le candidat idéal' pour charger une fiche.")
