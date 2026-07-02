from sentence_transformers import SentenceTransformer, util
import torch

from ky_damage_agent.schemas.schema import RssNormalizedSignal

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
    "shooting": "shooting gunshot gunfire shot fired victim wounded killed gun violence armed suspect",
    "crime": "arrest warrant fugitive armed dangerous suspect wanted manhunt law enforcement police",
    "violence": "homicide murder stabbing assault robbery attack violent crime victim",
    "active_threat": "active shooter lockdown shelter in place threat armed standoff hostage barricade",
    "missing_person": "missing person amber alert endangered missing child abduction search rescue",
}

labels = list(PROMPTS.keys())
prompt_texts = list(PROMPTS.values())

prompt_embs = model.encode(
    prompt_texts,
    convert_to_tensor=True,
    normalize_embeddings=True
)


def classify_article(signal: RssNormalizedSignal, threshold: float = 0.40) -> dict:
    """
    Classify an article based on its normalized RSS rss_signal.
    :param signal:
    :param threshold:
    :return:
    """

    text = signal.raw_text
    article_emb = model.encode(
        text,
        convert_to_tensor=True,
        normalize_embeddings=True
    )

    topic_scores = util.cos_sim(article_emb, prompt_embs)[0]
    best_idx = torch.argmax(topic_scores).item()
    best_label = labels[best_idx]
    best_score = topic_scores[best_idx].item()

    return {
        "relevant": (best_score >= threshold),
        "label": best_label,
        "score": best_score,
        "topic_scores": {labels[i]: topic_scores[i].item() for i in range(len(labels))},
        "article_emb": article_emb.tolist()
    }
