import openai
import streamlit as st
import json
import os
from dotenv import load_dotenv  # Pour charger les variables d'environnement à partir d'un fichier .env
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
    values = result.get('values', [])
    return values

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

user_prompt = st.text_area("Écrivez ici votre prompt pour générer une fiche de poste :", 
                          "Entrez ici le prompt pour ChatGPT...")

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
            fiche_generee = response['choices'][0]['message']['content'].strip()
            st.subheader('Fiche de Poste Générée:')
            st.write(fiche_generee)
            with st.form(key="form_prompt"):
                submit = st.form_submit_button("Trouver le candidat idéal")
                if submit:
                    st.success("Lancement de la recherche pour la fiche générée ci-dessus.")
        except Exception as e:
            st.error(f"Erreur lors de la génération de la fiche de poste : {e}")
    else:
        st.warning("Veuillez entrer un prompt avant de soumettre.")

if st.button('Générer à partir du fichier RPO'):
    try:
        donnees_rpo = recuperer_donnees_google_sheet()

        for i, poste_selectionne in enumerate(donnees_rpo[1:]):
            titre_poste = poste_selectionne[5] if len(poste_selectionne) > 5 else 'Titre non spécifié'
            duree_mission = poste_selectionne[13] if len(poste_selectionne) > 13 else '6 mois'
            statut_mission = poste_selectionne[6] if len(poste_selectionne) > 6 else ''
            salaire = poste_selectionne[14] if len(poste_selectionne) > 14 else ''
            teletravail = poste_selectionne[18] if len(poste_selectionne) > 18 else ''
            date_demarrage = poste_selectionne[12] if len(poste_selectionne) > 12 else ''
            competences = poste_selectionne[17] if len(poste_selectionne) > 17 else ''
            projet = poste_selectionne[15] if len(poste_selectionne) > 15 else ''
            client = poste_selectionne[9] if len(poste_selectionne) > 9 else ''
            localisation = poste_selectionne[10] if len(poste_selectionne) > 10 else ''

            prompt_fiche = "Description du poste :\n"
            prompt_fiche += f"- Titre du poste recherché : {titre_poste}\n"
            prompt_fiche += f"- Durée de la mission : {duree_mission}\n"
            prompt_fiche += f"- Statut mission : {statut_mission}\n" if statut_mission else ""
            prompt_fiche += f"- Projet : {projet}\n" if projet else ""
            prompt_fiche += f"- Compétences : {competences}\n" if competences else ""
            prompt_fiche += f"- Salaire : {salaire}\n" if salaire else ""
            prompt_fiche += f"- Télétravail : {teletravail}\n" if teletravail else ""
            prompt_fiche += f"- Date de démarrage : {date_demarrage}\n" if date_demarrage else ""
            prompt_fiche += f"- Localisation : {localisation}\n" if localisation else ""

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
                st.subheader(f'Fiche de Poste pour {titre_poste}:')
                st.write(fiche_rpo)
                with st.form(key=f"form_rpo_{i}"):
                    submit = st.form_submit_button("Trouver le candidat idéal")
                    if submit:
                        st.success(f"Lancement de la recherche pour le poste : {titre_poste}")

    except Exception as e:
        st.error(f"Erreur lors de la récupération ou du traitement des données : {e}")
