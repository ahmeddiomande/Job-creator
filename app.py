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
REQUETE_EMAILS_CSV = "requete_emails.csv"
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
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(s.replace('Z', '').strip())
    except Exception:
        return None

def detect_date_column(headers):
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
    values = read_google_sheet_values()
    if not values:
        return [], []
    headers = values[0]
    rows = values[1:]
    date_idx = detect_date_column(headers)
    if date_idx is not None:
        def row_key(r):
            d = r[date_idx] if len(r) > date_idx else ""
            dt = parse_date_maybe(d)
            return dt or datetime.min
        rows.sort(key=row_key, reverse=True)
    else:
        rows = list(reversed(rows))
    return headers, rows

def save_fiche(content: str, meta: dict):
    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")
    title = meta.get("titre_poste") or "fiche"
    fname = f"{ts}_{slugify(title)}.md"
    fpath = os.path.join(OUTPUT_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)

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
    rows.sort(key=lambda r: r.get("generated_at", ""), reverse=True)
    return rows

def openai_generate_fiche(prompt_text: str):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Vous êtes un assistant générateur de fiches de poste."},
            {"role": "user", "content": prompt_text}
        ],
        max_tokens=500
    )
    return response['choices'][0]['message']['content'].strip()

def build_prompt_from_row(row):
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

# ==============================
# Génération LinkedIn + Email
# ==============================
def extraire_ville_depuis_contenu(contenu: str):
    # 1) cherche une ligne "Localisation: ..."
    for ligne in contenu.splitlines():
        if "localisation" in ligne.lower():
            v = ligne.split(":")[-1].strip()
            if v:
                return v
    # 2) sinon heuristique simple sur quelques villes communes (facultatif)
    m = re.search(r"\b(Paris|Lyon|Marseille|Toulouse|Bordeaux|Nantes|Lille|Strasbourg|Rennes|Nice)\b", contenu, flags=re.I)
    if m:
        return m.group(1)
    return "votre région"

def extraire_ville(meta: dict, contenu: str):
    ville = (meta or {}).get("localisation", "") or extraire_ville_depuis_contenu(contenu)
    return ville

def generer_email(nom_poste: str, ville: str):
    return f"""Bonjour,

En découvrant votre profil, j’ai tout de suite vu une belle opportunité pour le poste de « {nom_poste} » basé à « {ville} ». Votre expérience et votre expertise dans ce domaine m’intéressent particulièrement, et je serais ravi d’échanger avec vous à ce sujet.

Je pense que cet échange pourrait être enrichissant des deux côtés. Seriez-vous disponible pour en discuter prochainement ?

Au plaisir d’échanger avec vous !"""

def generer_requete_linkedin(contenu_fiche: str):
    prompt = f"""
Tu es un expert en sourcing RH. Génère une requête booléenne LinkedIn pour trouver des candidats correspondant à cette fiche de poste.
Structure la requête ainsi :
("Synonyme1" OR "Synonyme2" OR "Synonyme3")
AND ("Domaine1" OR "Domaine2" OR "Domaine3")
AND ("Méthode1" OR "Méthode2" OR "Méthode3")
AND ("Outil1" OR "Outil2" OR "Outil3")

Voici la fiche :
{contenu_fiche[:2000]}

Retourne uniquement la requête booléenne sans explication.
"""
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Tu es un assistant pour le recrutement"},
            {"role": "user", "content": prompt}
        ],
        max_tokens=400
    )
    return response['choices'][0]['message']['content'].strip()

def save_requete_email(titre_poste: str, ville: str, requete: str, email: str):
    now = datetime.now().isoformat(timespec="seconds")
    fieldnames = ["timestamp", "titre_poste", "ville", "requete", "email"]
    file_exists = os.path.exists(REQUETE_EMAILS_CSV)
    with open(REQUETE_EMAILS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            w.writeheader()
        w.writerow({
            "timestamp": now,
            "titre_poste": titre_poste or "",
            "ville": ville or "",
            "requete": requete or "",
            "email": email or ""
        })

def load_requetes_emails():
    if not os.path.exists(REQUETE_EMAILS_CSV):
        return []
    rows = []
    with open(REQUETE_EMAILS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    rows.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return rows

def generate_and_store_requete_email(contenu_fiche: str, meta: dict):
    titre = (meta or {}).get("titre_poste") or "Fiche (sans titre)"
    ville = extraire_ville(meta, contenu_fiche)
    email = generer_email(titre, ville)
    requete = generer_requete_linkedin(contenu_fiche)
    save_requete_email(titre, ville, requete, email)
    return requete, email, ville, titre

# ==============================
# Pipelines
# ==============================
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

                # Bouton pour requête & email sous la fiche
                if st.button("⚙️ Générer la requête LinkedIn + email", key=f"RPO_req_{meta['titre_poste']}_{slugify(content[:40])}"):
                    req, mail, ville, titre = generate_and_store_requete_email(content, meta)
                    st.success("Requête & email générés et enregistrés ✅")
                    with st.expander("🔍 Requête LinkedIn"):
                        st.code(req)
                    with st.expander("✉️ Email"):
                        st.text_area("Email", mail, height=220)

                # Sauvegarde + index
                path, name = save_fiche(content, meta)
                st.success(f"Fiche enregistrée : {name}")
            except Exception as e:
                st.error(f"Erreur génération/sauvegarde pour {meta.get('titre_poste', 'N/A')} : {e}")

# ==============================
# UI
# ==============================
st.title('🎯 IDEALMATCH JOB CREATOR')

tab_accueil, tab_prompt, tab_rpo, tab_fiches, tab_requetes = st.tabs(
    ["🏠 Accueil", "✍️ Génération par prompt", "📄 Générer avec RPO", "📚 Fiches générées", "🔍 Requêtes & Emails"]
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
- Onglet **Requêtes & Emails** : historique de vos requêtes LinkedIn et emails générés.

📝 **Astuces** :
- Soyez précis dans votre description pour obtenir les meilleurs résultats.
- L'outil utilise la dernière version de GPT-3.5 pour vous fournir des résultats de qualité.
""")

    if 'accueil_prompt_content' not in st.session_state:
        st.session_state['accueil_prompt_content'] = None
        st.session_state['accueil_meta'] = None

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
                # Afficher bouton de génération de requête sous la fiche
                if st.button("⚙️ Générer la requête LinkedIn + email", key="prompt_req_btn"):
                    req, mail, ville, titre = generate_and_store_requete_email(content, meta)
                    st.success("Requête & email générés et enregistrés ✅")
                    with st.expander("🔍 Requête LinkedIn"):
                        st.code(req)
                    with st.expander("✉️ Email"):
                        st.text_area("Email", mail, height=220)

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
        for r in rows:
            with st.container(border=True):
                st.markdown(f"**{r.get('titre_poste','(sans titre)')}** — {r.get('localisation','')}  \n"
                            f"Client: {r.get('client','')}  \n"
                            f"🕒 Générée le: {r.get('generated_at','')}")
                file_path = r.get("filepath","")
                fiche_content = ""
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        fiche_content = f.read()
                    st.text_area("Aperçu", fiche_content[:1000], height=150, key=f"preview_{r.get('filename','')}")
                    # Bouton "Créer la requête" sous chaque fiche
                    if st.button("⚙️ Générer la requête LinkedIn + email", key=f"req_btn_{r.get('filename','')}"):
                        req, mail, ville, titre = generate_and_store_requete_email(fiche_content, r)
                        st.success("Requête & email générés et enregistrés ✅")
                        with st.expander("🔍 Requête LinkedIn"):
                            st.code(req)
                        with st.expander("✉️ Email"):
                            st.text_area("Email", mail, height=220, key=f"mail_{r.get('filename','')}")
                    st.download_button("Télécharger", data=fiche_content, file_name=r.get("filename","fiche.md"))
                else:
                    st.error("Fichier introuvable sur le disque. Vérifiez le répertoire de sortie.")

# -------- Onglet Requêtes & Emails (5ᵉ onglet) --------
with tab_requetes:
    st.subheader("Historique — Requêtes LinkedIn & Emails")
    requetes = load_requetes_emails()
    filtre = st.text_input("🔎 Filtrer (poste / ville / contenu requête / email)", "")

    if filtre:
        f = filtre.lower()
        def ok(r):
            hay = " ".join([r.get("titre_poste",""), r.get("ville",""), r.get("requete",""), r.get("email","")]).lower()
            return f in hay
        requetes = list(filter(ok, requetes))

    if not requetes:
        st.info("Pas encore d'historique. Générez une requête depuis une fiche.")
    else:
        for i, r in enumerate(requetes):
            with st.container(border=True):
                st.markdown(f"**{r.get('titre_poste','(sans titre)')}** — {r.get('ville','')}  \n"
                            f"🕒 {r.get('timestamp','')}")
                with st.expander("🔍 Requête LinkedIn"):
                    st.code(r.get("requete",""))
                with st.expander("✉️ Email"):
                    st.text_area("Email", r.get("email",""), height=220, key=f"hist_email_{i}")
        # Export CSV
        if os.path.exists(REQUETE_EMAILS_CSV):
            with open(REQUETE_EMAILS_CSV, "r", encoding="utf-8") as f:
                data = f.read()
            st.download_button("📥 Exporter l'historique (CSV)", data=data, file_name="requete_emails.csv", mime="text/csv")
