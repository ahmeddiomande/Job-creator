import openai
import streamlit as st
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Récupérer la clé API OpenAI depuis les secrets de Streamlit (de `secrets.toml` dans `.streamlit/`)
openai.api_key = st.secrets["openai"]["api_key"]

# Récupérer la clé Google Sheets depuis les secrets de Streamlit (de `secrets.toml` dans `.streamlit/`)
google_api_key = st.secrets["google"]["google_api_key"]

# Créer les identifiants d'authentification pour l'API Google Sheets en utilisant la clé JSON récupérée
credentials = service_account.Credentials.from_service_account_info(
    json.loads(google_api_key)
)

# ID de ton fichier Google Sheets et la plage de données que tu souhaites récupérer
SPREADSHEET_ID = '1wl_OvLv7c8iN8Z40Xutu7CyrN9rTIQeKgpkDJFtyKIU'  # Remplace par ton propre ID
RANGE_NAME = 'Besoins ASI!A1:Z1000'  # Plage de données dans Google Sheets

# Créer le service Google Sheets
service = build('sheets', 'v4', credentials=credentials)

# Fonction pour récupérer les données du fichier Google Sheets
def recuperer_donnees_google_sheet():
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    values = result.get('values', [])
    return values

# --- Mise en forme de l'interface Streamlit ---

# Titre principal
st.title('🎯 IDEALMATCH JOB CREATOR')

# Texte introductif
st.markdown("""
Bienvenue dans l'outil **IDEALMATCH JOB CREATOR** !  
Cet outil vous permet de générer des fiches de poste personnalisées à l'aide de l'intelligence artificielle (ChatGPT).

### Instructions :
- Entrez votre **prompt personnalisé** dans la zone de texte ci-dessous.
- Cliquez sur le bouton "Générer la Fiche de Poste" pour obtenir une fiche automatiquement générée.
- La fiche sera basée sur votre description du poste et des critères de sélection.

📝 **Astuces** :
- Soyez précis dans votre description pour obtenir les meilleurs résultats.
- L'outil utilise la dernière version de GPT-3.5 pour vous fournir des résultats de qualité.
""")

# --- Zone de saisie du prompt de l'utilisateur ---
user_prompt = st.text_area("Écrivez ici votre prompt pour générer une fiche de poste :", 
                          "Entrez ici le prompt pour ChatGPT...")

# --- Bouton pour envoyer la demande à OpenAI ---
if st.button('Générer la Fiche de Poste'):
    if user_prompt:
        try:
            # Appeler l'API OpenAI avec le prompt de l'utilisateur
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # Ou gpt-4 si tu l'as
                messages=[
                    {"role": "system", "content": "Vous êtes un assistant générateur de fiches de poste."},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=500
            )
            
            # Afficher la réponse générée par ChatGPT
            st.subheader('Fiche de Poste Générée:')
            st.write(response['choices'][0]['message']['content'].strip())
        
        except Exception as e:
            st.error(f"Erreur lors de la génération de la fiche de poste : {e}")
    else:
        st.warning("Veuillez entrer un prompt avant de soumettre.")

# --- Ajouter un bouton pour générer les fiches de poste depuis le fichier RPO ---
if st.button('Générer à partir du fichier RPO'):
    # Récupérer et traiter les données du fichier RPO
    try:
        donnees_rpo = recuperer_donnees_google_sheet()

        for poste_selectionne in donnees_rpo[1:]:  # Ignore la première ligne (les en-têtes)
            # Vérifier si les données sont présentes avant de les ajouter
            titre_poste = poste_selectionne[5] if len(poste_selectionne) > 5 else 'Titre non spécifié'
            duree_mission = poste_selectionne[13] if len(poste_selectionne) > 13 else '6 mois'  # Valeur par défaut
            statut_mission = poste_selectionne[6] if len(poste_selectionne) > 6 else ''
            salaire = poste_selectionne[14] if len(poste_selectionne) > 14 else ''
            teletravail = poste_selectionne[18] if len(poste_selectionne) > 18 else ''
            date_demarrage = poste_selectionne[12] if len(poste_selectionne) > 12 else ''
            competences = poste_selectionne[17] if len(poste_selectionne) > 17 else ''
            projet = poste_selectionne[15] if len(poste_selectionne) > 15 else ''
            client = poste_selectionne[9] if len(poste_selectionne) > 9 else ''
            localisation = poste_selectionne[10] if len(poste_selectionne) > 10 else ''

            # Construire le prompt en n'ajoutant que les informations disponibles
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

            # Appeler l'API OpenAI pour générer la fiche de poste
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # Ou gpt-4 si tu l'as
                messages=[
                    {"role": "system", "content": "Vous êtes un assistant générateur de fiches de poste."},
                    {"role": "user", "content": prompt_fiche}
                ],
                max_tokens=500
            )

            # Afficher la réponse générée par ChatGPT
            st.subheader(f'Fiche de Poste pour {titre_poste}:')
            st.write(response['choices'][0]['message']['content'].strip())
        
    except Exception as e:
        st.error(f"Erreur lors de la récupération ou du traitement des données : {e}")
