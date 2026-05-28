"""AI adapters. Pick via AI_BACKEND env var.

Interface:
    invoke(prompt, **kwargs) -> str
    retrieve_and_generate(query, kb_id="") -> dict with {"answer": str, "citations": list}
"""
from typing import Any


class BedrockAI:
    """Real Amazon Bedrock client. Uses Converse API for invoke; bedrock-agent-runtime for RAG."""

    def __init__(self, region: str, model_id: str):
        import boto3
        self.region = region
        self.model_id = model_id
        self.runtime = boto3.client("bedrock-runtime", region_name=region)
        self.agent_runtime = boto3.client("bedrock-agent-runtime", region_name=region)
        self.sts = boto3.client("sts", region_name=region)

    def _model_arn(self) -> str:
        if self.model_id.startswith("arn:"):
            return self.model_id
        if self.model_id.startswith(("global.", "apac.", "us.", "eu.", "au.")):
            account_id = self.sts.get_caller_identity()["Account"]
            return f"arn:aws:bedrock:{self.region}:{account_id}:inference-profile/{self.model_id}"
        return f"arn:aws:bedrock:{self.region}::foundation-model/{self.model_id}"

    def invoke(self, prompt: str, **kwargs: Any) -> str:
        max_tokens = kwargs.get("max_tokens", 1024)
        resp = self.runtime.converse(
            modelId=self.model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": kwargs.get("temperature", 0.2)},
        )
        return resp["output"]["message"]["content"][0]["text"]

    def converse(self, system_prompt: str, user_prompt: str, prior_messages: list[dict] | None = None, **kwargs: Any) -> str:
        max_tokens = kwargs.get("max_tokens", 1024)
        messages = []
        for message in prior_messages or []:
            role = message.get("role")
            if role not in {"user", "assistant"}:
                continue
            messages.append({"role": role, "content": [{"text": message.get("content", "")}]})
        messages.append({"role": "user", "content": [{"text": user_prompt}]})
        resp = self.runtime.converse(
            modelId=self.model_id,
            system=[{"text": system_prompt}],
            messages=messages,
            inferenceConfig={"maxTokens": max_tokens, "temperature": kwargs.get("temperature", 0.2)},
        )
        return resp["output"]["message"]["content"][0]["text"]

    def retrieve_and_generate(self, query: str, kb_id: str = "") -> dict:
        if not kb_id:
            raise ValueError("VECTOR_BEDROCK_KB_ID must be set for Bedrock KB retrieve_and_generate")
        resp = self.agent_runtime.retrieve_and_generate(
            input={"text": query},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": kb_id,
                    "modelArn": self._model_arn(),
                },
            },
        )
        return {
            "answer": resp["output"]["text"],
            "citations": [
                {
                    "text": ref.get("content", {}).get("text", ""),
                    "source": ref.get("location", {}),
                }
                for citation in resp.get("citations", [])
                for ref in citation.get("retrievedReferences", [])
            ],
        }


class LocalAI:
    """Local stub. Returns canned responses. Use for development without AWS credentials."""

    def invoke(self, prompt: str, **kwargs: Any) -> str:
        snippet = prompt[:200].replace("\n", " ")
        return (
            f"[LOCAL_AI_STUB] Received prompt: {snippet!r}... "
            "Set AI_BACKEND=bedrock + AWS credentials for real Bedrock output."
        )

    def converse(self, system_prompt: str, user_prompt: str, prior_messages: list[dict] | None = None, **kwargs: Any) -> str:
        combined = " ".join(
            [system_prompt[:120], *(m.get("content", "")[:80] for m in (prior_messages or [])[-3:]), user_prompt[:200]]
        )
        return f"[LOCAL_AI_STUB] Received chat prompt: {combined!r}..."

    def retrieve_and_generate(self, query: str, kb_id: str = "") -> dict:
        return {
            "answer": (
                f"[LOCAL_AI_STUB] Query received: {query!r}. "
                "Set AI_BACKEND=bedrock and VECTOR_BACKEND=bedrock_kb for real RAG."
            ),
            "citations": [],
        }
