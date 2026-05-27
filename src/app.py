"""FastAPI application — runtime-agnostic.

Runs on:
  - Local laptop:        uvicorn src.app:app --reload
  - AWS Lambda:          wrap with Mangum (pip install mangum) → expose `handler`
  - ECS Fargate / EC2:   uvicorn or gunicorn
  - App Runner:          uvicorn

The choice is yours. Code stays the same.
"""
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import config
from src.adapters import factory
from src import handlers


app = FastAPI(title="StudyBot — W7 Capstone Starter")


# CORS — allow frontend to live on a different origin (CloudFront / Amplify / separate ALB).
# CORS_ORIGINS env var controls this; default '*' is permissive for hackathon.
_allowed = ["*"] if config.cors_origins == "*" else [o.strip() for o in config.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singletons. In serverless this gets re-initialized per cold start; that's fine.
ai_client = factory.make_ai()
storage = factory.make_storage()
userstore = factory.make_userstore()
vector_store = factory.make_vector()


def _resolve_user_id(x_user_id: str | None) -> str:
    """Auth abstraction: extract user_id from header, fall back to default for local dev.

    In production you populate X-User-Id from:
      - Cognito JWT (decoded by API Gateway authorizer)
      - Signed URL claim
      - Custom auth Lambda
    """
    return x_user_id or config.default_user_id


class QueryRequest(BaseModel):
    question: str


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "backends": {
            "ai": config.ai_backend,
            "storage": config.storage_backend,
            "userstore": config.userstore_backend,
            "vector": config.vector_backend,
        },
    }


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    x_user_id: str | None = Header(default=None),
) -> dict:
    user_id = _resolve_user_id(x_user_id)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    return handlers.handle_upload(
        user_id=user_id,
        filename=file.filename or "untitled",
        data=data,
        storage=storage,
        userstore=userstore,
        vector_store=vector_store,
    )


@app.post("/query")
def query(req: QueryRequest, x_user_id: str | None = Header(default=None)) -> dict:
    user_id = _resolve_user_id(x_user_id)
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Empty question")
    return handlers.handle_query(
        user_id=user_id,
        question=req.question,
        ai_client=ai_client,
        userstore=userstore,
        vector_store=vector_store,
        vector_backend=config.vector_backend,
        bedrock_kb_id=config.vector_bedrock_kb_id,
    )


@app.get("/docs/list")
def list_docs(x_user_id: str | None = Header(default=None)) -> dict:
    return handlers.handle_list_docs(_resolve_user_id(x_user_id), userstore)


@app.get("/queries/recent")
def recent(x_user_id: str | None = Header(default=None), limit: int = 10) -> dict:
    return handlers.handle_recent_queries(_resolve_user_id(x_user_id), userstore, limit=limit)


class DocRequest(BaseModel):
    doc_id: str


class QuizSubmitRequest(BaseModel):
    doc_id: str
    score: int
    total: int


class AuthRequest(BaseModel):
    username: str
    password: str


class FolderAssignRequest(BaseModel):
    doc_id: str
    folder_name: str


class FolderQuizRequest(BaseModel):
    folder_name: str


@app.post("/summary")
def summary(req: DocRequest, x_user_id: str | None = Header(default=None)) -> dict:
    """Generate a one-page summary + top 5 testable concepts for a specific document."""
    user_id = _resolve_user_id(x_user_id)
    if not req.doc_id.strip():
        raise HTTPException(status_code=400, detail="doc_id is required")
    return handlers.handle_summary(
        user_id=user_id,
        doc_id=req.doc_id,
        ai_client=ai_client,
        vector_store=vector_store,
    )


@app.post("/quiz")
def quiz(req: DocRequest, x_user_id: str | None = Header(default=None)) -> dict:
    """Generate a 10-question multiple-choice quiz from a specific document."""
    user_id = _resolve_user_id(x_user_id)
    if not req.doc_id.strip():
        raise HTTPException(status_code=400, detail="doc_id is required")
    return handlers.handle_quiz(
        user_id=user_id,
        doc_id=req.doc_id,
        ai_client=ai_client,
        vector_store=vector_store,
    )


@app.post("/docs/folder")
def assign_folder(req: FolderAssignRequest, x_user_id: str | None = Header(default=None)) -> dict:
    """Assign a document to a folder."""
    user_id = _resolve_user_id(x_user_id)
    if not req.doc_id.strip() or not req.folder_name.strip():
        raise HTTPException(status_code=400, detail="doc_id and folder_name are required")
    return handlers.handle_assign_folder(
        user_id=user_id,
        doc_id=req.doc_id,
        folder_name=req.folder_name,
        userstore=userstore,
    )


@app.post("/quiz/folder")
def quiz_folder(req: FolderQuizRequest, x_user_id: str | None = Header(default=None)) -> dict:
    """Generate a 10-question multiple-choice quiz from all documents in a folder."""
    user_id = _resolve_user_id(x_user_id)
    if not req.folder_name.strip():
        raise HTTPException(status_code=400, detail="folder_name is required")
    return handlers.handle_quiz_folder(
        user_id=user_id,
        folder_name=req.folder_name,
        ai_client=ai_client,
        vector_store=vector_store,
        userstore=userstore,
    )


@app.post("/quiz/submit")
def quiz_submit(req: QuizSubmitRequest, x_user_id: str | None = Header(default=None)) -> dict:
    """Save a quiz result for the learning dashboard."""
    user_id = _resolve_user_id(x_user_id)
    return handlers.handle_quiz_submit(
        user_id=user_id,
        doc_id=req.doc_id,
        score=req.score,
        total=req.total,
        userstore=userstore,
    )


@app.get("/dashboard")
def dashboard(x_user_id: str | None = Header(default=None)) -> dict:
    """Return aggregated learning stats for the dashboard."""
    return handlers.handle_dashboard(_resolve_user_id(x_user_id), userstore)


@app.post("/auth/register")
def register(req: AuthRequest) -> dict:
    """Register a new user."""
    result = handlers.handle_register(req.username, req.password, userstore)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/auth/login")
def login(req: AuthRequest) -> dict:
    """Authenticate a user."""
    result = handlers.handle_login(req.username, req.password, userstore)
    if "error" in result:
        raise HTTPException(status_code=401, detail=result["error"])
    return result


# ---- Static frontend ----
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


if config.serve_frontend:
    @app.get("/")
    def index() -> FileResponse:
        """Convenience: serves frontend/index.html at /. Set SERVE_FRONTEND=false
        if you deploy the frontend separately (CloudFront+S3, Amplify, ALB)."""
        return FileResponse(FRONTEND_DIR / "index.html")


# ---- AWS Lambda handler (Mangum) ----
try:
    from mangum import Mangum
    handler = Mangum(app)
except ImportError:
    pass
