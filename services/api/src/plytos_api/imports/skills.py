"""How common tools and methods are spelled, so a skills list matches what recruiters search.

Applicant tracking systems match keywords, often exactly. "Sagemaker" can still
match, but a misspelling like "Milvius" never will. This is a small, curated
list, not a dictionary of every product.
"""

import re

_CANONICAL = """
Airflow Alteryx Android Angular Ansible Apptio Asana AWS Azure BigQuery Bitbucket
C# C++ Cassandra CircleCI Confluence Copilot CSS Databricks dbt Django Docker
DynamoDB Elasticsearch Excel FastAPI Figma Flask GCP Git GitHub GitLab Go GraphQL
Hadoop HTML HubSpot Hugging Face Java JavaScript Jenkins Jira Jupyter Kafka Keras Kotlin
Kubernetes LangChain LangGraph LightGBM Linux Llama Looker MATLAB Milvus MLflow
MongoDB MySQL NetSuite Next.js NLTK Node.js NumPy OpenAI Oracle pandas PostgreSQL
PowerPoint Power BI PySpark Python PyTorch QuickBooks R React Redis Redshift
Ruby Rust Salesforce SageMaker SAP SAS scikit-learn Scala Snowflake Spark SPSS SQL
Stata Swift Tableau TensorFlow Terraform TypeScript Vertex AI Workday XGBoost
"""
CANONICAL = {name.replace(" ", " ").lower(): name.replace(" ", " ") for name in _CANONICAL.split()}
# Misspellings seen in the wild, keyed by the wrong form.
MISSPELLINGS = {
    "milvius": "Milvus",
    "tensorflo": "TensorFlow",
    "pytourch": "PyTorch",
    "scikit learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "sci-kit learn": "scikit-learn",
    "postgres sql": "PostgreSQL",
    "power-bi": "Power BI",
    "powerbi": "Power BI",
    "javascipt": "JavaScript",
    "kubernates": "Kubernetes",
    "tableu": "Tableau",
    "databrick": "Databricks",
    "lang chain": "LangChain",
    "jupiter": "Jupyter",
    "hugging face": "Hugging Face",
}
_ACRONYMS_OK = {"llama": {"LLaMA", "Llama"}}


def spelling_fixes(skills: list[str]) -> list[tuple[str, str]]:
    """(as written, as usually written) for each skill that's spelled differently."""
    fixes: list[tuple[str, str]] = []
    for skill in skills:
        for token in _tokens(skill):
            low = token.lower()
            right = MISSPELLINGS.get(low) or CANONICAL.get(low)
            if right is None or token == right or token in _ACRONYMS_OK.get(low, set()):
                continue
            if len(token) <= 2:
                continue
            fixes.append((token, right))
    return list(dict.fromkeys(fixes))


def _tokens(skill: str) -> list[str]:
    """The skill, and its parts when it names several ("AWS Sagemaker", "LangChain/LangGraph")."""
    parts = [skill.strip()]
    parts += [p for p in re.split(r"[/\s]+", skill) if p and p != skill.strip()]
    return parts
