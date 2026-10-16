import os

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

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

# Les 2 modes que l'utilisateur peut choisir
MODE_TEXTE = "💬 Texte (GPT OSS 120B)"
MODE_VOCAL = "🎤 Vocal (Whisper large v3)"

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
    """Affiche du texte (ou une ancienne image si le message commence par IMAGE:)"""
    if contenu.startswith("IMAGE:"):
        chemin = contenu[len("IMAGE:"):]
        if os.path.exists(chemin):
            st.image(chemin)
        else:
            st.write("🖼️ (image introuvable)")
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
    mode = st.radio("🧠 Mode", [MODE_TEXTE, MODE_VOCAL])

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

if question:
    # Le titre de la conversation = début de la première question
    if not messages:
        db.rename_conversation(conv_id, question[:40], user_id)

    db.add_message(conv_id, "user", question)
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        # ---------- Modèle TEXTE (Groq + RAG) ----------
        with st.spinner("Réflexion..."):
            try:
                # On remplace les anciennes images de l'historique par un petit texte
                historique = []
                for m in db.get_messages(conv_id):
                    if m["content"].startswith("IMAGE:"):
                        historique.append({"role": m["role"], "content": "[image générée]"})
                    else:
                        historique.append(m)

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
    st.rerun()