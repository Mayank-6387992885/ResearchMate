"""Pre-loaded sample papers seeded for newly registered ResearchMate users."""

from uuid import uuid4

from sqlalchemy.orm import Session

from models.research_paper import ResearchPaper

SAMPLE_PAPERS = [
    {
        "title": "Attention Is All You Need",
        "filename": "attention-is-all-you-need.pdf",
        "pages": 15,
        "category": "Technology",
        "is_saved": True,
        "summary": (
            "## Overview\n"
            "Introduces the Transformer, a sequence transduction architecture based "
            "entirely on self-attention mechanisms, dispensing with recurrence and "
            "convolutions.\n\n"
            "## Key Contributions\n"
            "- **Scaled Dot-Product Attention & Multi-Head Attention**: Allows the model "
            "to jointly attend to information from different representation subspaces.\n"
            "- **Positional Encoding**: Injects sequence order information using sine "
            "and cosine functions of different frequencies.\n"
            "- **Parallelizable Training**: Eliminates sequential recurrent dependencies, "
            "enabling substantially greater parallelization.\n\n"
            "## Results & Impact\n"
            "Achieved 28.4 BLEU on WMT 2014 English-to-German and 41.8 BLEU on "
            "English-to-French translation with significantly lower training cost."
        ),
        "classification": {
            "domain": "Computer Science & Information Technology",
            "subfield": "Natural Language Processing",
            "topics": ["Transformers", "Self-Attention", "Sequence-to-Sequence", "Machine Translation"],
            "metrics": {
                "reading_time_minutes": 25,
                "key_datasets": ["WMT 2014 EN-DE", "WMT 2014 EN-FR"],
                "bleu_en_de": 28.4,
                "bleu_en_fr": 41.8,
            },
        },
    },
    {
        "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "filename": "retrieval-augmented-generation.pdf",
        "pages": 19,
        "category": "Technology",
        "is_saved": True,
        "summary": (
            "## Overview\n"
            "Combines pre-trained parametric sequence-to-sequence models with a "
            "non-parametric dense vector index of Wikipedia accessed via a neural "
            "retriever (DPR).\n\n"
            "## Key Contributions\n"
            "- **RAG-Sequence & RAG-Token**: Two formulations that marginalize over "
            "retrieved latent documents either per-sequence or per-token.\n"
            "- **End-to-End Differentiable Retrieval**: Jointly trains the query encoder "
            "and generator without requiring document-level supervision.\n"
            "- **Updatable Knowledge**: Enables updating world knowledge by swapping the "
            "non-parametric index without retraining the generator.\n\n"
            "## Results & Impact\n"
            "Set state-of-the-art results on open-domain QA benchmarks (Natural Questions, "
            "TriviaQA, WebQuestions) while generating more factual and specific responses."
        ),
        "classification": {
            "domain": "Computer Science & Information Technology",
            "subfield": "Natural Language Processing",
            "topics": ["Retrieval-Augmented Generation", "Open-Domain QA", "Dense Retrieval", "Knowledge Grounding"],
            "metrics": {
                "reading_time_minutes": 30,
                "key_datasets": ["Natural Questions", "TriviaQA", "FEVER"],
                "nq_exact_match": 44.5,
            },
        },
    },
]


def seed_sample_papers(db: Session, user_id: int) -> list[ResearchPaper]:
    """Seed pre-summarized sample papers for a user if they currently have 0 papers.

    Idempotent: returns an empty list if the user already has any papers.
    """
    has_papers = (
        db.query(ResearchPaper.id)
        .filter(ResearchPaper.user_id == user_id)
        .first()
        is not None
    )
    if has_papers:
        return []

    created: list[ResearchPaper] = []
    for sample in SAMPLE_PAPERS:
        stored_filename = f"sample-{uuid4().hex}.pdf"
        paper = ResearchPaper(
            title=sample["title"],
            filename=sample["filename"],
            stored_filename=stored_filename,
            file_path=f"sample/user-{user_id}/{stored_filename}",
            summary=sample["summary"],
            pages=sample["pages"],
            is_saved=sample["is_saved"],
            category=sample["category"],
            classification=dict(sample["classification"]),
            user_id=user_id,
        )
        created.append(paper)

    db.add_all(created)
    db.flush()
    return created
