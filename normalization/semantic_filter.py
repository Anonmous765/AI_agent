from sentence_transformers import SentenceTransformer, util
import torch

model = SentenceTransformer("all-MiniLM-L6-v2")

PROMPTS = {
    "flood": "flooding flash flood rising river water rescue flood warning",
    "tornado": "tornado severe thunderstorm wind damage funnel cloud storm emergency",
    "outage": "power outage utility disruption downed lines transformer failure",
    "water": "boil water advisory water contamination water main break",
    "evacuation": "evacuation shelter emergency response road closure public safety"
}

labels = list(PROMPTS.keys())
prompt_texts = list(PROMPTS.values())

prompt_embs = model.encode(
    prompt_texts,
    convert_to_tensor=True,
    normalize_embeddings=True
)

def classify_article(title: str, summary: str, threshold: float=0.40) -> dict:
    """
    Classify an article based on its title and summary.
    :param title:
    :param summary:
    :param threshold:
    :return:
    """

    text = f"{title}. {summary}"
    article_emb = model.encode(
        text,
        convert_to_tensor=True,
        normalize_embeddings=True
    )

    scores = util.cos_sim(article_emb, prompt_embs)[0]
    best_idx = torch.argmax(scores).item()
    best_label = labels[best_idx]
    best_score = scores[best_idx].item()

    return {
        "relevant": best_score >= threshold,
        "label": best_label,
        "score": best_score,
        "scores": {labels[i]: scores[i].item() for i in range(len(labels))}
    }