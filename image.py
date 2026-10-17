import os
import uuid

from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Modèle Gemini qui crée une image à partir d'un texte (niveau gratuit)
MODEL_IMAGE = "gemini-2.5-flash-image"

# Dossier où on enregistre les images créées
DOSSIER_IMAGES = "images"


def generer_image(description):
    """Crée une image avec Gemini, l'enregistre dans le dossier 'images'.

    Renvoie (chemin, texte) :
      - chemin : chemin de l'image créée (ou None si Gemini n'a pas renvoyé d'image)
      - texte  : texte éventuel renvoyé par Gemini (ex : refus, explication)
    """
    response = client.models.generate_content(
        model=MODEL_IMAGE,
        contents=description,
    )

    chemin = None
    texte = ""
    parties = []
    if response.candidates and response.candidates[0].content:
        parties = response.candidates[0].content.parts or []

    for partie in parties:
        if partie.inline_data and partie.inline_data.data:
            os.makedirs(DOSSIER_IMAGES, exist_ok=True)
            chemin = os.path.join(DOSSIER_IMAGES, f"{uuid.uuid4().hex}.png")
            with open(chemin, "wb") as f:
                f.write(partie.inline_data.data)
        elif partie.text:
            texte += partie.text

    return chemin, texte.strip()