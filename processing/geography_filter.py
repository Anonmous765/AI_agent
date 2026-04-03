import spacy
from spacy.pipeline import EntityRuler

nlp = spacy.load("en_core_web_trf")

ruler = nlp.add_pipe("entity_ruler", before="ner")



if __name__ == "__main__":
    doc = nlp("Major flooding in Louisville, KY.")
    print("\n".join(f"{ent.text:<20} {ent.label_:<12} " for ent in doc.ents))