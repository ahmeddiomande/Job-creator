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
    """Retourne (headers, rows) triés du plus récent au moins récent (si colonne date détectée)."""
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
            "salaire": meta.get("salaire", ""),  # <- contiendra TJM si présent
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

# ---------- Générateur au format STRICT & ROBUSTE ----------
TEMPLATE_OUTPUT = """Fiche de Poste Générée:
Intitulé du poste : {TITRE}

Description du poste :
{DESCRIPTION_PARAGRAPHE}

Responsabilités :
{RESP_PARAGRAPHE}
- {RESP1}
- {RESP2}
- {RESP3}
- {RESP4}
- {RESP5}

Compétences requises :
{COMP_PARAGRAPHE}
- {COMP1}
- {COMP2}
- {COMP3}
- {COMP4}
- {COMP5}

En résumé :
- Localisation : {RESUME_LOCALISATION}
- Statut & Rémunération : {RESUME_STATUT_REMU}
- Durée de la mission : {RESUME_DUREE}
- Télétravail : {RESUME_TELETRAVAIL}
- Expérience : {RESUME_EXPERIENCE}
"""

INSTRUCTIONS = """Tu es un assistant RH.
Tu dois produire UNIQUEMENT le contenu au format exact donné (TEMPLATE) sans ajouter d’explications ni de section "Consignes".
Style : phrases simples, lisibles, ton professionnel.
Règles de rédaction :
- Description : commence par reprendre le titre du poste avec une phrase d’accroche claire. Ajoute ensuite : « Au sein d’une équipe de <Taille de l’équipe> » si disponible.
- Responsabilités : réécris proprement TOUT le contenu de « Projet sur lequel va travailler le ou la candidate : » en un court paragraphe puis liste 3 à 5 responsabilités concrètes (puces).
- Compétences requises : combine les compétences techniques de « Compétences obligatoires… » et déduis des soft skills pertinents à partir du Projet. Écris d’abord un court paragraphe, puis 3 à 5 puces (mélange hard/soft).
- En résumé : fais une phrase d’accroche pour chaque ligne, puis la valeur. Pour « Statut & Rémunération » : 
    * si freelance → inclure « TJM <montant> € »
    * si CDI → inclure « Salaire <montant> »
    * si les deux sont possibles → mettre les deux, séparés par « — ».
- Ajoute le symbole « € » après toute valeur monétaire (TJM/Salaire) s’il est absent.
- N’ajoute pas d’autres sections. Respecte exactement les titres.

DONNÉES :
{DONNEES}

TEMPLATE (remplace les champs entre accolades ; garde exactement les titres/ponctuations) :
{TEMPLATE}
"""

def clean_fiche_output(text: str) -> str:
    """Nettoie toute fuite de 'Consignes' et normalise des puces."""
    text = re.sub(r"\n?Consignes\s*:.*$", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"^[ \t]*[•∙]\s?", "- ", text, flags=re.MULTILINE)
    return text.strip()

def ensure_euro_suffix(text: str) -> str:
    """Ajoute ' €' après les montants s'ils n'en ont pas déjà."""
    text = re.sub(r'(?im)\b(TJM|Salaire|Rémunération|Remuneration)\b([^:\n]*?:)?\s*([0-9][0-9\s.,kK]+)\b(?!\s*€)',
                  lambda m: f"{m.group(0)} €", text)
    text = re.sub(r'(?im)\b(TJM|Salaire)\s*[:\-]?\s*([0-9][0-9\s.,kK]+)\b(?!\s*€)',
                  lambda m: f"{m.group(0)} €", text)
    return text

def openai_generate_fiche_from_data(donnees: str, titre_force: str = None):
    template_vars = {
        "TITRE": (titre_force or "Intitulé non précisé"),
        "DESCRIPTION_PARAGRAPHE": "",
        "RESP_PARAGRAPHE": "",
        "RESP1": "", "RESP2": "", "RESP3": "", "RESP4": "", "RESP5": "",
        "COMP_PARAGRAPHE": "",
        "COMP1": "", "COMP2": "", "COMP3": "", "COMP4": "", "COMP5": "",
        "RESUME_LOCALISATION": "",
        "RESUME_STATUT_REMU": "",
        "RESUME_DUREE": "",
        "RESUME_TELETRAVAIL": "",
        "RESUME_EXPERIENCE": "",
    }
    prompt = INSTRUCTIONS.format(
        DONNEES=donnees.strip(),
        TEMPLATE=TEMPLATE_OUTPUT.format(**template_vars)
    )
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Tu génères des fiches de poste structurées au format imposé, sans ajouter de consignes."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1100,
        temperature=0.25
    )
    raw = response['choices'][0]['message']['content'].strip()
    cleaned = clean_fiche_output(raw)
    return ensure_euro_suffix(cleaned)

# ---------- Mapping EXACT des colonnes RPO ----------
COL_DATE_DEMARRAGE   = "Date de démarrage"
COL_TITRE            = "Titre du poste recherché"
COL_EXPERIENCE       = "Nombre d'année d'expérience"
COL_CLIENT           = "Nom du client"
COL_LOCALISATION     = "Localisation"
COL_STATUT           = "Statut"
COL_DUREE            = "Durée de la mission"
COL_TJM              = "TJM ( sans la marge ASI )"
COL_SALAIRE          = "Salaire "
COL_PROJET           = "Projet sur lequel va travailler le ou la candidate :"
COL_COMPETENCES      = "Compétences obligatoires ( Préciser technologies principales et frameworks pour les postes techniques )"
COL_TELETRAVAIL      = "Télétravail"
COL_TAILLE_EQUIPE    = "Taille de l’equipe"

def _norm(s: str) -> str:
    return (s or "").strip().lower().replace("’", "'").replace("  ", " ")

def header_index_map(headers):
    """Retourne un dict nom_cible->index avec variantes tolérées."""
    norm = { _norm(h): i for i, h in enumerate(headers) }

    def get_any(names):
        for n in names:
            key = _norm(n)
            if key in norm:
                return norm[key]
        return None

    idx = {}
    idx[COL_DATE_DEMARRAGE] = get_any([COL_DATE_DEMARRAGE, "Date de demarrage"])
    idx[COL_TITRE]          = get_any([COL_TITRE, "Intitulé du poste", "Intitule du poste", "Titre"])
    idx[COL_EXPERIENCE]     = get_any([COL_EXPERIENCE, "Annees d'experience", "Nombre d'annee d'experience"])
    idx[COL_CLIENT]         = get_any([COL_CLIENT, "Client", "Entreprise"])
    idx[COL_LOCALISATION]   = get_any([COL_LOCALISATION, "Ville", "Lieu", "Location"])
    idx[COL_STATUT]         = get_any([COL_STATUT, "Status", "Type de contrat"])
    idx[COL_DUREE]          = get_any([COL_DUREE, "Duree de la mission", "Durée"])
    idx[COL_TJM]            = get_any([COL_TJM, "TJM", "TJM (sans la marge ASI)"])
    idx[COL_SALAIRE]        = get_any([COL_SALAIRE, "Salaire", "Salaire brut", "Salaire net"])
    idx[COL_PROJET]         = get_any([COL_PROJET, "Projet", "Mission", "Contexte"])
    idx[COL_COMPETENCES]    = get_any([COL_COMPETENCES, "Compétences", "Competences", "Skills"])
    idx[COL_TELETRAVAIL]    = get_any([COL_TELETRAVAIL, "Remote", "Télétravail possible"])
    idx[COL_TAILLE_EQUIPE]  = get_any([COL_TAILLE_EQUIPE, "Taille de l'equipe", "Taille de l’équipe", "Taille equipe"])
    return idx

def safe_get_by_name(row, idx_map, name, default=""):
    i = idx_map.get(name, None)
    if i is None or len(row) <= i:
        return default
    val = row[i]
    if isinstance(val, str):
        return val.strip()
    return val if val is not None else default

def build_prompt_from_row(headers, row):
    idx = header_index_map(headers)

    # Valeurs
    titre_poste    = safe_get_by_name(row, idx, COL_TITRE, default='Titre non spécifié')
    duree_mission  = safe_get_by_name(row, idx, COL_DUREE, default='')
    statut_mission = safe_get_by_name(row, idx, COL_STATUT, default='')
    tjm            = safe_get_by_name(row, idx, COL_TJM, default='')      # rémunération/jour
    salaire_cdi    = safe_get_by_name(row, idx, COL_SALAIRE, default='')  # salaire si CDI
    teletravail    = safe_get_by_name(row, idx, COL_TELETRAVAIL, default='')
    date_demarrage = safe_get_by_name(row, idx, COL_DATE_DEMARRAGE, default='')
    competences    = safe_get_by_name(row, idx, COL_COMPETENCES, default='')
    projet         = safe_get_by_name(row, idx, COL_PROJET, default='')
    client         = safe_get_by_name(row, idx, COL_CLIENT, default='')
    localisation   = safe_get_by_name(row, idx, COL_LOCALISATION, default='')
    experience     = safe_get_by_name(row, idx, COL_EXPERIENCE, default='')
    taille_equipe  = safe_get_by_name(row, idx, COL_TAILLE_EQUIPE, default='')

    # Si titre non spécifié → on NE GÉNÈRE PAS
    titre_clean = (titre_poste or "").strip()
    if not titre_clean or titre_clean.lower() == "titre non spécifié":
        return None, None

    # Données passées au modèle
    donnees_lines = []
    donnees_lines.append(f'Titre du poste recherché : {titre_clean}')
    if taille_equipe:  donnees_lines.append(f'Taille de l’équipe : {taille_equipe}')
    if projet:         donnees_lines.append(f'{COL_PROJET} {projet}')
    if competences:    donnees_lines.append(f'{COL_COMPETENCES} {competences}')
    if localisation:   donnees_lines.append(f'Localisation : {localisation}')
    if statut_mission: donnees_lines.append(f'Statut : {statut_mission}')
    if tjm:            donnees_lines.append(f'{COL_TJM} {tjm}')
    if salaire_cdi:    donnees_lines.append(f'{COL_SALAIRE}{salaire_cdi}')
    if duree_mission:  donnees_lines.append(f'Durée de la mission : {duree_mission}')
    if teletravail:    donnees_lines.append(f'Télétravail : {teletravail}')
    if experience:     donnees_lines.append(f"Nombre d'année d'expérience : {experience}")
    if date_demarrage: donnees_lines.append(f'Date de démarrage : {date_demarrage}')
    if client:         donnees_lines.append(f'Nom du client : {client}')

    prompt_fiche = "\n".join(donnees_lines).strip()

    meta = {
        "titre_poste": titre_clean,
        "duree_mission": duree_mission,
        "statut_mission": statut_mission,
        "salaire": (tjm or salaire_cdi),  # priorité au TJM si présent
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
    for ligne in contenu.splitlines():
        if "localisation" in ligne.lower():
            v = ligne.split(":")[-1].strip()
            if v:
                return v
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
# Rendu UI pour une fiche (utilisé à l'accueil pour garder l'état)
# ==============================
def render_fiche_block(content: str, meta: dict, key_prefix: str):
    with st.container(border=True):
        st.subheader(f'Fiche de Poste pour {meta.get("titre_poste","(sans titre)")} :')
        if meta.get("salaire"):
            st.caption(f"💶 Rémunération (TJM/Sal.) : {meta['salaire']}")
        st.write(content)

        # État partagé pour afficher résultat à la suite du poste
        if "req_email_results" not in st.session_state:
            st.session_state["req_email_results"] = {}

        if st.button("⚙️ Générer la requête LinkedIn + email", key=f"{key_prefix}_btn"):
            req, mail, ville, titre = generate_and_store_requete_email(content, meta)
            st.session_state["req_email_results"][key_prefix] = {"req": req, "mail": mail}

        # Afficher (si déjà généré)
        result = st.session_state["req_email_results"].get(key_prefix)
        if result:
            with st.expander("🔍 Requête LinkedIn"):
                st.code(result["req"])
            with st.expander("✉️ Email"):
                st.text_area("Email", result["mail"], height=220, key=f"{key_prefix}_mail")

# ==============================
# Pipelines
# ==============================
def generate_from_rpo_pipeline(return_results: bool = False):
    """Si return_results=True, renvoie une liste de {'content','meta'} au lieu d'afficher directement."""
    headers, rows = recuperer_donnees_google_sheet_sorted_recent_first()
    if not rows:
        if not return_results:
            st.warning("Aucune donnée trouvée dans la Google Sheet.")
        return [] if return_results else None

    results = []

    with st.spinner("Génération des fiches à partir du RPO (ordre : récent → ancien) ..."):
        for row in rows:
            prompt_fiche, meta = build_prompt_from_row(headers, row)
            if prompt_fiche is None:
                continue
            try:
                content = openai_generate_fiche_from_data(prompt_fiche, titre_force=meta["titre_poste"])
                # Sauvegarde + index
                path, name = save_fiche(content, meta)

                if return_results:
                    results.append({"content": content, "meta": meta})
                else:
                    # Affichage direct (avec bouton inline)
                    render_fiche_block(content, meta, key_prefix=f"rpo_{slugify(meta['titre_poste'])}_{slugify(meta.get('localisation',''))}")
                    st.success(f"Fiche enregistrée : {name}")
            except Exception as e:
                if not return_results:
                    st.error(f"Erreur génération/sauvegarde pour {meta.get('titre_poste', 'N/A')} : {e}")

    if return_results:
        return results

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
- Onglet **Création d'une fiche instantanée** : écrivez un prompt libre.
- Onglet **Générer avec RPO** : générez à partir de la Google Sheet.
- Onglet **Fiches générées** : retrouvez toutes vos fiches (recherche + téléchargement).
- Onglet **Requêtes & Emails** : historique de vos requêtes LinkedIn et emails générés.

📝 **Astuces** :
- Soyez précis dans votre description pour obtenir les meilleurs résultats.
- Bonne recherche !
""")

    if "accueil_fiches" not in st.session_state:
        st.session_state["accueil_fiches"] = []

    if st.button('Générer avec RPO (récent → ancien)'):
        try:
            # On génère et on stocke en session pour que les boutons internes fonctionnent après le rerun
            st.session_state["accueil_fiches"] = generate_from_rpo_pipeline(return_results=True)
        except Exception as e:
            st.error(f"Erreur lors de la récupération ou du traitement des données : {e}")

    # Toujours afficher les fiches stockées (si présentes), AVEC le bouton requis à la suite
    if st.session_state["accueil_fiches"]:
        st.write("—")
        for i, item in enumerate(st.session_state["accueil_fiches"]):
            key_prefix = f"accueil_{i}_{slugify(item['meta'].get('titre_poste',''))}"
            render_fiche_block(item["content"], item["meta"], key_prefix)

# -------- Onglet Génération par prompt --------
with tab_prompt:
    user_prompt = st.text_area(
        "Écrivez ici votre prompt pour générer une fiche de poste :",
        "rédigez vos notes"
    )
    if st.button('Générer la Fiche de Poste'):
        if user_prompt:
            try:
                content = openai_generate_fiche_from_data(user_prompt, titre_force="Fiche (prompt libre)")
                st.subheader('Fiche de Poste Générée:')
                st.write(content)

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
                # Bouton et affichage à la suite (même logique que fiches générées)
                render_fiche_block(content, meta, key_prefix="prompt_generated")

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
            # Ici on affiche directement, mais avec render_fiche_block (donc bouton fonctionne)
            generate_from_rpo_pipeline(return_results=False)
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
                header = f"**{r.get('titre_poste','(sans titre)')}** — {r.get('localisation','')}"
                if r.get("salaire"):
                    header += f"  \n💶 Rémunération (TJM/Sal.) : {r.get('salaire','')}"
                st.markdown(header + f"  \nClient: {r.get('client','')}  \n🕒 Générée le: {r.get('generated_at','')}")
                file_path = r.get("filepath","")
                fiche_content = ""
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        fiche_content = f.read()
                    st.text_area("Aperçu", fiche_content[:1000], height=150, key=f"preview_{r.get('filename','')}")
                    # Bouton "Créer la requête" sous chaque fiche (logique existante)
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
