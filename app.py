import openai
import streamlit as st
import json
import os
import csv
from datetime import datetime
import re
import unicodedata
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ==============================
# Config & Secrets
# ==============================
openai.api_key = st.secrets["openai"]["api_key"]
google_api_key = st.secrets["google"]["google_api_key"]

# Google Sheets
SPREADSHEET_ID = '1wl_OvLv7c8iN8Z40Xutu7CyrN9rTIQeKgpkDJFtyKIU'  # Remplace par ton propre ID
RANGE_NAME = 'Besoins ASI!A1:Z1000'  # Plage de données dans Google Sheets

# Chemins de stockage local
OUTPUT_DIR = "out_fiches"
INDEX_CSV = "fiches_index.csv"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==============================
# Auth Google Sheets
# ==============================
credentials = service_account.Credentials.from_service_account_info(
    json.loads(google_api_key)
)
service = build('sheets', 'v4', credentials=credentials)

# ==============================
# Utilitaires
# ==============================
def slugify(value: str) -> str:
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^a-zA-Z0-9_-]+', '-', value).strip('-').lower()
    return value or "fiche"

def parse_date_maybe(s: str):
    """Essaie de parser une date avec quelques formats usuels. Retourne datetime ou None."""
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except Exception:
            continue
    # heuristique : si ça ressemble à une date ISO partielle
    try:
        # tente YYYY-MM-DDTHH:MM:SSZ
        return datetime.fromisoformat(s.replace('Z', '').strip())
    except Exception:
        return None

def detect_date_column(headers):
    """Trouve l'index d'une colonne date probable dans les en-têtes."""
    if not headers:
        return None
    keys = ['date', 'timestamp', 'créé', 'ajout', 'creation', 'added', 'updated', 'maj', 'demarrage', 'start']
    hdr_lower = [h.lower() for h in headers]
    for i, h in enumerate(hdr_lower):
        if any(k in h for k in keys):
            return i
    return None

def read_google_sheet_values():
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    values = result.get('values', [])
    return values

def recuperer_donnees_google_sheet_sorted_recent_first():
    """Récupère la sheet et renvoie (headers, rows triées du plus récent au moins récent)."""
    values = read_google_sheet_values()
    if not values:
        return [], []
    headers = values[0]
    rows = values[1:]

    # Détecte une colonne date et trie desc
    date_idx = detect_date_column(headers)
    if date_idx is not None:
        def row_key(r):
            d = r[date_idx] if len(r) > date_idx else ""
            dt = parse_date_maybe(d)
            # Pour les lignes sans date parseable, on renvoie datetime.min pour qu'elles soient en bas
            return dt or datetime.min
        rows.sort(key=row_key, reverse=True)
    else:
        # Fallback : on suppose que les lignes récentes sont en bas -> on inverse pour avoir récent -> ancien
        rows = list(reversed(rows))
    return headers, rows

def save_fiche(content: str, meta: dict):
    """Enregistre la fiche en .md et met à jour l'index CSV."""
    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")
    title = meta.get("titre_poste") or "fiche"
    fname = f"{ts}_{slugify(title)}.md"
    fpath = os.path.join(OUTPUT_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)

    # maj index
    fieldnames = ["filename", "filepath", "titre_poste", "client", "localisation", "statut_mission",
                  "duree_mission", "salaire", "teletravail", "date_demarrage", "competences", "projet",
                  "generated_at"]
    file_exists = os.path.exists(INDEX_CSV)
    with open(INDEX_CSV, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        row = {
            "filename": fname,
            "filepath": fpath,
            "titre_poste": meta.get("titre_poste", ""),
            "client": meta.get("client", ""),
            "localisation": meta.get("localisation", ""),
            "statut_mission": meta.get("statut_mission", ""),
            "duree_mission": meta.get("duree_mission", ""),
            "salaire": meta.get("salaire", ""),
            "teletravail": meta.get("teletravail", ""),
            "date_demarrage": meta.get("date_demarrage", ""),
            "competences": meta.get("competences", ""),
            "projet": meta.get("projet", ""),
            "generated_at": now.isoformat(timespec="seconds"),
        }
        writer.writerow(row)
    return fpath, fname

def load_index_rows():
    if not os.path.exists(INDEX_CSV):
        return []
    rows = []
    with open(INDEX_CSV, "r", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for r in reader:
            rows.append(r)
    # tri par défaut: plus récent -> moins récent
    rows.sort(key=lambda r: r.get("generated_at", ""), reverse=True)
    return rows

def openai_generate_fiche(prompt_text: str):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",  # Ou gpt-4 si dispos
        messages=[
            {"role": "system", "content": "Vous êtes un assistant générateur de fiches de poste."},
            {"role": "user", "content": prompt_text}
        ],
        max_tokens=500
    )
    return response['choices'][0]['message']['content'].strip()

def build_prompt_from_row(row):
    # Sécurise les accès aux colonnes comme dans ton code d'origine
    titre_poste   = row[5]  if len(row) > 5  else 'Titre non spécifié'
    duree_mission = row[13] if len(row) > 13 else '6 mois'
    statut_mission= row[6]  if len(row) > 6  else ''
    salaire       = row[14] if len(row) > 14 else ''
    teletravail   = row[18] if len(row) > 18 else ''
    date_demarrage= row[12] if len(row) > 12 else ''
    competences   = row[17] if len(row) > 17 else ''
    projet        = row[15] if len(row) > 15 else ''
    client        = row[9]  if len(row) > 9  else ''
    localisation  = row[10] if len(row) > 10 else ''

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

    meta = {
        "titre_poste": titre_poste,
        "duree_mission": duree_mission,
        "statut_mission": statut_mission,
        "salaire": salaire,
        "teletravail": teletravail,
        "date_demarrage": date_demarrage,
        "competences": competences,
        "projet": projet,
        "client": client,
        "localisation": localisation
    }
    return prompt_fiche, meta

def generate_from_rpo_pipeline():
    headers, rows = recuperer_donnees_google_sheet_sorted_recent_first()
    if not rows:
        st.warning("Aucune donnée trouvée dans la Google Sheet.")
        return

    with st.spinner("Génération des fiches à partir du RPO (ordre : récent → ancien) ..."):
        for row in rows:
            prompt_fiche, meta = build_prompt_from_row(row)
            try:
                content = openai_generate_fiche(prompt_fiche)
                # Affichage immédiat
                st.subheader(f'Fiche de Poste pour {meta["titre_poste"]}:')
                st.write(content)
                # Sauvegarde + index
                path, name = save_fiche(content, meta)
                st.success(f"Fiche enregistrée : {name}")
            except Exception as e:
                st.error(f"Erreur génération/sauvegarde pour {meta.get('titre_poste', 'N/A')} : {e}")

# ==============================
# UI
# ==============================
st.title('🎯 IDEALMATCH JOB CREATOR')

tab_accueil, tab_prompt, tab_rpo, tab_fiches = st.tabs(
    ["🏠 Accueil", "✍️ Génération par prompt", "📄 Générer avec RPO", "📚 Fiches générées"]
)

# -------- Onglet Accueil --------
with tab_accueil:
    st.markdown("""
Bienvenue dans l'outil **IDEALMATCH JOB CREATOR** !  
Cet outil vous permet de générer des fiches de poste personnalisées à l'aide de l'intelligence artificielle (ChatGPT).

### Instructions :
- Onglet **Génération par prompt** : écrivez un prompt libre.
- Onglet **Générer avec RPO** : générez à partir de la Google Sheet.
- Onglet **Fiches générées** : retrouvez toutes vos fiches (recherche + téléchargement).

📝 **Astuces** :
- Soyez précis dans votre description pour obtenir les meilleurs résultats.
- L'outil utilise la dernière version de GPT-3.5 pour vous fournir des résultats de qualité.
""")

    if st.button('Générer avec RPO (récent → ancien)'):
        try:
            generate_from_rpo_pipeline()
        except Exception as e:
            st.error(f"Erreur lors de la récupération ou du traitement des données : {e}")

# -------- Onglet Génération par prompt --------
with tab_prompt:
    user_prompt = st.text_area(
        "Écrivez ici votre prompt pour générer une fiche de poste :",
        "Entrez ici le prompt pour ChatGPT..."
    )
    if st.button('Générer la Fiche de Poste'):
        if user_prompt:
            try:
                content = openai_generate_fiche(user_prompt)
                st.subheader('Fiche de Poste Générée:')
                st.write(content)

                # métadonnées minimales pour l'index si génération par prompt
                meta = {
                    "titre_poste": "Fiche (prompt libre)",
                    "client": "",
                    "localisation": "",
                    "statut_mission": "",
                    "duree_mission": "",
                    "salaire": "",
                    "teletravail": "",
                    "date_demarrage": "",
                    "competences": "",
                    "projet": ""
                }
                path, name = save_fiche(content, meta)
                st.success(f"Fiche enregistrée : {name}")
            except Exception as e:
                st.error(f"Erreur lors de la génération de la fiche de poste : {e}")
        else:
            st.warning("Veuillez entrer un prompt avant de soumettre.")

# -------- Onglet Générer avec RPO --------
with tab_rpo:
    st.markdown("Génération depuis la Google Sheet, **traitée du plus récent au moins récent**.")
    if st.button('Générer à partir du fichier RPO (récent → ancien)'):
        try:
            generate_from_rpo_pipeline()
        except Exception as e:
            st.error(f"Erreur lors de la récupération ou du traitement des données : {e}")

# -------- Onglet Fiches générées --------
with tab_fiches:
    st.subheader("Toutes les fiches générées")
    query = st.text_input("🔎 Recherche (titre, client, localisation, compétences, projet, ...)", "")

    rows = load_index_rows()

    # Filtrage plein-texte simple
    if query:
        q = query.lower()
        def match(r):
            hay = " ".join([
                r.get("titre_poste",""), r.get("client",""), r.get("localisation",""),
                r.get("statut_mission",""), r.get("duree_mission",""), r.get("salaire",""),
                r.get("teletravail",""), r.get("date_demarrage",""), r.get("competences",""),
                r.get("projet",""), r.get("filename","")
            ]).lower()
            return q in hay
        rows = list(filter(match, rows))

    if not rows:
        st.info("Aucune fiche enregistrée pour le moment.")
    else:
        # Affichage en liste, tri déjà récent -> ancien
        for r in rows:
            with st.container(border=True):
                st.markdown(f"**{r.get('titre_poste','(sans titre)')}** — {r.get('localisation','')}  \n"
                            f"Client: {r.get('client','')}  \n"
                            f"🕒 Générée le: {r.get('generated_at','')}")
                file_path = r.get("filepath","")
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        content_preview = f.read()
                    # petit extrait aperçu
                    st.text_area("Aperçu", content_preview[:1000], height=150, key=f"preview_{r.get('filename','')}")
                    st.download_button("Télécharger", data=content_preview, file_name=r.get("filename","fiche.md"))
                else:
                    st.error("Fichier introuvable sur le disque. Vérifiez le répertoire de sortie.")
