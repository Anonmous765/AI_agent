import spacy
from spacy.pipeline import EntityRuler

nlp = spacy.load("en_core_web_sm")

ruler = nlp.add_pipe("entity_ruler", before="ner")
ruler.add_patterns([
    {"label": "KY_ROAD", "pattern": [{"TEXT": {"REGEX": r"^I-\d+$"}}]},
    {"label": "KY_ROAD", "pattern": [{"TEXT": {"REGEX": r"^KY-\d+$"}}]},
    {"label": "KY_ROAD", "pattern": [{"TEXT": {"REGEX": r"^US-\d+$"}}]},
])
