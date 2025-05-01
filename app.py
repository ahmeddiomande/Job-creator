import openai
import streamlit as st
import json
import os
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

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

# --- Initialisation session ---
if 'fiches' not in st.session_state:
    st.session_state['fiches'] = []
if 'fiche_selectionnee' not in st.session_state:
    st.session_state['fiche_selectionnee'] = None

# Interface avec tabs
onglet1, onglet2 = st.tabs(["Générateur de Fiche", "Trouver un candidat"])

with onglet1:
    st.image("assets/logo.png", width=400)
    st.title('🎯 IDEALMATCH JOB CREATOR')

    st.markdown("""
    Bienvenue dans l'outil **IDEALMATCH JOB CREATOR** !  

    ### Instructions :
    - Personnalisez vos fiches de postes dans la zone de texte ci-dessous.
    - Cliquez sur le bouton "Générer la Fiche de Poste" pour obtenir une fiche automatiquement générée.
    - Ou cliquez sur "Générer à partir du fichier RPO" pour charger vos besoins ASI.
    """)

    user_prompt = st.text_area("Écrivez ici votre prompt pour générer une fiche de poste :", "Entrez ici le prompt pour ChatGPT...")

    if st.button('Générer la Fiche de Poste'):
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
                fiche = response['choices'][0]['message']['content'].strip()
                st.session_state['fiches'].append({"titre": "Fiche personnalisée", "contenu": fiche})
            except Exception as e:
                st.error(f"Erreur lors de la génération : {e}")
        else:
            st.warning("Veuillez entrer un prompt.")

    if st.button('Générer à partir du fichier RPO'):
        try:
            donnees_rpo = recuperer_donnees_google_sheet()
            for ligne in donnees_rpo[1:]:
                titre_poste = ligne[5] if len(ligne) > 5 else 'Titre non spécifié'
                duree_mission = ligne[13] if len(ligne) > 13 else '6 mois'
                statut_mission = ligne[6] if len(ligne) > 6 else ''
                salaire = ligne[14] if len(ligne) > 14 else ''
                teletravail = ligne[18] if len(ligne) > 18 else ''
                date_demarrage = ligne[12] if len(ligne) > 12 else ''
                competences = ligne[17] if len(ligne) > 17 else ''
                projet = ligne[15] if len(ligne) > 15 else ''
                localisation = ligne[10] if len(ligne) > 10 else ''

                prompt_fiche = user_prompt.strip() + "\n\n"
                prompt_fiche += f"Titre : {titre_poste}\n"
                prompt_fiche += f"Durée : {duree_mission}\n"
                prompt_fiche += f"Statut : {statut_mission}\n" if statut_mission else ""
                prompt_fiche += f"Projet : {projet}\n" if projet else ""
                prompt_fiche += f"Compétences : {competences}\n" if competences else ""
                prompt_fiche += f"Salaire : {salaire}\n" if salaire else ""
                prompt_fiche += f"Télétravail : {teletravail}\n" if teletravail else ""
                prompt_fiche += f"Démarrage : {date_demarrage}\n" if date_demarrage else ""
                prompt_fiche += f"Localisation : {localisation}\n" if localisation else ""

                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Vous êtes un assistant générateur de fiches de poste."},
                        {"role": "user", "content": prompt_fiche.strip()}
                    ],
                    max_tokens=500
                )
                fiche = response['choices'][0]['message']['content'].strip()
                st.session_state['fiches'].append({"titre": titre_poste, "contenu": fiche})
        except Exception as e:
            st.error(f"Erreur lors du traitement des données : {e}")

    for i, fiche in enumerate(st.session_state['fiches']):
        if isinstance(fiche, dict):
            st.markdown(f"<h4><strong>{fiche['titre']}</strong></h4>", unsafe_allow_html=True)
            st.markdown(fiche['contenu'], unsafe_allow_html=False)
            with st.form(key=f"form_{i}"):
                submit = st.form_submit_button("Trouver le candidat idéal")
                if submit:
                    st.session_state['fiche_selectionnee'] = fiche

with onglet2:
    st.title("Trouver un candidat")
    fiche = st.session_state.get('fiche_selectionnee')
    if fiche:
        st.markdown(f"<h4><strong>{fiche['titre']}</strong></h4>", unsafe_allow_html=True)
        st.markdown(fiche['contenu'], unsafe_allow_html=False)
    else:
        st.info("Cliquez sur un bouton 'Trouver le candidat idéal' pour charger une fiche.")
