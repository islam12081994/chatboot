import base64
import io
import os
import re
import uuid

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

import auth
import db
import rag

load_dotenv()
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)
MODEL = "openai/gpt-oss-120b"
MODEL_VOC = "whisper-large-v3"
# Modèle de vision (lecture d'images). Tu peux aussi essayer "qwen/qwen3.8-27b"
MODEL_VISION = "qwen/qwen3.8-27b"
DOSSIER_IMAGES = "images_envoyees"

# Les 3 modes que l'utilisateur peut choisir
MODE_TEXTE = "💬 Texte (GPT OSS 120B)"
MODE_VOCAL = "🎤 Vocal (Whisper large v3)"
MODE_VISION = "🖼️ Vision (Qwen 3.6 27B)"

st.set_page_config(page_title="islam chatboot", page_icon="🐉")

# Crée les tables SQLite si besoin
auth.init_db()
db.init_db()


# =====================================================================
# 1) PAGE D'AUTHENTIFICATION
# =====================================================================
def page_authentification():
    st.title("🔐 Authentification")
    tab_login, tab_register = st.tabs(["Connexion", "Créer un compte"])

    with tab_login:
        with st.form("form_login"):
            username = st.text_input("Nom d'utilisateur")
            password = st.text_input("Mot de passe", type="password")
            envoyer = st.form_submit_button("Se connecter", use_container_width=True)
        if envoyer:
            if not username.strip() or not password:
                st.warning("Remplis tous les champs.")
            else:
                ok, msg = auth.login_user(username.strip(), password)
                if ok:
                    st.session_state.username = username.strip()
                    st.session_state.user_id = auth.get_user_id(username.strip())
                    st.rerun()
                else:
                    st.error(msg)

    with tab_register:
        with st.form("form_register"):
            new_user = st.text_input("Nom d'utilisateur", key="reg_user")
            new_pass = st.text_input("Mot de passe (6 caractères min.)", type="password", key="reg_pass")
            confirm = st.text_input("Confirmer le mot de passe", type="password", key="reg_confirm")
            creer = st.form_submit_button("Créer le compte", use_container_width=True)
        if creer:
            if not new_user.strip() or not new_pass:
                st.warning("Remplis tous les champs.")
            elif len(new_pass) < 6:
                st.warning("Le mot de passe doit contenir au moins 6 caractères.")
            elif new_pass != confirm:
                st.warning("Les mots de passe ne correspondent pas.")
            else:
                ok, msg = auth.register_user(new_user.strip(), new_pass)
                if ok:
                    st.success(msg + " Tu peux maintenant te connecter.")
                else:
                    st.error(msg)


# Si l'utilisateur n'est pas connecté : on affiche la page de connexion et on s'arrête
if "user_id" not in st.session_state:
    page_authentification()
    st.stop()

user_id = st.session_state.user_id


def afficher_message(contenu):
    """Affiche du texte. Si le message commence par IMAGE:chemin, affiche aussi l'image
    (le texte éventuel est placé après le premier retour à la ligne)."""
    if contenu.startswith("IMAGE:"):
        premiere_ligne, _, texte = contenu.partition("\n")
        chemin = premiere_ligne[len("IMAGE:"):]
        if os.path.exists(chemin):
            st.image(chemin)
        else:
            st.write("🖼️ (image introuvable)")
        if texte:
            st.write(texte)
    else:
        st.write(contenu)


def transcrire(audio_file) -> str:
    """Transforme l'enregistrement du micro en texte avec Whisper (Groq)."""
    resultat = client.audio.transcriptions.create(
        model=MODEL_VOC,
        file=("audio.wav", audio_file.getvalue()),
        # language="fr",  # décommente pour forcer le français
    )
    return resultat.text.strip()


def preparer_image(source) -> bytes:
    """Ouvre l'image, la réduit (1568 px max) et la convertit en JPEG
    pour rester sous la limite de taille de l'API."""
    img = Image.open(source).convert("RGB")
    img.thumbnail((1568, 1568))
    tampon = io.BytesIO()
    img.save(tampon, format="JPEG", quality=85)
    return tampon.getvalue()


def sauvegarder_image(data: bytes) -> str:
    """Enregistre l'image sur le disque et retourne son chemin."""
    os.makedirs(DOSSIER_IMAGES, exist_ok=True)
    chemin = os.path.join(DOSSIER_IMAGES, f"{uuid.uuid4().hex}.jpg")
    with open(chemin, "wb") as f:
        f.write(data)
    return chemin


def derniere_image(liste_messages):
    """Retourne les octets de la dernière image envoyée par l'utilisateur dans la conversation."""
    for m in reversed(liste_messages):
        if m["role"] == "user" and m["content"].startswith("IMAGE:"):
            chemin = m["content"].partition("\n")[0][len("IMAGE:"):]
            if os.path.exists(chemin):
                with open(chemin, "rb") as f:
                    return f.read()
    return None


def convertir_historique(liste_messages):
    """Remplace les images de l'historique par un petit texte (pour les modèles texte)."""
    resultat = []
    for m in liste_messages:
        contenu = m["content"]
        if contenu.startswith("IMAGE:"):
            _, _, texte = contenu.partition("\n")
            contenu = "[image jointe] " + texte if texte else "[image jointe]"
        resultat.append({"role": m["role"], "content": contenu})
    return resultat


def nettoyer_reponse(texte: str) -> str:
    """Retire un éventuel bloc <think>...</think> (raisonnement) de la réponse."""
    return re.sub(r"<think>.*?</think>", "", texte or "", flags=re.DOTALL).strip()


# =====================================================================
# 2) CHATBOT (utilisateur connecté)
# =====================================================================
st.title("🤖 welcome to chatboot")

# --- Conversation courante ---
if "conv_id" not in st.session_state:
    convs = db.list_conversations(user_id)
    st.session_state.conv_id = convs[0]["id"] if convs else db.create_conversation(user_id)

# Compteur pour vider l'enregistreur audio après chaque envoi
if "audio_n" not in st.session_state:
    st.session_state.audio_n = 0

# Compteur pour vider le champ d'import d'image après chaque envoi
if "img_n" not in st.session_state:
    st.session_state.img_n = 0

# --- Barre latérale ---
with st.sidebar:
    st.title("💬 Assistant RAG")
    st.caption(f"👤 Connecté : **{st.session_state.username}**")

    if st.button("🚪 Se déconnecter", use_container_width=True):
        for cle in ["user_id", "username", "conv_id", "editing_id", "fichiers_ajoutes"]:
            st.session_state.pop(cle, None)
        st.rerun()

    st.divider()

    # --- Choix du mode ---
    mode = st.radio("🧠 Mode", [MODE_TEXTE, MODE_VOCAL, MODE_VISION])

    st.divider()

    if st.button("➕ Nouvelle conversation", use_container_width=True):
        st.session_state.conv_id = db.create_conversation(user_id)
        st.rerun()

    st.subheader("🕘 Historique")
    for conv in db.list_conversations(user_id):
        est_active = conv["id"] == st.session_state.conv_id

        if st.session_state.get("editing_id") == conv["id"]:
            # Mode édition : champ de texte + Enregistrer / Annuler
            nouveau_titre = st.text_input(
                "Nouveau titre",
                value=conv["title"],
                max_chars=60,
                key=f"input_{conv['id']}",
            )
            c1, c2 = st.columns(2)
            if c1.button("✅ Enregistrer", key=f"save_{conv['id']}", use_container_width=True):
                if nouveau_titre.strip():
                    db.rename_conversation(conv["id"], nouveau_titre.strip(), user_id)
                    st.session_state.editing_id = None
                    st.rerun()
                else:
                    st.warning("Le titre ne peut pas être vide.")
            if c2.button("❌ Annuler", key=f"cancel_{conv['id']}", use_container_width=True):
                st.session_state.editing_id = None
                st.rerun()
        else:
            # Mode normal : titre | ✏️ | 🗑
            col1, col2, col3 = st.columns([5, 1, 1])
            if col1.button(
                conv["title"],
                key=f"open_{conv['id']}",
                use_container_width=True,
                type="primary" if est_active else "secondary",
            ):
                st.session_state.conv_id = conv["id"]
                st.rerun()
            if col2.button("✏️", key=f"edit_{conv['id']}"):
                st.session_state.editing_id = conv["id"]
                st.rerun()
            if col3.button("🗑", key=f"del_{conv['id']}"):
                db.delete_conversation(conv["id"], user_id)
                if conv["id"] == st.session_state.conv_id:
                    convs = db.list_conversations(user_id)
                    st.session_state.conv_id = (
                        convs[0]["id"] if convs else db.create_conversation(user_id)
                    )
                st.rerun()

    st.divider()

    st.subheader("📁 Documents")
    fichiers = st.file_uploader(
        "Importer un fichier",
        type=["pdf", "txt"],
        accept_multiple_files=True,
    )
    # Ajouter les fichiers dans ChromaDB (une seule fois par fichier)
    if "fichiers_ajoutes" not in st.session_state:
        st.session_state.fichiers_ajoutes = []
    for fichier in fichiers or []:
        if fichier.name not in st.session_state.fichiers_ajoutes:
            with st.spinner(f"Lecture de {fichier.name}..."):
                nb = rag.ajouter_document(user_id, fichier)
            st.session_state.fichiers_ajoutes.append(fichier.name)
            st.success(f"{fichier.name} : {nb} morceaux ajoutés")

    nb_total = rag.nombre_morceaux(user_id)
    if nb_total > 0:
        st.info(f"📚 {nb_total} morceaux dans ta base")
        if st.button("🗑 Vider mes documents", use_container_width=True):
            rag.supprimer_documents(user_id)
            st.session_state.fichiers_ajoutes = []
            st.rerun()
    else:
        st.info("Aucun document chargé")

# --- Afficher les anciens messages (depuis SQLite) ---
conv_id = st.session_state.conv_id
messages = db.get_messages(conv_id)

for msg in messages:
    with st.chat_message(msg["role"]):
        afficher_message(msg["content"])

# --- Zone pour écrire (ou dire) la question ---
question = st.chat_input("Écris ta question ici...")

if mode == MODE_VOCAL:
    audio = st.audio_input(
        "🎤 Clique sur le micro, parle, puis arrête l'enregistrement",
        key=f"audio_{st.session_state.audio_n}",
    )
    if audio is not None and not question:
        erreur = False
        with st.spinner("Transcription de ta voix..."):
            try:
                texte = transcrire(audio)
            except Exception as e:
                texte = ""
                erreur = True
                st.error(f"⚠️ Erreur de transcription : {e}")
        # On vide l'enregistreur pour ne pas retraiter le même audio
        st.session_state.audio_n += 1
        if texte:
            question = texte
        elif not erreur:
            st.warning("Je n'ai rien entendu, réessaie.")

# --- Mode VISION : import d'une image à analyser ---
image_data = None
nouvelle_image = False

if mode == MODE_VISION:
    fichier_image = st.file_uploader(
        "🖼️ Image à analyser (png, jpg, webp)",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"img_{st.session_state.img_n}",
    )
    if question:
        if fichier_image is not None:
            try:
                image_data = preparer_image(fichier_image)
                nouvelle_image = True
            except Exception as e:
                st.error(f"⚠️ Image illisible : {e}")
                question = None
        else:
            # Pas de nouvelle image : on réutilise la dernière de la conversation
            image_data = derniere_image(messages)
            if image_data is None:
                st.warning("Importe d'abord une image à analyser.")
                question = None

if question:
    # Le titre de la conversation = début de la première question
    if not messages:
        db.rename_conversation(conv_id, question[:40], user_id)

    contenu_user = question
    if nouvelle_image:
        contenu_user = f"IMAGE:{sauvegarder_image(image_data)}\n{question}"

    db.add_message(conv_id, "user", contenu_user)
    with st.chat_message("user"):
        afficher_message(contenu_user)

    with st.chat_message("assistant"):
        if mode == MODE_VISION:
            # ---------- Modèle VISION (Groq + Qwen) ----------
            with st.spinner("Analyse de l'image..."):
                try:
                    historique = convertir_historique(messages)
                    url_image = "data:image/jpeg;base64," + base64.b64encode(image_data).decode()
                    historique.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": question},
                            {"type": "image_url", "image_url": {"url": url_image}},
                        ],
                    })
                    response = client.chat.completions.create(
                        model=MODEL_VISION,
                        messages=historique,
                    )
                    answer = nettoyer_reponse(response.choices[0].message.content)
                except Exception as e:
                    answer = f"⚠️ Erreur lors de l'analyse de l'image : {e}"
        else:
            # ---------- Modèle TEXTE (Groq + RAG) ----------
            with st.spinner("Réflexion..."):
                try:
                    historique = convertir_historique(db.get_messages(conv_id))

                    # RAG : on cherche les morceaux utiles dans les documents
                    morceaux = rag.chercher(user_id, question)
                    if morceaux:
                        contexte = "\n\n".join(morceaux)
                        systeme = {
                            "role": "system",
                            "content": "Réponds en utilisant ces extraits de documents "
                            "si c'est utile :\n\n" + contexte,
                        }
                        historique = [systeme] + historique

                    response = client.chat.completions.create(
                        model=MODEL,
                        messages=historique,
                    )
                    answer = response.choices[0].message.content
                except Exception as e:
                    answer = f"⚠️ Erreur lors de l'appel à l'API : {e}"
        afficher_message(answer)

    db.add_message(conv_id, "assistant", answer)
    if nouvelle_image:
        st.session_state.img_n += 1  # vide le champ d'import d'image
    st.rerun()