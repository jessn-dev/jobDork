"""
jobdork.search.resume
=====================
Reads your resume once and uses it to sort the list, offline.

This costs nothing and needs no `claude` CLI. It is deliberately the smaller
half of what a resume is for here: drafting a tailored CV needs a model, but
*ranking* what you are shown does not. Skill overlap between your record and
the advert is a decent proxy for fit, and it is a proxy you can inspect.

What it does NOT do is claim to be a rating. It reports which of your skills
the advert names and which it wants that you do not have, and leaves the
judgement to you.

.txt and .md are read directly. .docx is a zip of XML and is read with the
standard library. .pdf needs `pypdf`, which is an optional extra rather than a
hard dependency — scanning, filtering and tracking all work without it, and a
missing parser says so instead of silently scoring nothing.

    pip install pypdf
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# Skills worth matching on, by field. Deliberately a list rather than "every
# capitalised word": the second approach matches company names, city names
# and the word "Agile" in a sentence about culture, and scores everything the
# same.
#
# Grouped because a word is a skill in one field and plain English in
# another: "go", "rest" and "spring" are a programmer's, and a nurse's advert
# says "rest breaks" and "go up stairs". So an advert's terms count only from
# the fields your resume is in (`near`): a nurse is not marked down for an
# advert's "rest", and a programmer for its "patient care". Tech is one
# field, as it was before the others were added, so a tech resume is scored
# as it always was.
FIELDS: dict[str, tuple[str, ...]] = {
    "technology": (
        # languages
        "python", "java", "javascript", "typescript", "go", "golang", "rust",
        "ruby", "php", "c++", "c#", "scala", "kotlin", "swift", "elixir", "perl",
        "r", "matlab", "bash", "shell", "sql", "html", "css",
        # web and app frameworks
        "react", "angular", "vue", "svelte", "next.js", "node", "node.js",
        "django", "flask", "fastapi", "rails", "spring", "spring boot", ".net",
        "express", "laravel", "graphql", "rest", "grpc",
        # data
        "postgres", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
        "cassandra", "dynamodb", "snowflake", "bigquery", "redshift", "databricks",
        "spark", "hadoop", "kafka", "airflow", "dbt", "etl", "pandas", "numpy",
        "tableau", "power bi", "looker",
        # ml
        "machine learning", "deep learning", "pytorch", "tensorflow",
        "scikit-learn", "nlp", "llm", "computer vision", "mlops",
        # infra
        "aws", "azure", "gcp", "kubernetes", "docker", "terraform", "ansible",
        "jenkins", "gitlab", "github actions", "ci/cd", "linux", "nginx",
        "microservices", "serverless", "lambda", "prometheus", "grafana",
        "datadog", "helm", "argocd", "help desk", "technical support",
        "jira", "confluence",
        # practice
        "agile", "scrum", "kanban", "tdd", "code review", "pair programming",
        "system design", "distributed systems", "api design", "security",
        "accessibility", "observability",
        # security operations
        "siem", "soc", "soar", "edr", "xdr", "splunk", "qradar", "sentinel",
        "crowdstrike", "carbon black", "incident response", "threat hunting",
        "threat intelligence", "malware analysis", "digital forensics",
        "intrusion detection", "firewall", "dlp", "casb", "honeypot",
        "mitre att&ck", "kill chain", "tabletop exercise",
        # offensive and assessment
        "penetration testing", "vulnerability management", "vulnerability scanning",
        "nessus", "qualys", "rapid7", "burp suite", "metasploit", "wireshark",
        "nmap", "red team", "blue team", "purple team", "osint",
        # identity
        "iam", "sso", "mfa", "okta", "active directory", "ldap", "saml", "oauth",
        "privileged access", "zero trust", "least privilege", "rbac",
        # governance, risk and compliance
        "grc", "risk assessment", "risk register", "risk management",
        "internal audit", "compliance", "control testing", "gap analysis",
        "third party risk", "vendor risk", "business continuity",
        "disaster recovery", "security awareness", "policy development",
        "security architecture", "data privacy", "incident management",
        # frameworks and standards
        "nist", "nist csf", "nist 800-53", "iso 27001", "soc 2", "soc2",
        "pci dss", "hipaa", "gdpr", "ccpa", "fedramp", "cmmc", "sox", "ferpa",
        "glba", "cis controls", "cobit", "itil", "fair",
        # certifications
        "cissp", "cisa", "cism", "crisc", "security+", "gsec", "gcih", "oscp",
        "ceh", "ccsp", "cgeit",
        # cloud security
        "cloud security", "cspm", "cwpp", "container security", "devsecops",
        "secrets management", "vault", "encryption", "pki", "key management",
    ),
    "healthcare": (
        # care
        "patient care", "patient assessment", "vital signs", "medication administration",
        "iv therapy", "iv insertion", "phlebotomy", "wound care", "triage", "telemetry",
        "critical care", "intensive care", "icu", "emergency department",
        "med-surg", "medical-surgical", "labor and delivery", "postpartum",
        "pediatrics", "neonatal", "nicu", "oncology", "geriatrics", "hospice",
        "home health", "behavioral health", "mental health", "case management",
        "discharge planning", "care planning", "care coordination",
        "infection control", "patient education", "charting", "dialysis",
        "ventilator management", "ekg", "ecg", "specimen collection",
        "sterile technique", "aseptic technique", "medical terminology",
        "physical therapy", "occupational therapy", "respiratory therapy",
        "speech therapy", "radiology", "ultrasound", "mri", "x-ray",
        "surgical technology", "operating room", "perioperative", "anesthesia",
        "activities of daily living", "fall prevention", "hipaa",
        # records and systems
        "electronic health records", "ehr", "emr", "epic", "cerner", "meditech",
        "pyxis", "omnicell", "athenahealth", "eclinicalworks",
        # credentials asked for as skills
        "rn", "lpn", "lvn", "cna", "bsn", "msn", "acls", "bls", "pals", "nrp",
        "tncc", "cpr", "ccrn", "cen",
        # pharmacy
        "pharmacy", "dispensing", "compounding", "medication reconciliation",
        "pharmacology", "controlled substances", "prescription processing",
        # administration and billing
        "medical billing", "medical coding", "icd-10", "cpt", "hcpcs",
        "revenue cycle", "prior authorization", "insurance verification",
        "patient scheduling", "patient registration", "medical records",
    ),
    "finance": (
        "accounts payable", "accounts receivable", "general ledger",
        "account reconciliation", "bank reconciliation", "reconciliation",
        "month-end close", "year-end close", "journal entries", "accruals",
        "fixed assets", "financial reporting", "financial statements",
        "financial analysis", "financial modeling", "forecasting", "budgeting",
        "variance analysis", "gaap", "ifrs", "audit", "internal controls", "sox",
        "tax preparation", "tax compliance", "payroll", "invoicing", "billing",
        "cost accounting", "fp&a", "treasury", "cash management",
        "quickbooks", "netsuite", "xero", "oracle financials", "sap", "excel",
        "pivot tables", "vlookup", "cpa", "cma", "cfa",
        # banking and insurance
        "underwriting", "credit analysis", "credit risk", "loan origination",
        "loan processing", "mortgage", "kyc", "aml", "anti-money laundering",
        "bsa", "fraud prevention", "wealth management", "portfolio management",
        "risk management", "claims processing", "claims adjusting", "actuarial",
        "teller", "cash handling", "branch operations", "finra", "series 7",
        "series 63", "series 66", "property and casualty", "life and health",
    ),
    "sales and marketing": (
        "salesforce", "hubspot", "crm", "lead generation", "prospecting",
        "cold calling", "account management", "business development",
        "pipeline management", "quota", "negotiation", "b2b", "b2c",
        "seo", "sem", "ppc", "google ads", "google analytics",
        "social media marketing", "content marketing", "email marketing",
        "marketing automation", "marketo", "copywriting", "brand management",
        "market research", "campaign management", "upselling",
    ),
    "customer service": (
        "customer service", "customer support", "call center", "contact center",
        "inbound calls", "outbound calls", "zendesk", "ticketing", "live chat",
        "de-escalation", "complaint resolution", "customer retention", "bpo",
        "csat", "nps", "first call resolution", "average handle time",
        "help desk", "technical support", "upselling", "crm",
    ),
    "retail and hospitality": (
        "point of sale", "pos", "cash handling", "merchandising",
        "visual merchandising", "inventory management", "stocking",
        "loss prevention", "store operations", "customer service",
        "food safety", "servsafe", "food handler", "food preparation",
        "line cook", "front of house", "back of house", "guest services",
        "front desk", "housekeeping", "reservations", "opera pms", "banquets",
        "bartending", "barista", "upselling",
    ),
    "logistics": (
        "warehouse", "forklift", "pallet jack", "reach truck", "order picking",
        "picking and packing", "shipping and receiving", "inventory control",
        "inventory management", "cycle counting", "rf scanner", "wms",
        "warehouse management system", "supply chain", "procurement",
        "purchasing", "sourcing", "vendor management", "logistics", "freight",
        "dispatch", "route planning", "fleet management", "cdl", "class a cdl",
        "dot regulations", "hazmat", "last mile", "3pl", "customs",
        "demand planning", "s&op", "erp", "sap", "lean", "six sigma", "kaizen", "5s",
    ),
    "manufacturing and trades": (
        "cnc", "machining", "blueprint reading", "gd&t", "quality control",
        "quality assurance", "iso 9001", "lean manufacturing", "lean",
        "six sigma", "kaizen", "5s", "preventive maintenance", "plc", "hvac",
        "electrical", "welding", "mig welding", "tig welding", "plumbing",
        "carpentry", "osha", "osha 10", "osha 30", "lockout/tagout",
        "power tools", "assembly", "production line", "autocad", "solidworks",
        "hydraulics", "pneumatics", "troubleshooting", "multimeter", "forklift",
    ),
    "construction and engineering": (
        "construction management", "estimating", "primavera p6", "procore",
        "bluebeam", "site supervision", "civil engineering",
        "structural engineering", "mechanical engineering",
        "electrical engineering", "revit", "autocad", "solidworks", "surveying",
        "permitting", "building codes", "osha", "osha 10", "osha 30",
        "project management", "scheduling",
    ),
    "education": (
        "lesson planning", "curriculum development", "classroom management",
        "differentiated instruction", "special education", "iep", "esl",
        "tesol", "tefl", "student assessment", "google classroom", "canvas",
        "blackboard", "tutoring", "early childhood education",
        "instructional design", "e-learning", "articulate storyline", "cpr",
    ),
    "human resources": (
        "recruiting", "talent acquisition", "sourcing", "onboarding",
        "employee relations", "benefits administration", "payroll", "hris",
        "workday", "adp", "successfactors", "performance management",
        "compensation", "labor law", "shrm-cp", "phr", "applicant tracking",
    ),
    "legal": (
        "legal research", "contract review", "contract drafting", "litigation",
        "e-discovery", "westlaw", "lexisnexis", "paralegal",
        "regulatory compliance", "due diligence", "corporate law",
        "intellectual property",
    ),
    "office and business": (
        "data entry", "microsoft office", "excel", "powerpoint", "outlook",
        "google workspace", "calendar management", "scheduling", "bookkeeping",
        "filing", "records management", "travel arrangements", "transcription",
        "project management", "pmp", "stakeholder management", "jira",
        "confluence", "product management", "requirements gathering",
        "business analysis", "process improvement", "change management",
        "data analysis", "tableau", "power bi",
    ),
}

# Terms that say nothing about which field a resume is in: plain words in
# most fields ("go", "rest", "security", "scheduling"), or asked for in every
# field (Excel, customer service, HIPAA, SOX). They still match inside the
# fields a resume is found to be in; they only never put it in one.
WEAK = frozenset((
    "go", "r", "rest", "spring", "express", "lambda", "vault", "fair",
    "sentinel", "soc", "node", "shell", "security", "compliance", "agile",
    "scrum", "kanban", "accessibility", "risk assessment", "risk management",
    "policy development", "data privacy", "hipaa", "gdpr", "sox", "encryption",
    "firewall", "triage", "telemetry", "charting", "cpr", "audit", "billing",
    "invoicing", "payroll", "forecasting", "budgeting", "excel", "sap", "erp",
    "crm", "pos", "lean", "six sigma", "kaizen", "5s", "osha", "quota",
    "negotiation", "b2b", "b2c", "upselling", "customer service",
    "inventory management", "stocking", "warehouse", "logistics", "dispatch",
    "sourcing", "purchasing", "onboarding", "compensation", "workday", "adp",
    "canvas", "blackboard", "scheduling", "filing", "microsoft office",
    "powerpoint", "outlook", "project management", "stakeholder management",
    "process improvement", "change management", "data analysis", "jira",
    "confluence", "tableau", "power bi", "assembly", "electrical",
    "troubleshooting", "reconciliation", "cash handling", "epic",
))

# Every term, each once, in the order above.
SKILL_TERMS = tuple(dict.fromkeys(t for terms in FIELDS.values() for t in terms))

# How a skill is written for a person to read. Matching stays on the lower
# case terms above; anything not named here reads in sentence case, which is
# right for plain phrases ("Machine learning") and wrong for names, so every
# acronym and product that has its own spelling is listed.
SKILL_NAMES = {
    "javascript": "JavaScript", "typescript": "TypeScript", "golang": "Golang",
    "php": "PHP", "matlab": "MATLAB", "sql": "SQL", "html": "HTML", "css": "CSS",
    "next.js": "Next.js", "node.js": "Node.js", "fastapi": "FastAPI",
    "graphql": "GraphQL", "rest": "REST", "grpc": "gRPC", ".net": ".NET",
    "postgresql": "PostgreSQL", "mysql": "MySQL", "mongodb": "MongoDB",
    "elasticsearch": "Elasticsearch", "dynamodb": "DynamoDB",
    "bigquery": "BigQuery", "etl": "ETL", "dbt": "dbt", "numpy": "NumPy",
    "pytorch": "PyTorch", "tensorflow": "TensorFlow", "nlp": "NLP",
    "llm": "LLM", "mlops": "MLOps", "aws": "AWS", "gcp": "GCP",
    "gitlab": "GitLab", "github actions": "GitHub Actions", "ci/cd": "CI/CD",
    "argocd": "Argo CD", "tdd": "TDD", "api design": "API design",
    "siem": "SIEM", "soc": "SOC", "soar": "SOAR", "edr": "EDR", "xdr": "XDR",
    "qradar": "QRadar", "crowdstrike": "CrowdStrike", "dlp": "DLP",
    "casb": "CASB", "mitre att&ck": "MITRE ATT&CK", "osint": "OSINT",
    "burp suite": "Burp Suite", "rapid7": "Rapid7", "iam": "IAM", "sso": "SSO",
    "mfa": "MFA", "active directory": "Active Directory", "ldap": "LDAP",
    "saml": "SAML", "oauth": "OAuth", "rbac": "RBAC", "grc": "GRC",
    "nist": "NIST", "nist csf": "NIST CSF", "nist 800-53": "NIST 800-53",
    "iso 27001": "ISO 27001", "soc 2": "SOC 2", "soc2": "SOC 2",
    "pci dss": "PCI DSS", "hipaa": "HIPAA", "gdpr": "GDPR", "ccpa": "CCPA",
    "fedramp": "FedRAMP", "cmmc": "CMMC", "sox": "SOX", "ferpa": "FERPA",
    "glba": "GLBA", "cis controls": "CIS Controls", "cobit": "COBIT",
    "itil": "ITIL", "fair": "FAIR", "cissp": "CISSP", "cisa": "CISA",
    "cism": "CISM", "crisc": "CRISC", "security+": "Security+", "gsec": "GSEC",
    "gcih": "GCIH", "oscp": "OSCP", "ceh": "CEH", "ccsp": "CCSP",
    "cgeit": "CGEIT", "cspm": "CSPM", "cwpp": "CWPP", "devsecops": "DevSecOps",
    "pki": "PKI", "c++": "C++", "c#": "C#", "r": "R",
    "spring boot": "Spring Boot", "carbon black": "Carbon Black",
    "power bi": "Power BI", "jira": "Jira",
    # healthcare
    "iv therapy": "IV therapy", "iv insertion": "IV insertion", "icu": "ICU",
    "nicu": "NICU", "med-surg": "Med-surg", "ekg": "EKG", "ecg": "ECG",
    "mri": "MRI", "x-ray": "X-ray", "ehr": "EHR", "emr": "EMR", "rn": "RN",
    "lpn": "LPN", "lvn": "LVN", "cna": "CNA", "bsn": "BSN", "msn": "MSN",
    "acls": "ACLS", "bls": "BLS", "pals": "PALS", "nrp": "NRP", "tncc": "TNCC",
    "cpr": "CPR", "ccrn": "CCRN", "cen": "CEN", "icd-10": "ICD-10", "cpt": "CPT",
    "hcpcs": "HCPCS", "eclinicalworks": "eClinicalWorks", "athenahealth": "athenahealth",
    # finance
    "gaap": "GAAP", "ifrs": "IFRS", "fp&a": "FP&A", "quickbooks": "QuickBooks",
    "netsuite": "NetSuite", "oracle financials": "Oracle Financials", "sap": "SAP",
    "vlookup": "VLOOKUP", "cpa": "CPA", "cma": "CMA", "cfa": "CFA", "kyc": "KYC",
    "aml": "AML", "bsa": "BSA", "finra": "FINRA", "series 7": "Series 7",
    "series 63": "Series 63", "series 66": "Series 66",
    # sales, service, retail
    "hubspot": "HubSpot", "crm": "CRM", "b2b": "B2B", "b2c": "B2C", "seo": "SEO",
    "sem": "SEM", "ppc": "PPC", "google ads": "Google Ads",
    "google analytics": "Google Analytics", "bpo": "BPO", "csat": "CSAT",
    "nps": "NPS", "pos": "POS", "servsafe": "ServSafe", "opera pms": "Opera PMS",
    # logistics, trades, construction
    "wms": "WMS", "rf scanner": "RF scanner", "cdl": "CDL", "class a cdl": "Class A CDL",
    "dot regulations": "DOT regulations", "3pl": "3PL", "s&op": "S&OP",
    "erp": "ERP", "5s": "5S", "cnc": "CNC", "gd&t": "GD&T", "iso 9001": "ISO 9001",
    "plc": "PLC", "hvac": "HVAC", "mig welding": "MIG welding",
    "tig welding": "TIG welding", "osha": "OSHA", "osha 10": "OSHA 10",
    "osha 30": "OSHA 30", "lockout/tagout": "Lockout/tagout", "autocad": "AutoCAD",
    "solidworks": "SolidWorks", "primavera p6": "Primavera P6",
    # education, HR, legal, office
    "iep": "IEP", "esl": "ESL", "tesol": "TESOL", "tefl": "TEFL",
    "google classroom": "Google Classroom", "articulate storyline": "Articulate Storyline",
    "e-learning": "E-learning", "hris": "HRIS", "adp": "ADP",
    "successfactors": "SuccessFactors", "shrm-cp": "SHRM-CP", "phr": "PHR",
    "e-discovery": "E-discovery", "lexisnexis": "LexisNexis",
    "microsoft office": "Microsoft Office", "powerpoint": "PowerPoint",
    "google workspace": "Google Workspace", "pmp": "PMP",
}


def skill_name(term: str) -> str:
    """A matched skill as a person writes it: "aws" is "AWS"."""
    return SKILL_NAMES.get(term) or term[:1].upper() + term[1:]


def flag_label(flag: str) -> str:
    """A stored flag as shown: sentence case, and a fit flag's skills named.

    "fit: has aws, sql; wants ci/cd" was written at scan time in the terms'
    lower case, and stays that way in the database until a rescreen, so the
    names are put right where the flag is shown rather than where it is kept.
    """
    flag = str(flag or "")
    if flag.startswith("fit: "):
        parts = []
        for part in flag[5:].split("; "):
            word, _, terms = part.partition(" ")
            if word in ("has", "wants") and terms:
                part = f"{word} {', '.join(skill_name(t) for t in terms.split(', '))}"
            parts.append(part)
        flag = "fit: " + "; ".join(parts)
    return flag[:1].upper() + flag[1:]

_YEARS = re.compile(r"(\d{1,2})\+?\s*(?:\+|plus)?\s*years?", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9+#./-]+")


class ResumeError(Exception):
    pass


@dataclass
class Resume:
    path: str = ""
    text: str = ""
    skills: set[str] = field(default_factory=set)

    @property
    def loaded(self) -> bool:
        return bool(self.text)


# How much of one resume file is read. A resume is a few pages: these are
# far past any real one, and stop a file built to stall the app (a PDF of
# thousands of pages, a .docx whose text unpacks to gigabytes) before it does.
MAX_PDF_PAGES = 30
MAX_TEXT_CHARS = 200_000
MAX_DOCX_XML = 20 * 1024 * 1024        # word/document.xml, unpacked


def document_xml(archive: zipfile.ZipFile, name: str = "word/document.xml") -> str:
    """A .docx's text part, refused when it would unpack past MAX_DOCX_XML.
    Raises KeyError when it has none, as ZipFile.read does."""
    if archive.getinfo(name).file_size > MAX_DOCX_XML:
        raise ResumeError(f"this .docx's text unpacks to over {MAX_DOCX_XML // 2**20} MB, "
                          "far more than any resume; save it again from Word")
    return archive.read(name).decode("utf-8", "replace")


def _read_docx(path: Path) -> str:
    """A .docx is a zip; the text lives in word/document.xml."""
    try:
        with zipfile.ZipFile(path) as archive:
            xml = document_xml(archive)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ResumeError(f"{path} is not a readable .docx: {exc}") from exc
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    return re.sub(r"\n{3,}", "\n\n", xml).strip()[:MAX_TEXT_CHARS]


_PARA = re.compile(r"<w:p[ >].*?</w:p>|<w:p/>", re.DOTALL)
_RUN = re.compile(r"<w:r[ >].*?</w:r>", re.DOTALL)
_PIECE = re.compile(r"<w:t(?: [^>]*)?>([^<]*)</w:t>|(<w:tab/>)|(<w:br/>)")


def docx_markdown(path: str) -> str:
    """A .docx as the resume template's small Markdown, for showing it.

    Headings (a Title or Heading style) become headings, list paragraphs
    become bullets, bold runs stay bold. Only for the page: the tools read
    the plain text from `load`.
    """
    import html

    try:
        with zipfile.ZipFile(path) as archive:
            xml = document_xml(archive)
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise ResumeError(f"{path} is not a readable .docx: {exc}") from exc
    lines = []
    for para in _PARA.findall(xml):
        style = re.search(r'<w:pStyle w:val="([^"]+)"', para)
        style = style.group(1).lower() if style else ""
        text = ""
        for run in _RUN.findall(para):
            piece = html.unescape("".join(
                t or (" " if tab else "\n") for t, tab, _br in _PIECE.findall(run)))
            bold = re.search(r"<w:b/>|<w:b w:val=\"(?:1|true|on)\"/>", run)
            text += f"**{piece.strip()}** " if bold and piece.strip() else piece
        text = re.sub(r"[ \t]+", " ", text).strip()
        if not text:
            lines.append("")
        elif style.startswith("title"):
            lines.append(f"# {text.replace('**', '')}")
        elif style.startswith("heading"):
            lines.append(f"## {text.replace('**', '')}")
        elif "<w:numPr>" in para or style.startswith("list"):
            lines.append(f"- {text}")
        else:
            lines.append(text)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


# Letter pairs some fonts (Calibri, in Word's PDF export) draw as one glyph,
# which come out of the PDF as other letters: "construcƟon", "submiƩals",
# "MicrosoŌ" (a construction manager's CV, 2026-10-26: 156 of them). A quote
# of "construction" then never matched the resume, so true claims were
# flagged. Only between lowercase letters, where no real word has them.
_GLYPH_PAIRS = {"\u019f": "ti", "\u01a9": "tt", "\u014c": "ft"}
_GLYPH = re.compile(r"(?<=[a-z\-\u019f\u01a9])[ \t]?([\u019f\u01a9])[ \t]?(?=[a-z\u019f\u01a9])"
                    r"|(?<=[a-z])[ \t]?([\u019f\u01a9\u014c])(?![A-Za-z])")


def _fix_glyphs(text: str) -> str:
    import unicodedata

    # Real ligatures (ﬁ ﬀ ﬂ ﬃ ﬄ ﬅ ﬆ) have a standard spelling out.
    # lambda: an adapter, the match object to the text normalize takes.
    text = re.sub("[\ufb00-\ufb06]", lambda m: unicodedata.normalize("NFKC", m.group()), text)
    text = text.replace("\uf0b7", "•")          # a font's own bullet, private use
    # lambda: picks the pair for whichever group matched.
    return _GLYPH.sub(lambda m: _GLYPH_PAIRS[m.group(1) or m.group(2)], text)


def _word_per_line(text: str) -> bool:
    """Most lines one word: a PDF whose words came out apart."""
    counts = sorted(len(line.split()) for line in text.splitlines() if line.strip())
    return len(counts) >= 40 and counts[len(counts) // 2] <= 1


def _read_pdf(path: Path) -> str:
    """Read a PDF via pypdf, which is optional and says so when absent.

    A resume laid out in columns or built from vector text can extract to
    almost nothing, and a near-empty extraction would silently score every
    role at zero fit rather than looking broken. So a suspiciously short
    result is reported rather than used.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ResumeError(
            f"{path} is a PDF and `pypdf` is not installed. Either "
            "`pip install pypdf`, or export the resume to .docx, .md or .txt."
        ) from exc

    try:
        reader = PdfReader(str(path))
        pages = list(reader.pages)[:MAX_PDF_PAGES]
        text = "\n\n".join((page.extract_text() or "") for page in pages)
        # Some PDFs place every word apart, and come out one word per line
        # ("April / 2025 / - / present"): every word read, every line lost.
        # Read by layout instead. Not always: layout puts two columns side
        # by side, line by line, where the default reads one, then the other.
        if _word_per_line(text):
            laid = "\n\n".join(
                (page.extract_text(extraction_mode="layout") or "") for page in pages)
            text = "\n".join(re.sub(r"[ \t]{2,}", " ", line).strip()
                              for line in laid.splitlines())
    except Exception as exc:                      # pypdf raises a wide variety
        raise ResumeError(f"{path} could not be read as a PDF: {exc}") from exc

    text = _fix_glyphs(text)[:MAX_TEXT_CHARS]
    if len(text.strip()) < 200:
        raise ResumeError(
            f"{path} yielded only {len(text.strip())} characters of text. It is "
            "probably a scan or an image-based export, and scoring against it "
            "would quietly rate every job post a zero. Export a text-based copy."
        )
    return text


def load(path: str) -> Resume:
    """Read a resume. Raises ResumeError rather than returning something empty."""
    if not path:
        return Resume()
    p = Path(path).expanduser()
    if not p.is_file():
        raise ResumeError(f"{p} is not a file")

    suffix = p.suffix.lower()
    if suffix in (".txt", ".md", ".markdown"):
        text = p.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".docx":
        text = _read_docx(p)
    elif suffix == ".pdf":
        text = _read_pdf(p)
    else:
        raise ResumeError(f"{p}: unsupported format {suffix!r}. Use .docx, .md or .txt.")

    return Resume(path=str(p), text=text, skills=resume_skills(text))


# Terms that are a skill only in capitals, matched as written: FAIR the risk
# model and not "fair chance hiring" (219 of 2,251 stored adverts counted it
# missing, 2026-10-23), REST and not "rest breaks", POS and not "pos".
CASED = {"fair": "FAIR", "rest": "REST", "soc": "SOC", "r": "R", "pos": "POS",
         "cen": "CEN"}

# Compiled once: there are more terms than re's own cache holds, so compiling
# per call would compile every one of them for every advert in a scan.
_TERM_PATTERNS = tuple(
    (term, re.compile(r"(?<![A-Za-z0-9])" + re.escape(CASED[term]) + r"(?![A-Za-z0-9])")
     if term in CASED else
     re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"))
    for term in SKILL_TERMS)
# Which fields each term belongs to.
_TERM_FIELDS: dict[str, set[str]] = {}
for _name, _terms in FIELDS.items():
    for _term in _terms:
        _TERM_FIELDS.setdefault(_term, set()).add(_name)


def extract_skills(text: str) -> set[str]:
    """Which known skill terms appear, matched on word boundaries."""
    text = text or ""
    low = text.lower()
    # `term in low` first: a plain substring test, far cheaper than the
    # pattern, rules out nearly every term for any one advert.
    return {term for term, pattern in _TERM_PATTERNS
            if term in low and pattern.search(text if term in CASED else low)}


def fields_of(skills: set[str]) -> set[str]:
    """The fields a resume is in: those it names two or more skills of that
    are not WEAK. One passing mention ("built a patient care app") does not
    make a programmer's resume a nurse's. When no field has two, every field
    with one."""
    counts: dict[str, int] = {}
    for term in skills - WEAK:
        for name in _TERM_FIELDS.get(term, ()):
            counts[name] = counts.get(name, 0) + 1
    strong = {name for name, n in counts.items() if n >= 2}
    return strong or set(counts)


def near(have: set[str], wanted: set[str]) -> set[str]:
    """Of the skills an advert names, the ones in this resume's fields. A
    resume in no field yet (no skill found, or only weak ones) counts every
    one, as before fields existed."""
    fields = fields_of(have)
    if not fields:
        return set(wanted)
    return {t for t in wanted if _TERM_FIELDS.get(t, set()) & fields}


def resume_skills(text: str) -> set[str]:
    """A resume's skills: the terms it names, kept to its own fields, so a
    nurse's "go-to preceptor" is not the programming language Go."""
    found = extract_skills(text)
    return near(found, found)


def years_claimed(text: str) -> int:
    """Largest "N years" figure in the resume. A blunt instrument, and enough."""
    return max((int(m) for m in _YEARS.findall(text or "") if int(m) <= 50),
               default=0)


_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_MONTH = r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)\.?\s+((?:19|20)\d\d)"
# "- Present", and "- Up to present" / "to date" as resumes in the Philippines
# write it: a pharmacist's two current jobs were not counted (2026-10-26).
_SPAN = re.compile(_MONTH + r"\s*(?:-|\u2013|\u2014|to)\s*(?:" + _MONTH
                   + r"|(?:up\s+to\s+)?(present|current|now|date))", re.IGNORECASE)
# Words near a date range that make it study, not work; or a certificate's
# or licence's term: "(cycle Feb 2024 to Jan 2027)" was counted as work, to
# a month that had not come yet (2026-10-26).
_STUDY = re.compile(r"universit|college|school|bachelor|master|degree|diploma|"
                    r"institute|academy|education|b\.?s\.?c?\b|m\.?s\.?c?\b|"
                    # Not "certified" or "licensed": Certified Nursing
                    # Assistant and Licensed Practical Nurse are jobs.
                    r"cycle|valid|expir|renew",
                    re.IGNORECASE)


# Section headings, to tell study from work by where dates sit rather than by
# the employer's name: "University of Eastern Pangasinan (February 2026 - Up
# to present)" is a faculty job, and was dropped as study (2026-10-26).
_HEADING = re.compile(r"^[ \t•*#\-]*([A-Za-z][A-Za-z &/,'-]{2,48}?)[ \t]*:?[ \t]*$", re.MULTILINE)
_EDU_HEADING = re.compile(r"^(?:education(?:al)?\b|academic\b)", re.IGNORECASE)
_WORK_HEADING = re.compile(
    r"\b(?:experiences?|employment|work history|career history|internships?)\s*$"
    r"|^(?:work|professional|relevant|career)\b", re.IGNORECASE)
# Plural, or words no job title starts with: "Language Teacher", "Training
# Coordinator" and "Project Manager" are jobs, not headings.
_OTHER_HEADING = re.compile(
    r"^(?:skills|technical skills|key skills|leadership|awards|honou?rs|trainings|"
    r"seminars|certifications|licen[sc]es|references|character references|projects|"
    r"summary|professional summary|profile|personal profile|objectives?|"
    r"career objectives?|languages|interests|affiliations|memberships|examinations|"
    r"publications)\b", re.IGNORECASE)


def _sections(text: str) -> list[tuple[int, str]]:
    """(position, "study" | "work" | "other") for each heading the resume has."""
    out = []
    for m in _HEADING.finditer(text):
        name = m.group(1).strip()
        if len(name.split()) > 5:
            continue
        # Other first: "Professional Summary" and "Career Objective" are not work.
        kind = ("study" if _EDU_HEADING.search(name)
                else "other" if _OTHER_HEADING.search(name)
                else "work" if _WORK_HEADING.search(name) else "")
        if kind:
            out.append((m.start(), kind))
    return out


@dataclass
class WorkSpan:
    first: str                    # as written: "January 2016"
    last: str                     # "September 2023", or "Present"
    months: int                   # worked, overlapping roles counted once

    def line(self) -> str:
        years, months = divmod(self.months, 12)
        length = (f"{years} year{'s' * (years != 1)}"
                  + (f" {months} month{'s' * (months != 1)}" if months else ""))
        return (f"Work history in the resume: {self.first} to {self.last}, "
                f"{length} in all: every role together, not any one field or "
                "title, counted from its dated roles with overlaps counted once "
                "(study not counted).")


def work_span(text: str, today: tuple[int, int] | None = None) -> WorkSpan | None:
    """How long the resume's dated roles cover, counted here rather than by a
    model: "over 5 years" was the claim a model made most often and the one
    it could least back, since a resume gives dates, not totals.

    Only "Month YYYY - Month YYYY" (or "- Present") ranges count, and one
    with a university, school or degree beside it is study. Overlapping roles
    are merged. None when no work range is found.
    """
    import time

    now = today or time.localtime()[:2]
    spans = []
    sections = _sections(text or "")
    # With a work section, only its dates are work: an award's or a club's
    # "June 2021 - May 2023" is not. Without one, the words beside them decide.
    has_work = any(kind == "work" for _, kind in sections)
    for m in _SPAN.finditer(text or ""):
        under = [kind for at, kind in sections if at < m.start()]
        if under and (under[-1] == "study" or (has_work and under[-1] == "other")):
            continue
        if under and under[-1] == "work":
            start = (int(m.group(2)), _MONTHS[m.group(1)[:3].lower()])
            end = (now if m.group(5) else
                   (int(m.group(4)), _MONTHS[m.group(3)[:3].lower()]))
            end = min(end, now)
            if start <= end:
                spans.append((start, end, m))
            continue
        # Its own line before it, and a few characters after (PDF text can
        # run "December 2015Bachelor's" together), not the next entry.
        before = text[max(0, m.start() - 60):m.start()].rsplit("\n", 1)[-1]
        after = text[m.end():m.end() + 12]
        # Dates on a line of their own belong to the line above: "Bachelor
        # of Science in Chemical Engineering" then "August 2019 - July 2020"
        # was counted as a year of work.
        if not before.strip(" \t(") and not after.split("\n", 1)[0].strip(" \t)"):
            lines = text[:m.start()].rstrip().rsplit("\n", 1)
            before = lines[-1] if lines else ""
        if _STUDY.search(before + after):
            continue
        start = (int(m.group(2)), _MONTHS[m.group(1)[:3].lower()])
        end = (now if m.group(5) else
               (int(m.group(4)), _MONTHS[m.group(3)[:3].lower()]))
        # Months not yet come are not worked: a planned end date counts to now.
        end = min(end, now)
        if start <= end:
            spans.append((start, end, m))
    if not spans:
        return None
    # lambda: ranges in order of their start.
    spans.sort(key=lambda s: s[0])
    total, cur_start, cur_end = 0, spans[0][0], spans[0][1]
    for start, end, _ in spans[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
            continue
        total += _months(cur_start, cur_end)
        cur_start, cur_end = start, end
    total += _months(cur_start, cur_end)
    first = min(spans, key=lambda s: s[0])[2]
    last = max(spans, key=lambda s: s[1])[2]
    ends = (int(last.group(4)), _MONTHS[last.group(3)[:3].lower()]) if last.group(3) else now
    return WorkSpan(first=f"{first.group(1)} {first.group(2)}",
                    last=("Present" if last.group(5) and last.group(5).lower() == "date"
                          else last.group(5).capitalize() if last.group(5)
                          else "Present" if ends > now
                          else f"{last.group(3)} {last.group(4)}"),
                    months=total)


def _months(start: tuple[int, int], end: tuple[int, int]) -> int:
    """Months from start to end, both counted: Jan to Mar is 3."""
    return (end[0] - start[0]) * 12 + end[1] - start[1] + 1


# An advert naming fewer skills than this is scored as though it named this
# many. A 500-character teaser that mentions only "java" is not a perfect fit
# for anyone who knows Java; it is an advert too short to judge, and scoring
# it 1 of 1 put snippets above full adverts that matched 8 of 10.
MIN_SKILLS = 5


@dataclass
class Fit:
    score: float = 0.0            # 0-25, folded into the role's total
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.matched and not self.missing:
            return ""
        bits = []
        if self.matched:
            bits.append(f"has {', '.join(map(skill_name, self.matched[:6]))}")
        if self.missing:
            bits.append(f"wants {', '.join(map(skill_name, self.missing[:5]))}")
        return "; ".join(bits)


def fit(resume: Resume, description: str, title: str = "") -> Fit:
    """How much of what this advert asks for is already on your resume.

    Scored on the share of the advert's named skills you have, not on the
    count: an advert listing five technologies you all know is a better fit
    than one listing twenty where you know eight. Below MIN_SKILLS the share
    is taken of MIN_SKILLS instead, so a thin advert cannot score full marks.
    """
    if not resume.loaded or not description:
        return Fit()

    wanted = near(resume.skills, extract_skills(f"{title}\n{description}"))
    if not wanted:
        return Fit()

    matched = sorted(wanted & resume.skills)
    missing = sorted(wanted - resume.skills)
    share = len(matched) / max(len(wanted), MIN_SKILLS)
    return Fit(score=round(25.0 * share, 1), matched=matched, missing=missing)
