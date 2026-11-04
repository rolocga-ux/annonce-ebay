import json
import re
import requests
import streamlit as st

BASE = "https://generativelanguage.googleapis.com/v1beta"
MODELES_SECOURS = ["gemini-3.8-flash", "gemini-3.6-flash",
                   "gemini-3.5-flash-lite", "gemini-2.5-flash"]
GARANTIES = [
    "Aucune garantie commerciale (garantie légale uniquement)",
    "30 jours", "3 mois", "6 mois", "1 an", "2 ans", "Autre…",
]
CHAMPS = ["titre", "sous_titre", "categorie", "caracteristiques",
          "description", "livraison", "mots_cles", "conseil_prix"]

st.set_page_config(page_title="Annonce eBay en 1 clic", page_icon="🏷️")
st.title("🏷️ Annonce eBay en 1 clic")


def nettoyer(e):
    """Cache la clé API dans les messages d'erreur."""
    return re.sub(r"key=[^&\s\"']+", "key=***", str(e))


# ---------- Mot de passe ----------
mdp = st.secrets.get("APP_PASSWORD", "")
if mdp:
    if st.text_input("Mot de passe", type="password") != mdp:
        st.info("Entre le mot de passe pour utiliser l'application.")
        st.stop()


# ---------- Choix automatique du modèle Gemini ----------
@st.cache_data(ttl=3600)
def modeles_disponibles(cle):
    try:
        r = requests.get(f"{BASE}/models", params={"key": cle, "pageSize": 200}, timeout=30)
        r.raise_for_status()
        noms = []
        for m in r.json().get("models", []):
            n = m["name"].replace("models/", "")
            if ("generateContent" in m.get("supportedGenerationMethods", [])
                    and "flash" in n
                    and not any(x in n for x in ("image", "tts", "audio", "live",
                                                  "embedding", "preview", "exp"))):
                noms.append(n)
        return sorted(noms, reverse=True)
    except Exception:
        return []


def liste_modeles():
    cle = st.secrets["GEMINI_API_KEY"]
    out = []
    for n in modeles_disponibles(cle) + MODELES_SECOURS:
        if n not in out:
            out.append(n)
    return out[:6]

# ---------- Réglages ----------
st.subheader("⚙️ Tes réglages")
c1, c2 = st.columns(2)
etat = c1.radio("État", ["Neuf", "Occasion"], horizontal=True)
prix = c2.number_input("Prix (€)", min_value=0.0, value=0.0, step=0.5, format="%.2f")
garantie = st.selectbox("Garantie", GARANTIES)
if garantie == "Autre…":
    garantie = st.text_input("Décris ta garantie")

lien = st.text_input("Lien du produit (pour mémoire, facultatif)")
texte = st.text_area("Colle ici le texte de la page produit", height=220)


def generer():
    prompt = f"""Tu es expert vendeur eBay France. Rédige une annonce eBay complète,
optimisée pour le référencement et honnête, avec tes propres mots (ne recopie pas
le texte source). N'invente AUCUNE caractéristique absente du texte.

Réglages imposés par le vendeur :
- État : {etat}
- Prix : {prix if prix > 0 else "non précisé, propose un prix"} €
- Garantie : {garantie}

Lien de référence : {lien or "aucun"}
Texte de la page produit :
{texte}

Règles :
- titre : 80 caractères maximum, mots-clés les plus recherchés en premier ;
- si l'état est Occasion, mentionne-le clairement et demande au vendeur de
  décrire les défauts dans la description ; si Neuf, ne parle pas d'usure ;
- la description et la livraison doivent citer la garantie choisie ;
- caracteristiques : une ligne par caractéristique, au format "Nom : valeur".

Réponds UNIQUEMENT avec un JSON de cette forme :
{{"titre": "", "sous_titre": "", "categorie": "", "caracteristiques": "",
"description": "", "livraison": "", "mots_cles": "", "conseil_prix": ""}}"""
    cle = st.secrets["GEMINI_API_KEY"]
    dernier = "aucun modèle disponible"
    for modele in liste_modeles():
        try:
            r = requests.post(
                f"{BASE}/models/{modele}:generateContent",
                params={"key": cle},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
                timeout=90,
            )
        except requests.RequestException as e:
            dernier = nettoyer(e)
            continue
        if r.status_code in (404, 429, 500, 503):
            dernier = f"{modele} : erreur {r.status_code}"
            continue
        if r.status_code in (400, 401, 403):
            raise RuntimeError(
                f"Clé API refusée (erreur {r.status_code}). Vérifie GEMINI_API_KEY dans les Secrets.")
        r.raise_for_status()
        t = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(t[t.find("{"): t.rfind("}") + 1])
    raise RuntimeError(
        "Aucun modèle n'a répondu (" + dernier + "). Si c'est une erreur 429, "
        "la limite gratuite est atteinte : réessaie dans une minute.")


if st.button("Créer mon annonce", type="primary", use_container_width=True):
    if not texte.strip():
        st.warning("Colle d'abord le texte de la page produit.")
    elif texte.strip().startswith("http") and len(texte.split()) < 5:
        st.warning("Tu as collé un lien. Copie plutôt le titre, les détails et la description de la page produit.")
    else:
        with st.spinner("Création de l'annonce…"):
            try:
                data = generer()
                for k in CHAMPS:
                    st.session_state[k] = str(data.get(k, ""))
                st.session_state["pret"] = True
            except Exception as e:
                st.error("Erreur : " + nettoyer(e))

# ---------- Annonce modifiable ----------
if st.session_state.get("pret"):
    st.divider()
    st.subheader("📝 Ton annonce (tout est modifiable)")
    st.text_input("Titre", key="titre", max_chars=80)
    st.text_input("Sous-titre", key="sous_titre")
    st.text_input("Catégorie conseillée", key="categorie")
    st.text_area("Caractéristiques", key="caracteristiques", height=150)
    st.text_area("Description", key="description", height=300)
    st.text_area("Livraison et retours", key="livraison", height=100)
    st.text_input("Mots-clés", key="mots_cles")
    st.caption("💶 Conseil de prix : " + st.session_state.get("conseil_prix", ""))

    s = st.session_state
    complet = (
        f"TITRE\n{s['titre']}\n\nSOUS-TITRE\n{s['sous_titre']}\n\n"
        f"CATÉGORIE\n{s['categorie']}\n\nÉTAT\n{etat}\n\n"
        f"PRIX\n{prix:.2f} €\n\nGARANTIE\n{garantie}\n\n"
        f"CARACTÉRISTIQUES\n{s['caracteristiques']}\n\n"
        f"DESCRIPTION\n{s['description']}\n\n"
        f"LIVRAISON ET RETOURS\n{s['livraison']}\n\n"
        f"MOTS-CLÉS\n{s['mots_cles']}"
    )
    st.subheader("📋 Annonce complète à copier")
    st.code(complet, language=None)
