import openai
import streamlit as st
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Clés API
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

# Interface principale
st.set_page_config(page_title="IdealMatch", layout="centered")
tabs = st.tabs(["🏠 Générateur de Fiche", "🔎 TROUVE UN CANDIDAT"])

with tabs[0]:
    st.image("assets/logo.png", width=400)
    st.title('🎯 IDEALMATCH JOB CREATOR')

    st.markdown("""
    Bienvenue dans l'outil **IDEALMATCH JOB CREATOR** !

    ### Instructions :
    - Personnalisez vos fiches de postes dans la zone de texte ci-dessous.
    - Cliquez sur le bouton "Générer la Fiche de Poste" pour obtenir une fiche automatiquement générée.
    - La fiche sera basée sur votre description du poste et des critères de sélection.

    📝 **Astuces** :
    - Soyez précis dans votre description pour obtenir les meilleurs résultats.
    """)

    user_prompt = st.text_area("Écrivez ici votre prompt pour générer une fiche de poste :", "Entrez ici le prompt pour ChatGPT...")

    if st.button('Générer la Fiche de Poste', key="btn_manual"):
        if user_prompt:
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Vous êtes un assistant générateur de fiches de poste."},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_tokens=500
                )
                fiche_generee = response['choices'][0]['message']['content'].strip()
                st.subheader('Fiche de Poste Générée:')
                st.write(fiche_generee)
                with st.form(key="form_prompt"):
                    submit = st.form_submit_button("Trouver le candidat idéal")
                    if submit:
                        st.session_state['onglet_actif'] = 1
                        st.experimental_rerun()
            except Exception as e:
                st.error(f"Erreur : {e}")
        else:
            st.warning("Veuillez entrer un prompt.")

    if st.button('Générer à partir du fichier RPO'):
        try:
            donnees_rpo = recuperer_donnees_google_sheet()
            for i, ligne in enumerate(donnees_rpo[1:]):
                titre_poste = ligne[5] if len(ligne) > 5 else 'Titre non spécifié'
                prompt_fiche = f"Description du poste :\n- Titre : {titre_poste}\n"
                prompt_fiche += f"- Durée : {ligne[13]}\n" if len(ligne) > 13 else ""
                prompt_fiche += f"- Projet : {ligne[15]}\n" if len(ligne) > 15 else ""
                prompt_fiche += f"- Compétences : {ligne[17]}\n" if len(ligne) > 17 else ""
                prompt_fiche += f"- Salaire : {ligne[14]}\n" if len(ligne) > 14 else ""
                prompt_fiche += f"- Télétravail : {ligne[18]}\n" if len(ligne) > 18 else ""
                prompt_fiche += f"- Démarrage : {ligne[12]}\n" if len(ligne) > 12 else ""
                prompt_fiche += f"- Lieu : {ligne[10]}\n" if len(ligne) > 10 else ""

                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Vous êtes un assistant générateur de fiches de poste."},
                        {"role": "user", "content": prompt_fiche}
                    ],
                    max_tokens=500
                )

                fiche_rpo = response['choices'][0]['message']['content'].strip()
                with st.container():
                    st.subheader(f'Fiche de Poste : {titre_poste}')
                    st.write(fiche_rpo)
                    with st.form(key=f"form_rpo_{i}"):
                        submit = st.form_submit_button("Trouver le candidat idéal")
                        if submit:
                            st.session_state['onglet_actif'] = 1
                            st.experimental_rerun()

        except Exception as e:
            st.error(f"Erreur : {e}")

with tabs[1]:
    st.title("🔎 Recherche de candidats")
    st.write("Ici s'affichera l'interface de sélection intelligente des candidats.")
