"""Research paper classification taxonomy and local-model classifier."""
import json
import re
from typing import Any, Callable

import requests

from summarizer import stream_ollama

RESEARCH_DOMAINS = {
    "Computer Science & Information Technology": [
        "Artificial Intelligence", "Machine Learning", "Deep Learning",
        "Natural Language Processing", "Computer Vision", "Data Science",
        "Big Data", "Cloud Computing", "Cybersecurity", "Blockchain",
        "Software Engineering", "Computer Networks", "Internet of Things",
        "Human-Computer Interaction", "Distributed Systems", "Robotics",
        "Quantum Computing",
    ],
    "Engineering & Technology": [
        "Mechanical Engineering", "Electrical Engineering",
        "Electronics Engineering", "Civil Engineering", "Chemical Engineering",
        "Aerospace Engineering", "Automotive Engineering",
        "Biomedical Engineering", "Industrial Engineering",
        "Robotics Engineering", "Mechatronics", "Materials Engineering",
        "Environmental Engineering", "Telecommunications",
    ],
    "Medical & Health Sciences": [
        "Medicine", "Nursing", "Public Health", "Pharmacology",
        "Clinical Research", "Medical Imaging", "Medical Diagnostics",
        "Genetics", "Immunology", "Neuroscience", "Oncology", "Cardiology",
        "Epidemiology", "Bioinformatics", "Digital Health", "Healthcare AI",
    ],
    "Biological & Life Sciences": [
        "Biotechnology", "Microbiology", "Molecular Biology", "Cell Biology",
        "Genetics", "Biochemistry", "Botany", "Zoology", "Ecology",
        "Evolutionary Biology", "Marine Biology",
        "Agricultural Biotechnology", "Synthetic Biology",
    ],
    "Physical Sciences": [
        "Physics", "Chemistry", "Astronomy", "Astrophysics", "Mathematics",
        "Applied Mathematics", "Statistics", "Geology", "Geophysics",
        "Meteorology", "Nanotechnology", "Materials Science",
    ],
    "Environmental & Earth Sciences": [
        "Environmental Science", "Climate Change", "Climate Modeling",
        "Renewable Energy", "Sustainability", "Environmental Pollution",
        "Water Resources", "Conservation", "Geography", "Oceanography",
        "Natural Disasters", "Waste Management",
    ],
    "Business, Management & Economics": [
        "Business Administration", "Finance", "Accounting", "Marketing",
        "Human Resource Management", "Operations Management",
        "Entrepreneurship", "Economics", "Behavioral Economics",
        "International Business", "Supply Chain Management",
        "Business Analytics", "FinTech",
    ],
    "Social Sciences": [
        "Psychology", "Sociology", "Political Science", "Anthropology",
        "Education", "Linguistics", "Communication Studies", "Criminology",
        "International Relations", "Public Policy", "Social Work",
        "Human Geography",
    ],
    "Humanities & Arts": [
        "History", "Philosophy", "Literature", "Linguistics",
        "Religious Studies", "Cultural Studies", "Archaeology", "Music",
        "Fine Arts", "Media Studies", "Ethics",
    ],
    "Agriculture & Food Sciences": [
        "Agronomy", "Horticulture", "Soil Science", "Plant Pathology",
        "Animal Science", "Food Technology", "Food Safety",
        "Agricultural Economics", "Precision Agriculture", "Aquaculture",
        "Food Nutrition",
    ],
    "Law & Legal Studies": [
        "Constitutional Law", "Criminal Law", "Corporate Law",
        "International Law", "Intellectual Property Law", "Human Rights Law",
        "Environmental Law", "Cyber Law", "Legal Technology",
    ],
    "Education & Learning Sciences": [
        "Educational Technology", "E-Learning", "Learning Analytics",
        "Curriculum Development", "Educational Psychology",
        "Special Education", "Higher Education", "Distance Learning",
    ],
    "Architecture & Design": [
        "Architecture", "Urban Planning", "Interior Design",
        "Landscape Architecture", "Industrial Design",
        "Sustainable Architecture", "Computational Design",
    ],
    "Energy & Power Systems": [
        "Solar Energy", "Wind Energy", "Nuclear Energy", "Hydrogen Energy",
        "Battery Technology", "Smart Grids", "Energy Storage",
        "Power Electronics", "Electric Vehicles",
    ],
}

METHODOLOGIES = [
    "Experimental Research", "Theoretical Research", "Empirical Research",
    "Quantitative Research", "Qualitative Research", "Mixed-Methods Research",
    "Computational Research", "Simulation-Based Research",
    "Observational Research", "Case Study Research", "Survey-Based Research",
    "Comparative Research", "Longitudinal Research",
    "Cross-Sectional Research", "Design Science Research", "Action Research",
]

PAPER_TYPES = [
    "Original Research Article", "Review Paper", "Systematic Literature Review",
    "Meta-Analysis", "Survey Paper", "Conference Paper", "Journal Article",
    "Short Communication", "Case Study", "Technical Paper", "Position Paper",
    "Perspective Article", "Methodological Paper", "Replication Study",
    "Benchmark Paper", "Dataset Paper", "Preprint",
]

APPLICATION_AREAS = [
    "Healthcare", "Education", "Agriculture", "Finance and Banking",
    "Manufacturing", "Transportation", "Automotive Industry", "Aerospace",
    "Telecommunications", "Retail and E-commerce", "Cybersecurity",
    "Smart Cities", "Environmental Protection", "Energy Management",
    "Defense and Security", "Entertainment", "Gaming",
    "Business Automation", "Scientific Discovery", "Public Administration",
]

TECHNIQUES = [
    "Machine Learning", "Deep Learning", "Natural Language Processing",
    "Computer Vision", "Generative AI", "Reinforcement Learning",
    "Optimization", "Data Mining", "Explainable AI", "Federated Learning",
    "Graph Learning",
]

CLASSIFICATION_OPTIONS = {
    "research_domains": list(RESEARCH_DOMAINS),
    "subdomains": sorted({item for items in RESEARCH_DOMAINS.values() for item in items}),
    "methodologies": METHODOLOGIES,
    "paper_types": PAPER_TYPES,
    "application_areas": APPLICATION_AREAS,
    "techniques": TECHNIQUES,
}
CLASSIFICATION_PROGRESS_FIELDS = (
    "research_domains",
    "subdomains",
    "methodologies",
    "paper_types",
    "application_areas",
    "techniques",
)
_SUBDOMAIN_STOP_WORDS = {
    "and", "of", "for", "the", "in", "with", "science", "technology",
    "engineering", "systems", "system", "research", "studies", "study",
}
_SUBDOMAIN_ALIASES = {
    "artificial intelligence": {"ai"},
    "machine learning": {"ml"},
    "deep learning": {"dl"},
    "natural language processing": {"nlp"},
    "computer vision": {"cv"},
    "internet of things": {"iot"},
    "human-computer interaction": {"hci"},
}


def _prompt_options(evidence: str) -> dict[str, list[str]]:
    evidence_lower = evidence.lower()
    evidence_words = set(re.findall(r"[a-z0-9]+", evidence_lower))
    subdomains = []
    for label in CLASSIFICATION_OPTIONS["subdomains"]:
        label_words = {
            word for word in re.findall(r"[a-z0-9]+", label.lower())
            if word not in _SUBDOMAIN_STOP_WORDS and len(word) > 2
        }
        aliases = _SUBDOMAIN_ALIASES.get(label.lower(), set())
        score = len(label_words & evidence_words)
        if label.lower() in evidence_lower:
            score += 3
        if aliases & evidence_words:
            score += 2
        if score:
            subdomains.append((score, label))
    subdomains.sort(key=lambda item: (-item[0], item[1]))

    return {
        **CLASSIFICATION_OPTIONS,
        "subdomains": [label for _, label in subdomains[:20]],
    }


def validate_classification(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise ValueError("Classification must be an object of category lists.")

    unexpected = set(value) - set(CLASSIFICATION_OPTIONS)
    if unexpected:
        raise ValueError(f"Unknown classification fields: {', '.join(sorted(unexpected))}.")

    result = {}
    for field, options in CLASSIFICATION_OPTIONS.items():
        selected = value.get(field, [])
        if not isinstance(selected, list) or any(not isinstance(item, str) for item in selected):
            raise ValueError(f"{field} must be a list of category names.")
        if len(selected) != len(set(selected)):
            raise ValueError(f"{field} cannot contain duplicate categories.")
        invalid = set(selected) - set(options)
        if invalid:
            raise ValueError(f"Invalid {field}: {', '.join(sorted(invalid))}.")
        result[field] = selected

    if not result["research_domains"]:
        raise ValueError("Select at least one research domain.")
    return result


def classify_research_paper(
    paper_text: str,
    summary: str,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, list[str]]:
    compact_text = paper_text[:300]
    compact_summary = summary[:800]
    total_fields = len(CLASSIFICATION_PROGRESS_FIELDS)
    completed_fields: set[str] = set()
    decoder = json.JSONDecoder()

    def report_stream_progress(response_text: str) -> None:
        if progress_callback is None:
            return
        for field in CLASSIFICATION_PROGRESS_FIELDS:
            if field in completed_fields:
                continue
            match = re.search(rf'"{re.escape(field)}"\s*:\s*', response_text)
            if match is None:
                continue
            try:
                selected, _ = decoder.raw_decode(response_text[match.end():])
            except json.JSONDecodeError:
                continue
            if not isinstance(selected, list) or any(
                not isinstance(item, str) for item in selected
            ):
                continue
            if len(selected) != len(set(selected)):
                continue
            if set(selected) - set(CLASSIFICATION_OPTIONS[field]):
                continue
            completed_fields.add(field)
            progress_callback(len(completed_fields), total_fields, field)

    prompt_options = _prompt_options(f"{compact_text}\n{compact_summary}")
    prompt = f"""Classify this academic paper using only evidence in its text and summary.
Return exactly one JSON object with these six keys and array values, in this order:
research_domains, subdomains, methodologies, paper_types, application_areas, techniques.
Choose every clearly relevant exact label from the corresponding allowed values below.
Use [] when evidence is insufficient. Do not infer a value from the title alone.
{json.dumps(prompt_options, ensure_ascii=False)}

PAPER TEXT EXCERPT:
{compact_text}

EXISTING PAPER SUMMARY:
{compact_summary}
"""
    if progress_callback is not None:
        progress_callback(0, total_fields, CLASSIFICATION_PROGRESS_FIELDS[0])

    try:
        response = stream_ollama(
            prompt,
            max_tokens=900,
            progress_callback=report_stream_progress,
        )
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            "AI classification is unavailable. Please check the AI service and retry."
        ) from exc

    try:
        classification = json.loads(response)
        if not isinstance(classification, dict):
            raise ValueError("The response must be a JSON object.")
        if set(classification) != set(CLASSIFICATION_OPTIONS):
            raise ValueError("The response must include all six classification fields.")
        return validate_classification(classification)
    except ValueError as exc:
        raise RuntimeError(f"AI classification returned invalid categories: {exc}") from exc
