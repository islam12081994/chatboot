
import os
import uuid

from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()
client = InferenceClient(token=os.getenv("HF_TOKEN"))

# Modèle qui crée une image à partir d'un texte
MODEL_IMAGE = "Qwen/Qwen-Image"

# Dossier où on enregistre les images créées
DOSSIER_IMAGES = "images"


def generer_image(description):
    """Crée une image, l'enregistre dans le dossier 'images' et renvoie son chemin."""
    image = client.text_to_image(description, model=MODEL_IMAGE)

    os.makedirs(DOSSIER_IMAGES, exist_ok=True)
    chemin = os.path.join(DOSSIER_IMAGES, f"{uuid.uuid4().hex}.png")
    image.save(chemin)
    return chemin