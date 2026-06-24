import re

# =============================================================================
# TDR DETECTION ENGINE
# =============================================================================
#
# Scoring layers (applied to filename + first N chars of text):
#
#   DEFINITIVE  (+30 each)  — phrases that exist ONLY in consulting TDRs
#   STRONG      (+7 title / +4 head)  — very distinctive, rare elsewhere
#   STRUCTURE   (+2 each)   — typical TDR section headers
#   FILENAME    (+15)       — TDR keyword in filename
#   NON_TDR     (-8 title / -3 body)  — penalise clearly wrong document types
#
#   Threshold: score >= 10  → is_tdr = True
# =============================================================================

# ── Definitive signals — if any ONE is found, document is almost certainly a TDR
TDR_DEFINITIVE_SIGNALS = [
    # French — procurement/hiring phrases that only appear in TDRs
    "termes de référence pour",
    "termes de reference pour",
    "terms of reference for",
    "avis de recrutement d'un consultant",
    "avis de recrutement d'une firme",
    "avis de sélection de consultant",
    "appel à manifestation d'intérêt pour le recrutement",
    "appel a manifestation d'interet pour le recrutement",
    "recrutement d'un consultant individuel",
    "recrutement d'une firme de consultants",
    "sélection d'un consultant individuel",
    "selection d'un consultant individuel",
    "expression d'intérêt pour la fourniture de services",
    "demande de propositions de services",
    "request for proposals for consulting",
    "invitation à soumissionner",
    "dossier de candidature pour le poste de",
    "avis de consultants — sélection",
    "avis de consultants - selection",
    "offre de services de consultance",
]

# ── Strong signals — highly distinctive of TDRs
TDR_STRONG_SIGNALS = [
    # French explicit
    "termes de référence", "termes de reference",
    "cahier des charges",
    "appel à candidatures", "appel a candidatures",
    "appel à propositions", "appel a propositions",
    "appel à manifestation d'intérêt", "appel a manifestation d'interet",
    "manifestation d'intérêt", "manifestation d'interet",
    "demande de propositions", "demande de cotation",
    "avis de recrutement", "avis de sélection", "avis de selection",
    "recrutement de consultant", "recrutement d'un consultant", "recrutement d un consultant",
    "sélection d'un consultant", "selection d'un consultant",
    "offre de services", "offre technique et financière", "offre technique et financiere",
    # English explicit
    "terms of reference",
    "expression of interest",
    "request for proposals", "request for quotation",
    "call for consultants", "call for proposals",
    "consultant selection", "recruitment of a consultant",
    "invitation to bid", "invitation to tender",
    "scope of work for consulting",
]

# ── Structure signals — typical section headers unique to TDR structure
TDR_STRUCTURE_SIGNALS = [
    # Context
    "contexte et justification", "contexte de la mission", "contexte général",
    "background and context", "project background", "contexte du projet",
    "présentation du projet", "présentation de la mission",
    # Objectives
    "objectifs de la mission", "objectifs de la consultance",
    "objectifs spécifiques", "objectifs généraux de la mission",
    "scope of work", "objectifs attendus", "résultats attendus",
    "but de la mission", "finalité de la mission",
    # Tasks
    "tâches du consultant", "tâches du prestataire",
    "tâches à réaliser", "activités à mener", "activités du consultant",
    "responsabilités du consultant", "description des tâches",
    "travaux à réaliser", "prestations attendues",
    # Deliverables
    "livrables attendus", "livrables de la mission", "livrables du consultant",
    "deliverables", "expected outputs", "produits attendus",
    "rapports à produire", "documents à soumettre",
    # Consultant profile
    "profil du consultant", "profil requis", "profil recherché",
    "profil du candidat", "qualifications requises", "qualifications minimales",
    "required qualifications", "consultant profile", "expert profile",
    "compétences requises", "expériences requises",
    "niveau d'études requis", "diplôme requis",
    "nombre d'années d'expérience", "années d'expérience exigées",
    # Timeline
    "durée de la mission", "durée du contrat", "période d'exécution",
    "duration of assignment", "calendrier de la mission",
    "planning de la mission", "chronogramme de la mission",
    "date de démarrage", "date de prise de service",
    # Budget / payment
    "modalités de paiement", "honoraires du consultant",
    "budget de la mission", "budget indicatif", "enveloppe budgétaire",
    "rémunération du consultant", "per diem", "frais de mission",
    "montant du marché", "budget prévisionnel",
    # Selection criteria
    "critères de sélection", "critères d'évaluation", "critères d'attribution",
    "selection criteria", "evaluation criteria", "grille d'évaluation",
    "pondération des critères",
    # Submission
    "soumission des offres", "dépôt des candidatures", "dépôt des offres",
    "submission of proposals", "dossier de candidature",
    "composition du dossier", "pièces à fournir", "documents requis",
    "modalités de soumission", "conditions de soumission",
    "date limite de soumission", "date limite de dépôt",
    "adresse de soumission", "lieu de dépôt",
    # Eligibility
    "conditions d'éligibilité", "conditions de participation",
    "eligibility criteria", "critères d'éligibilité",
    "instruction aux soumissionnaires",
    # Contracting
    "modalités contractuelles", "type de contrat", "nature du contrat",
    "contrat de consultant", "contrat de consultance",
    "contracting arrangements",
]

# ── Filename keywords — strongest signal (+15 if any match)
TDR_FILENAME_KEYWORDS = [
    "tdr", "tdrs", "t.d.r", "tor_", "_tor",
    "termes_de_ref", "termes-de-ref", "termes_ref",
    "terms_of_ref", "terms-of-ref", "terms_ref",
    "cahier_des_charges", "cahier-des-charges",
    "appel_a_candid", "appel-a-candid", "appel_candid",
    "appel-a-consul", "appel_a_consul",         # Appel-a-consultants
    "appel-d-offre", "appel_d_offre", "appel-doffre",  # Appel d'offres
    "recrutement_consultant", "recrutement-consultant",
    "offre_de_service", "offre-de-service",
    "contrat-de-service", "contrat_de_service",
    "manifestation_interet", "manifestation-interet",
    "manifestation-d_interet", "manifestation_d_interet",
    "expression_of_interest", "expression-of-interest",
    "sow_", "_sow", "scope_of_work",
    "ami_", "_ami",                             # Avis à Manifestation d'Intérêt
    "avis_consul", "avis-consul",
    "avis-de-manifes", "avis_de_manifes",
    "appel_offre", "appel-offre",
    "dao-", "_dao_",                            # Dossier d'Appel d'Offres
    "demande_offre", "demande-offre",
    "demande_doffre", "demande-doffre",
]

# ── Non-TDR penalty signals — clearly wrong document types
NON_TDR_SIGNALS = [
    # Reports
    "rapport de progression", "progress report",
    "rapport annuel", "annual report",
    "rapport final du projet",
    "rapport de mission effectuée",
    "rapport de synthèse", "synthesis report",
    "midterm review", "revue à mi-parcours",
    "evaluation finale du projet",
    # Presentations / events
    "présentation powerpoint", "conference proceedings",
    "séminaire international", "workshop report",
    "compte rendu de la réunion",
    "procès verbal de la réunion",
    "ordre du jour de la réunion",
    "minutes of meeting",
    # Manuals / technical
    "manuel utilisateur", "user manual",
    "guide d'utilisation", "mode d'emploi",
    "technical documentation",
    "installation manual", "user guide",
    "time domain reflectometry",
    "geophone", "seismic survey",
    "technical design report",
    # Administrative
    "note de service",
    "certificat de conformité",
    "attestation de",
    "acte de naissance",
    # Academic
    "article scientifique", "thèse de doctorat",
    "mémoire de master", "research paper",
    "working paper",
    # Environmental / regulatory (not TDR)
    "plan de gestion environnementale",
    "pges ", " pges",
    "environmental impact assessment",
    "plan de sauvegarde",
    "procurement regulations",
    "règlement de passation des marchés",
    # Assembly / engineering
    "plan de montage",
    "assembly instructions",
    "technical specifications for equipment",
]


def classify_tdr(text: str, filename: str) -> dict:
    """
    Score a document and return TDR classification fields.

    Returns: is_tdr, tdr_confidence (0-1), tdr_label, tdr_score
    """
    fn_lower     = filename.lower()
    title_area   = (filename + " " + text[:3000]).lower()
    head         = (filename + " " + text[:8000]).lower()
    full_sample  = (filename + " " + text[:15000]).lower()

    score = 0.0
    matched = []

    # Definitive signals — each worth +30, capped at 2 hits
    def_hits = 0
    for sig in TDR_DEFINITIVE_SIGNALS:
        if sig in full_sample:
            if def_hits < 2:
                score += 30
                matched.append(f"DEFINITIVE:{sig[:40]}")
            def_hits += 1

    # Filename bonus
    if any(kw in fn_lower for kw in TDR_FILENAME_KEYWORDS):
        score += 15
        matched.append("FILENAME")

    # Strong signals
    for sig in TDR_STRONG_SIGNALS:
        in_title = title_area.count(sig)
        in_head  = head.count(sig) - in_title
        if in_title > 0:
            score += in_title * 7
            matched.append(f"STRONG(title):{sig[:35]}")
        if in_head > 0:
            score += in_head * 4
            matched.append(f"STRONG(head):{sig[:35]}")

    # Structure signals
    struct_count = 0
    for sig in TDR_STRUCTURE_SIGNALS:
        if sig in full_sample:
            score += 2
            struct_count += 1
    if struct_count:
        matched.append(f"STRUCTURE:{struct_count} sections")

    # Non-TDR penalties
    for sig in NON_TDR_SIGNALS:
        in_title = title_area.count(sig)
        in_body  = full_sample.count(sig) - in_title
        if in_title > 0:
            score -= in_title * 8
            matched.append(f"PENALTY(title):{sig[:30]}")
        if in_body > 0:
            score -= in_body * 3
            matched.append(f"PENALTY(body):{sig[:30]}")

    is_tdr         = score >= 10
    tdr_confidence = round(min(1.0, max(0.0, score / 40.0)), 3)

    if score >= 35:
        tdr_label = "TDR confirme"
    elif score >= 20:
        tdr_label = "TDR probable"
    elif score >= 10:
        tdr_label = "TDR possible"
    elif score >= 0:
        tdr_label = "Indetermine"
    else:
        tdr_label = "Non-TDR"

    return {
        "is_tdr":          is_tdr,
        "tdr_confidence":  tdr_confidence,
        "tdr_label":       tdr_label,
        "tdr_score":       round(score, 1),
        "tdr_matched":     matched[:6],  # top signals for debugging
    }


# =============================================================================
# GEOGRAPHIC / THEMATIC METADATA
# =============================================================================

COUNTRIES = {
    "Mali":           ["mali", "bamako"],
    "Maroc":          ["maroc", "marocain", "rabat", "casablanca"],
    "Mauritanie":     ["mauritanie", "mauritanien", "nouakchott"],
    "Senegal":        ["senegal", "dakar"],
    "Niger":          ["niger", "niamey"],
    "Burkina Faso":   ["burkina", "ouagadougou"],
    "Cote d'Ivoire":  ["cote d'ivoire", "ivoirien", "abidjan"],
    "Cameroun":       ["cameroun", "yaounde", "douala"],
    "RDC":            ["rdc", "congo democratique", "kinshasa"],
    "RCA":            ["rca", "centrafrique", "bangui"],
    "Congo":          ["congo-brazzaville", "brazzaville", "republique du congo", "conkouati"],
    "Guinee":         ["republique de guinee", "guinee conakry", "conakry"],
    "Tchad":          ["tchad", "ndjamena"],
    "Ethiopie":       ["ethiopie", "addis"],
    "Kenya":          ["kenya", "nairobi"],
    "Tanzanie":       ["tanzanie", "dar es salaam"],
    "Mozambique":     ["mozambique", "maputo"],
    "Madagascar":     ["madagascar", "antananarivo"],
    "Tunisie":        ["tunisie", "tunisien", "tunis"],
    "Algerie":        ["algerie", "alger"],
    "Egypte":         ["egypte", "le caire"],
    "Liban":          ["liban", "beyrouth"],
    "Jordanie":       ["jordanie", "amman"],
    "Benin":          ["benin", "cotonou"],
    "Togo":           ["togo", "lome"],
    "Rwanda":         ["rwanda", "kigali"],
    "Ouganda":        ["ouganda", "kampala"],
    "Nigeria":        ["nigeria", "lagos", "abuja"],
    "Ghana":          ["ghana", "accra"],
    "Djibouti":       ["djibouti"],
    "Soudan":         ["soudan", "khartoum"],
}

REGION_MAP = {
    "Afrique de l'Ouest":          ["Mali", "Senegal", "Niger", "Burkina Faso", "Cote d'Ivoire", "Guinee", "Benin", "Togo", "Ghana", "Nigeria"],
    "Afrique centrale":            ["Cameroun", "Congo", "RDC", "RCA", "Tchad"],
    "Afrique de l'Est":            ["Ethiopie", "Kenya", "Tanzanie", "Rwanda", "Ouganda", "Djibouti"],
    "Afrique australe":            ["Mozambique", "Madagascar"],
    "Maghreb":                     ["Maroc", "Tunisie", "Algerie"],
    "Moyen-Orient & Afrique Nord": ["Liban", "Jordanie", "Egypte", "Soudan"],
}

DONORS = {
    "Banque Mondiale":  ["banque mondiale", "world bank", "ida", "bird"],
    "Union Europeenne": ["union europeenne", "commission europeenne", " ue ", " eu "],
    "AFD":              ["afd", "agence francaise de developpement"],
    "USAID":            ["usaid"],
    "KfW / GIZ":        ["kfw", "giz", "cooperation allemande"],
    "UNICEF":           ["unicef"],
    "PNUD":             ["pnud", "undp"],
    "FAO":              ["fao"],
    "OMS":              ["oms", "who", "organisation mondiale de la sante"],
    "UNFPA":            ["unfpa", "fnuap"],
    "BAD":              ["banque africaine de developpement", "african development bank"],
    "Enabel / DGD":     ["enabel", "ctb", "dgd", "cooperation belge"],
    "JICA":             ["jica"],
    "AMC / Canada":     ["affaires mondiales canada", "global affairs canada", "cooperation canadienne", "agence canadienne"],
}

DOMAINS = {
    "Agriculture":          ["agriculture", "agricole", "elevage", "peche", "agroalimentaire", "semences", "irrigation"],
    "Sante":                ["sante", "medical", "medicament", "hopital", "vaccin", "epidemie", "maladie", "health"],
    "Education":            ["education", "formation", "ecole", "universite", "enseignement", "alphabetisation"],
    "Infrastructure":       ["infrastructure", "route", "pont", "batiment", "construction", "travaux publics"],
    "Eau & Assainissement": ["eau potable", "assainissement", "hydraulique", "wash", "latrines"],
    "Energie":              ["energie", "electricite", "solaire", "renouvelable", "biomasse"],
    "Finance & Audit":      ["audit", "financier", "comptable", "microfinance"],
    "Environnement":        ["environnement", "climat", "biodiversite", "foret", "ecologie"],
    "Gouvernance":          ["gouvernance", "institutionnel", "decentralisation", "reforme politique"],
    "Protection sociale":   ["protection sociale", "genre", "femmes", "enfants", "handicap", "vulnerables"],
    "Consultation":         ["consultance", "recrutement expert", "selection consultant"],
}


def _score(text_lower: str, keywords: list[str]) -> int:
    return sum(text_lower.count(kw) for kw in keywords)


def extract_metadata(text: str, filename: str) -> dict:
    # Normalise for keyword matching (remove accents for broader matching)
    import unicodedata
    def _norm(s):
        return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower()

    sample_raw = (filename + " " + text[:6000]).lower()
    sample     = _norm(filename + " " + text[:6000])

    # Year
    years = re.findall(r'\b(20[01]\d|202\d)\b', filename + " " + text[:3000])
    year  = max(years) if years else "Inconnu"

    # Country
    scores      = {c: _score(sample, [_norm(k) for k in kws]) for c, kws in COUNTRIES.items()}
    best_country = max(scores, key=scores.get)
    country      = best_country if scores[best_country] > 0 else "Inconnu"

    # Region
    region = "Inconnu"
    for reg, members in REGION_MAP.items():
        if country in members:
            region = reg
            break

    # Donor
    scores     = {d: _score(sample, [_norm(k) for k in kws]) for d, kws in DONORS.items()}
    best_donor = max(scores, key=scores.get)
    donor      = best_donor if scores[best_donor] > 0 else "Inconnu"

    # Domain
    scores      = {d: _score(sample, [_norm(k) for k in kws]) for d, kws in DOMAINS.items()}
    best_domain = max(scores, key=scores.get)
    domain      = best_domain if scores[best_domain] > 0 else "Inconnu"

    # TDR classification
    tdr_info = classify_tdr(text, filename)

    return {
        "year":           year,
        "country":        country,
        "region":         region,
        "donor":          donor,
        "domain":         domain,
        "is_tdr":         tdr_info["is_tdr"],
        "tdr_confidence": tdr_info["tdr_confidence"],
        "tdr_label":      tdr_info["tdr_label"],
        "tdr_score":      tdr_info["tdr_score"],
    }
