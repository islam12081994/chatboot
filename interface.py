import os

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

import auth
import db

load_dotenv()
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)
MODEL = "openai/gpt-oss-120b"

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

# =====================================================================
# 2) CHATBOT (utilisateur connecté)
# =====================================================================
st.title("🤖 welcome to chatboot")

# --- Conversation courante ---
if "conv_id" not in st.session_state:
    convs = db.list_conversations(user_id)
    st.session_state.conv_id = convs[0]["id"] if convs else db.create_conversation(user_id)

# --- Barre latérale ---
with st.sidebar:
    st.title("💬 Assistant RAG")
    st.caption(f"👤 Connecté : **{st.session_state.username}**")

    if st.button("🚪 Se déconnecter", use_container_width=True):
        for cle in ["user_id", "username", "conv_id", "editing_id"]:
            st.session_state.pop(cle, None)
        st.rerun()

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
    if fichiers:
        st.success(f"{len(fichiers)} document(s) chargé(s)")
    else:
        st.info("Aucun document chargé")

# --- Afficher les anciens messages (depuis SQLite) ---
conv_id = st.session_state.conv_id
messages = db.get_messages(conv_id)

for msg in messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# --- Zone pour écrire la question ---
question = st.chat_input("Écris ta question ici...")

if question:
    # Le titre de la conversation = début de la première question
    if not messages:
        db.rename_conversation(conv_id, question[:40], user_id)

    db.add_message(conv_id, "user", question)
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Réflexion..."):
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=db.get_messages(conv_id),
                )
                answer = response.choices[0].message.content
            except Exception as e:
                answer = f"⚠️ Erreur lors de l'appel à l'API : {e}"
            st.write(answer)

    db.add_message(conv_id, "assistant", answer)
    st.rerun()