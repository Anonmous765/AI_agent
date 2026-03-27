from sentence_transformers import SentenceTransformer, util
import torch
import spacy
import geopy

model = SentenceTransformer("all-MiniLM-L6-v2")

PROMPTS = {
    "flood": "flooding flash flood rising river water rescue flood warning",
    "tornado": "tornado severe thunderstorm wind damage funnel cloud storm emergency",
    "outage": "power outage utility disruption downed lines transformer failure",
    "water": "boil water advisory water contamination water main break",
    "evacuation": "evacuation shelter emergency response road closure public safety",
    "traffic": "vehicle fire road closure lane blocked accident crash highway interstate emergency detour",
    "fire": "structure fire building fire wildfire brush fire firefighters blaze smoke",
    "hazmat": "hazardous materials chemical spill gas leak explosion industrial accident",
    "infrastructure": "bridge collapse dam failure sinkhole landslide road damage highway closed",
}

KY_LOCATIONS = [
    "Kentucky Louisville Lexington Bowling Green Owensboro Covington",
    "Jefferson County Fayette County Warren County Ohio County",
    "Ohio River Kentucky River Cumberland River Lake Cumberland",
    "KY Tennessee Indiana Ohio border region midwest"
]

labels = list(PROMPTS.keys())
prompt_texts = list(PROMPTS.values())

prompt_embs = model.encode(
    prompt_texts,
    convert_to_tensor=True,
    normalize_embeddings=True
)

location_embs = model.encode(
    KY_LOCATIONS,
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

    # Compute cosine similarity between article and prompt embeddings
    topic_scores = util.cos_sim(article_emb, prompt_embs)[0]
    best_idx = torch.argmax(topic_scores).item()
    best_label = labels[best_idx]
    best_score = topic_scores[best_idx].item()

    # Compute cosine similarity between article and location embeddings

    location_scores = util.cos_sim(article_emb, location_embs)[0]
    location_score = torch.max(location_scores).item()

    return {
        "relevant": (best_score >= threshold),
        "label": best_label,
        "score": best_score,
        "location_score": location_score,
        "topic_scores": {labels[i]: topic_scores[i].item() for i in range(len(labels))},
        "article_emb": article_emb.tolist()
    }