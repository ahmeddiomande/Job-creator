import openai
import streamlit as st
import json
import re
from dotenv import load_dotenv  # Pour charger les variables d'environnement à partir d'un fichier .env
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Charger la clé API OpenAI depuis les secrets de Streamlit
openai.api_key = st.secrets["openai"]["api_key"]

# Récupérer la clé Google Sheets depuis les secrets Streamlit
google_api_key = st.secrets["google"]["google_api_key"]

# Charger la clé JSON Google en utilisant json.loads
google_credentials_dict = json.loads(google_api_key)

# Créer les identifiants d'authentification pour l'API Google Sheets en utilisant la clé JSON récupérée
credentials = service_account.Credentials.from_service_account_info(google_credentials_dict)

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

# --- Fonction pour nettoyer les caractères spéciaux et les espaces ---
def clean_string(s):
    # Remplacer les espaces par des underscores et enlever les caractères spéciaux
    s = s.replace(" ", "_")
    s = re.sub(r'[^a-zA-Z0-9_]', '', s)  # Enlever tous les caractères spéciaux
    return s

# --- Liste des fiches de poste générées ---
generated_fiches = []
fiche_contenu = {}

# --- Affichage de l'image transparente en entête ---
st.image("assets/logo.png", width=400)

# Titre principal
st.title('🎯 IDEALMATCH JOB CREATOR')

# Texte introductif
st.markdown("""
Bienvenue dans l'outil **IDEALMATCH JOB CREATOR** !

### Instructions :
- Personnalisez vos fiches de postes dans la zone de texte ci-dessous.
- Cliquez sur le bouton "Générer la Fiche de Poste" pour obtenir une fiche automatiquement générée.
- La fiche sera basée sur votre description du poste et des critères de sélection.

📝 **Astuces** :
- Soyez précis dans votre description pour obtenir les meilleurs résultats.
""")

# --- Zone de saisie du prompt de l'utilisateur ---
user_prompt = st.text_area("Écrivez ici votre prompt pour générer une fiche de poste :", 
                          "Entrez ici le prompt pour ChatGPT...")

# --- Bouton pour envoyer la demande à OpenAI ---
if st.button('Générer la Fiche de Poste'):
    if user_prompt:
        try:
            # Appeler l'API OpenAI avec le prompt de l'utilisateur en utilisant ChatCompletion
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # Ou gpt-4 si tu l'as
                messages=[
                    {"role": "system", "content": "Vous êtes un assistant générateur de fiches de poste."},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=500
            )
            
            # Récupérer la réponse générée par ChatGPT
            generated_text = response['choices'][0]['message']['content'].strip()

            # Générer un titre pour chaque fiche en fonction du prompt
            title = user_prompt.split(" ")[0]  # Exemple : Utiliser le premier mot du prompt comme titre
            generated_fiches.append(title)

            # Stocker la fiche de poste générée dans un dictionnaire
            fiche_contenu[title] = generated_text

            # Afficher la fiche de poste générée
            st.subheader(f'Fiche de Poste Générée pour {title}:')
            st.write(generated_text)

        except Exception as e:
            st.error(f"Erreur lors de la génération de la fiche de poste : {e}")
    else:
        st.warning("Veuillez entrer un prompt avant de soumettre.")

# --- Affichage des liens cliquables pour chaque fiche de poste ---
if generated_fiches:
    st.subheader('Liste des Fiches de Poste générées :')
    
    for poste in generated_fiches:
        # Récupérer les informations sur le poste et l'entreprise
        titre_poste = poste.split('_')[0]  # Utiliser juste le titre sans l'entreprise
        entreprise = "Société inconnue"  # Si l'entreprise n'est pas spécifiée
        
        # Nettoyer les noms des titres de postes et entreprises
        titre_poste_clean = clean_string(titre_poste)
        entreprise_clean = clean_string(entreprise)
        
        # Créer un lien cliquable
        st.markdown(f"[{titre_poste} ({entreprise})](#{titre_poste_clean}_{entreprise_clean})")

# --- Affichage de la fiche de poste lorsqu'on clique sur le lien ---
for fiche, contenu in fiche_contenu.items():
    # Ajouter une ancre pour que le lien fonctionne
    st.markdown(f"<a name='{fiche}'></a>", unsafe_allow_html=True)
    st.subheader(f"Fiche de Poste pour {fiche}:")
    st.write(contenu)

# --- Ajouter un bouton pour générer les fiches de poste depuis le fichier RPO ---
if st.button('Générer à partir du fichier RPO'):
    # Récupérer et traiter les données du fichier RPO
    try:
        donnees_rpo = recuperer_donnees_google_sheet()

        for poste_selectionne in donnees_rpo[1:]:  # Ignore la première ligne (les en-têtes)
            # Vérifier si les données sont présentes avant de les ajouter
            titre_poste = poste_selectionne[5] if len(poste_selectionne) > 5 else 'Titre non spécifié'
            entreprise = poste_selectionne[9] if len(poste_selectionne) > 9 else 'Société inconnue'
            
            # Nettoyer les noms des titres de postes et entreprises
            titre_poste_clean = clean_string(titre_poste)
            entreprise_clean = clean_string(entreprise)

            # Construire le prompt pour l'AI
            prompt_fiche = f"Fiche de poste pour {titre_poste} à {entreprise}."

            # Appeler l'API OpenAI pour générer la fiche de poste
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # Ou gpt-4 si tu l'as
                messages=[
                    {"role": "system", "content": "Vous êtes un assistant générateur de fiches de poste."},
                    {"role": "user", "content": prompt_fiche}
                ],
                max_tokens=500
            )

            generated_text = response['choices'][0]['message']['content'].strip()

            # Stocker la fiche de poste générée dans un dictionnaire
            fiche_contenu[f"{titre_poste}_{entreprise}"] = generated_text

            # Ajouter le titre de cette fiche de poste à la liste
            generated_fiches.append(f"{titre_poste}_{entreprise}")

        # Afficher la liste des liens après avoir généré toutes les fiches
        st.subheader('Sommaire des Fiches de Poste générées à partir du fichier RPO:')
        for fiche in generated_fiches:
            # Affichage des liens cliquables
            st.markdown(f"[{fiche}](#{fiche})")

    except Exception as e:
        st.error(f"Erreur lors de la récupération ou du traitement des données : {e}")
