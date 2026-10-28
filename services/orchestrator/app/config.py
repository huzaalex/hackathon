import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bedrock_api_key: str = os.environ.get("BEDROCK_API_KEY", "")
    aws_region: str = os.environ.get("AWS_REGION", "us-east-1")
    llm_model: str = os.environ.get("LLM_MODEL", "anthropic.claude-opus-5-5")
    llm_fallback_model: str = os.environ.get("LLM_FALLBACK_MODEL", "")
    llm_effort: str = os.environ.get("LLM_EFFORT", "medium")
    llm_subagent_effort: str = os.environ.get("LLM_SUBAGENT_EFFORT", "low")

    core_banking_url: str = os.environ.get("CORE_BANKING_URL", "http://localhost:8001")
    rules_engine_url: str = os.environ.get("RULES_ENGINE_URL", "http://localhost:8002")
    document_service_url: str = os.environ.get("DOCUMENT_SERVICE_URL", "http://localhost:8003")
    fx_service_url: str = os.environ.get("FX_SERVICE_URL", "http://localhost:8004")

    data_dir: str = os.environ.get("DATA_DIR", "/data")
    bank_name: str = os.environ.get("BANK_NAME", "Banca Demo S.A.")

    # Impact metrics: list price of the model (USD per million tokens) and the manual-work baseline.
    # The baseline should come from the bank interview in docs/research.md.
    price_input_per_mtok: float = float(os.environ.get("PRICE_INPUT_PER_MTOK", "4.0"))
    price_output_per_mtok: float = float(os.environ.get("PRICE_OUTPUT_PER_MTOK", "20.0"))
    manual_minutes_per_case: float = float(os.environ.get("MANUAL_MINUTES_PER_CASE", "20"))
    operator_minutes_per_review: float = float(os.environ.get("OPERATOR_MINUTES_PER_REVIEW", "3"))

    @property
    def llm_base_url(self) -> str:
        # Claude in Amazon Bedrock, Messages API endpoint; the Bedrock API key is sent as a bearer token
        return f"https://bedrock-mantle.{self.aws_region}.api.aws/anthropic"


settings = Settings()
