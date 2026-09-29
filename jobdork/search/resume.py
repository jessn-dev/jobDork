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

# Skills worth matching on. Deliberately a list rather than "every capitalised
# word": the second approach matches company names, city names and the word
# "Agile" in a sentence about culture, and scores everything the same.
SKILL_TERMS = (
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
    # ml
    "machine learning", "deep learning", "pytorch", "tensorflow",
    "scikit-learn", "nlp", "llm", "computer vision", "mlops",
    # infra
    "aws", "azure", "gcp", "kubernetes", "docker", "terraform", "ansible",
    "jenkins", "gitlab", "github actions", "ci/cd", "linux", "nginx",
    "microservices", "serverless", "lambda", "prometheus", "grafana",
    "datadog", "helm", "argocd",
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
)

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


def _read_docx(path: Path) -> str:
    """A .docx is a zip; the text lives in word/document.xml."""
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", "replace")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ResumeError(f"{path} is not a readable .docx: {exc}") from exc
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    return re.sub(r"\n{3,}", "\n\n", xml).strip()


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
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:                      # pypdf raises a wide variety
        raise ResumeError(f"{path} could not be read as a PDF: {exc}") from exc

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

    return Resume(path=str(p), text=text, skills=extract_skills(text))


def extract_skills(text: str) -> set[str]:
    """Which known skill terms appear, matched on word boundaries."""
    low = (text or "").lower()
    found = set()
    for term in SKILL_TERMS:
        pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
        if re.search(pattern, low):
            found.add(term)
    return found


def years_claimed(text: str) -> int:
    """Largest "N years" figure in the resume. A blunt instrument, and enough."""
    return max((int(m) for m in _YEARS.findall(text or "") if int(m) <= 50),
               default=0)


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

    wanted = extract_skills(f"{title}\n{description}")
    if not wanted:
        return Fit()

    matched = sorted(wanted & resume.skills)
    missing = sorted(wanted - resume.skills)
    share = len(matched) / max(len(wanted), MIN_SKILLS)
    return Fit(score=round(25.0 * share, 1), matched=matched, missing=missing)
