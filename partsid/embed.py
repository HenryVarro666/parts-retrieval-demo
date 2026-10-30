"""Off-the-shelf encoders, no fine-tuning.

ImageEncoder: SigLIP image tower, used on its own for image-to-image similarity.
TextEncoder: BGE-small sentence embeddings.
Both return L2-normalised float32 numpy rows, so a dot product is cosine similarity.
"""
import numpy as np
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor, AutoTokenizer

DEFAULT_IMAGE_MODEL = "google/siglip-base-patch16-224"
DEFAULT_TEXT_MODEL = "BAAI/bge-small-en-v1.5"
# Hugging Face commits of the default models, the ones results/ was measured with.
# Any other model id loads the current main revision.
REVISIONS = {
    DEFAULT_IMAGE_MODEL: "7fd15f0689c79d79e38b1c2e2e2370a7bf2761ed",
    DEFAULT_TEXT_MODEL: "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
}


class ImageEncoder:
    def __init__(self, device: str, model_id: str = DEFAULT_IMAGE_MODEL):
        self.device = device
        self.model_id = model_id
        self.revision = REVISIONS.get(model_id, "main")
        self.processor = AutoProcessor.from_pretrained(model_id, revision=self.revision)
        self.model = AutoModel.from_pretrained(model_id, revision=self.revision).to(device).eval()

    @torch.inference_mode()
    def encode(self, images: list[Image.Image]) -> np.ndarray:
        inputs = self.processor(images=[im.convert("RGB") for im in images], return_tensors="pt").to(self.device)
        feats = self.model.get_image_features(**inputs)
        if not torch.is_tensor(feats):  # newer transformers return a ModelOutput
            feats = feats.pooler_output
        return torch.nn.functional.normalize(feats, dim=-1).float().cpu().numpy()


class TextEncoder:
    # BGE's recommended instruction for short retrieval queries
    QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

    def __init__(self, device: str, model_id: str = DEFAULT_TEXT_MODEL):
        self.device = device
        self.model_id = model_id
        self.revision = REVISIONS.get(model_id, "main")
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, revision=self.revision)
        self.model = AutoModel.from_pretrained(model_id, revision=self.revision).to(device).eval()

    @torch.inference_mode()
    def encode(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        if is_query:
            texts = [self.QUERY_PREFIX + t for t in texts]
        batch = self.tokenizer(texts, padding=True, truncation=True, max_length=256, return_tensors="pt").to(self.device)
        cls = self.model(**batch).last_hidden_state[:, 0]  # BGE uses CLS pooling
        return torch.nn.functional.normalize(cls, dim=-1).float().cpu().numpy()
