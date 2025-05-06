import openai
import streamlit as st
import json
from pymongo import MongoClient
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- Configuration des API ---
openai.api_key = st.secrets["openai"]["api_key"]

# Connexion MongoDB Atlas
mongo_uri = st.secrets["mongodb"]["uri"]
client = MongoClient(mongo_uri)
db = client["Job_creator"]
collection_fiches = db["fiches"]
collection_emails = db["emails"]

# Google Sheets
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

def extraire_ville(fiche_contenu):
    for ligne in fiche_contenu.split('\n'):
        if "localisation" in ligne.lower():
            return ligne.split(":")[-1].strip()
    return "votre région"

def generer_email(nom_poste, ville):
    return f"""Bonjour,

En découvrant votre profil, j’ai tout de suite vu une belle opportunité pour le poste de « {nom_poste} » basé à « {ville} ». Votre expérience et votre expertise dans ce domaine m’intéressent particulièrement, et je serais ravi d’échanger avec vous à ce sujet.

Je pense que cet échange pourrait être enrichissant des deux côtés. Seriez-vous disponible pour en discuter prochainement ?

Au plaisir d’échanger avec vous !"""

# --- Chargement des données sauvegardées ---
if 'fiches' not in st.session_state:
    st.session_state['fiches'] = list(collection_fiches.find({}, {"_id": 0}))
if 'fiche_selectionnee' not in st.session_state:
    st.session_state['fiche_selectionnee'] = None
if 'afficher_liste_candidats' not in st.session_state:
    st.session_state['afficher_liste_candidats'] = False
if 'email_genere' not in st.session_state:
    st.session_state['email_genere'] = ""

onglet1, onglet2, onglet3 = st.tabs(["Générateur de Fiche", "Trouver un candidat", "Création d'email"])

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
                fiche_doc = {"titre": "Fiche personnalisée", "contenu": fiche}
                st.session_state['fiches'].append(fiche_doc)
                collection_fiches.insert_one(fiche_doc)
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
                fiche_doc = {"titre": titre_poste, "contenu": fiche}
                st.session_state['fiches'].append(fiche_doc)
                collection_fiches.insert_one(fiche_doc)
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
                    st.session_state['afficher_liste_candidats'] = False

                    ville = extraire_ville(fiche['contenu'])
                    email = generer_email(fiche['titre'], ville)
                    st.session_state['email_genere'] = email
                    collection_emails.insert_one({"poste": fiche['titre'], "ville": ville, "email": email})

with onglet2:
    st.title("Trouver un candidat")
    fiche = st.session_state.get('fiche_selectionnee')
    if fiche:
        st.markdown(f"<h4><strong>{fiche['titre']}</strong></h4>", unsafe_allow_html=True)
        st.markdown(fiche['contenu'], unsafe_allow_html=False)

        if st.button("Liste de candidats"):
            st.session_state['afficher_liste_candidats'] = True

        if st.session_state.get('afficher_liste_candidats'):
            st.markdown(f"### 👥 Liste des candidats pour {fiche['titre']}")
            st.info("Ici s'affichera la liste des candidats sélectionnés...")
    else:
        st.info("Cliquez sur un bouton 'Trouver le candidat idéal' pour charger une fiche.")

with onglet3:
    st.title("Création d'email")
    email = st.session_state.get('email_genere', "")
    if email:
        st.text_area("✉️ Email généré automatiquement :", email, height=220)

    if st.button("📥 Voir l'historique des emails"):
        emails = list(collection_emails.find().sort("_id", -1))
        for mail in emails:
            st.markdown(f"**Poste :** {mail['poste']}  ")
            st.markdown(f"**Ville :** {mail['ville']}  ")
            st.text_area("Email envoyé :", mail['email'], height=200)
            st.markdown("---")
    else:
        st.info("Cliquez sur le bouton ci-dessus pour afficher les emails enregistrés.")
