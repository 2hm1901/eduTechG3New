# StudyBot — W7 Capstone Starter

**Domain:** EduTech. Upload lecture files into a shared bank, compose folder workspaces, generate 5 study topics, chat in sessions, and run quizzes per topic.

This starter runs **completely locally** with zero AWS credentials. Switch env vars to flip to AWS Bedrock + KB + S3 + your chosen DB when you're ready to deploy.

---

## Phạm vi task hiện có

Repo này đã có một MVP chạy được cho 4 task bên dưới. Kiến trúc hiện tại là local-first, nhưng vẫn giữ adapter Bedrock/KB/S3 để sau này chuyển sang AWS bằng env vars.

### Task 1 - Upload & Summary

Đã có trong code:
- Đăng ký / đăng nhập người dùng (`/auth/register`, `/auth/login`)
- Upload PDF/TXT/MD vào bank (`POST /api/bank/documents/upload`)
- Trích xuất text cục bộ từ file upload
- Lưu metadata tài liệu vào SQLite
- Liệt kê tài liệu trong bank (`GET /api/bank/documents`)
- Tạo folder và thêm file vào folder
- Generate topic từ nội dung folder (`POST /api/folders/{folder_id}/topics/generate`)

Chưa có hoặc mới làm một phần:
- Endpoint tóm tắt 1 trang cho tài liệu
- OCR / hiểu PDF dạng ảnh ở mức slide
- Bộ 5 chủ đề gắn chặt riêng với từng slide

### Task 2 - Q&A with Citation

Đã có trong code:
- Chat session theo folder (`POST /api/folders/{folder_id}/sessions`)
- API chat messages (`GET/POST /api/sessions/{session_id}/messages`)
- Retrieval trên tài liệu đã upload
- AI trả lời qua adapter model
- Trả về citation kèm câu trả lời
- Prompt có bám topic khi user chọn topic

Chưa có hoặc mới làm một phần:
- Citation theo mức slide
- Mapping chắc chắn `1 topic = 1 slide`
- Chế độ retrieval chỉ theo slide

### Task 3 - Quiz Generation

Đã có trong code:
- Tạo quiz theo topic (`POST /api/topics/{topic_id}/quiz`)
- Nộp quiz và lưu kết quả (`POST /api/topics/{topic_id}/quiz/submit`)
- Lưu quiz attempt trong SQLite
- Cập nhật progress topic sau khi nộp quiz
- Có page quiz trên frontend

Chưa có hoặc mới làm một phần:
- Quiz chất lượng cao cho PDF nhiều ảnh
- Mức độ khó của quiz
- Scope quiz theo từng slide

### Task 4 - Learning Dashboard

Đã có trong code:
- API dashboard theo folder (`GET /api/folders/{folder_id}/dashboard`)
- Hiển thị số file, số câu hỏi, quiz history và topic progress
- Có page dashboard trên frontend
- Lưu quiz history trong SQLite
- Track progress theo folder/topic

Chưa có hoặc mới làm một phần:
- Dashboard cá nhân global cho toàn bộ folder
- Analytics học tập theo tuần
- Streak / spaced repetition dài hạn

---

## Run locally (2 minutes)

```bash
python3 -m venv .venv
source .venv/bin/activate                # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                     # all backends default to LOCAL
uvicorn src.app:app --reload --port 8000

# In another terminal or browser:
curl http://localhost:8000/health
open http://localhost:8000               # macOS — or just navigate to that URL
```

**Smoke test the workspace flow:**

```bash
# Upload the sample lecture into the bank
curl -X POST http://localhost:8000/api/bank/documents/upload \
  -H "X-User-Id: alice" \
  -F "file=@sample_data/sample_lecture.txt"

# Create a folder
curl -X POST http://localhost:8000/api/folders \
  -H "X-User-Id: alice" -H "Content-Type: application/json" \
  -d '{"name":"Exam Revision"}'

# List uploaded docs in the bank
curl http://localhost:8000/api/bank/documents -H "X-User-Id: alice"
```

The browser UI at `http://localhost:8000` does the same thing visually.

Run the test suite:
```bash
pytest -v
```

---

## Sau khi pull repo: build lại Terraform Lambda package

Các thư mục thư viện trong `terraform/lambda_api` và các file `.zip` không commit lên Git. Sau khi pull repo mới, chạy các lệnh dưới đây từ repo root để tạo lại package trước khi `terraform apply`.

Yêu cầu máy có Python 3, pip, Terraform CLI, AWS CLI và AWS credentials.

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd terraform

python3 -m pip install \
  --platform manylinux2014_aarch64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --target lambda_api \
  fastapi mangum python-multipart pydantic

cd lambda_api
zip -qr api_backend.zip \
  src \
  fastapi starlette pydantic pydantic_core \
  annotated_doc annotated_types anyio idna mangum \
  multipart python_multipart typing_inspection typing_extensions.py \
  *.dist-info
cd ../..

cd terraform/lambda_placeholder
zip -q upload_handler.zip upload_handler.py
zip -q chat.zip chat.py
zip -q summarize_quiz.zip summarize_quiz.py
zip -q dashboard.zip dashboard.py

mkdir -p build_text_extract
python3 -m pip install \
  --platform manylinux2014_aarch64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --target build_text_extract \
  pypdf
cp text_extraction.py build_text_extract/
cd build_text_extract
zip -qr ../text_extraction.zip .
cd ../../..
```

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

Set-Location terraform

python -m pip install `
  --platform manylinux2014_aarch64 `
  --implementation cp `
  --python-version 3.12 `
  --only-binary=:all: `
  --target lambda_api `
  fastapi mangum python-multipart pydantic

Set-Location lambda_api
Compress-Archive -Path `
  src, `
  fastapi, starlette, pydantic, pydantic_core, `
  annotated_doc, annotated_types, anyio, idna, mangum, `
  multipart, python_multipart, typing_inspection, typing_extensions.py, `
  *.dist-info `
  -DestinationPath api_backend.zip -Force
Set-Location ..\..

Set-Location terraform\lambda_placeholder
Compress-Archive -Path upload_handler.py -DestinationPath upload_handler.zip -Force
Compress-Archive -Path chat.py -DestinationPath chat.zip -Force
Compress-Archive -Path summarize_quiz.py -DestinationPath summarize_quiz.zip -Force
Compress-Archive -Path dashboard.py -DestinationPath dashboard.zip -Force

New-Item -ItemType Directory -Force build_text_extract | Out-Null
python -m pip install `
  --platform manylinux2014_aarch64 `
  --implementation cp `
  --python-version 3.12 `
  --only-binary=:all: `
  --target build_text_extract `
  pypdf
Copy-Item text_extraction.py build_text_extract\
Set-Location build_text_extract
Compress-Archive -Path * -DestinationPath ..\text_extraction.zip -Force
Set-Location ..\..\..
```

Nếu PowerShell báo không chạy được `Activate.ps1`, chạy lệnh này trong cùng terminal rồi activate lại:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Deploy Terraform trên cả macOS/Linux/Windows:

```bash
cd terraform
terraform init
terraform plan
terraform apply
cd ..
```

Terraform state dùng remote backend S3, không commit file `terraform.tfstate` lên Git. Backend hiện tại:

- Bucket: `ai-study-buddy-tfstate-894597652722`
- Key: `w7-hackathon/terraform.tfstate`
- Region: `ap-southeast-2`
- Lock: S3 native lockfile (`use_lockfile = true`)

Dev mới clone repo chỉ cần có AWS credentials đúng account rồi chạy `terraform init`; Terraform sẽ tự đọc state từ S3 nên `terraform plan` không tạo lại toàn bộ resource.

### Update frontend lên S3 + CloudFront

Chạy từ repo root sau khi sửa file trong `frontend/`:

```bash
aws s3 sync frontend/ s3://ai-study-buddy-frontend-894597652722 --delete
aws cloudfront create-invalidation --distribution-id E1PYS7LV0BH3PN --paths "/*"
```

### Update Lambda code

Ví dụ build lại Lambda `text_extraction`:

```bash
cd terraform/lambda_placeholder
zip -r text_extraction.zip text_extraction.py
cd ../..
```

Sau đó apply Terraform để đẩy zip mới lên Lambda:

```bash
cd terraform
terraform apply
cd ..
```

Nếu cần build lại từ đầu trên macOS/Linux:

```bash
rm -rf terraform/lambda_api/{fastapi,starlette,pydantic,pydantic_core,annotated_doc,annotated_types,anyio,idna,mangum,multipart,python_multipart,typing_inspection,bin,*.dist-info,typing_extensions.py,api_backend.zip}
rm -rf terraform/lambda_placeholder/{build_text_extract,*.zip}
```

Nếu cần build lại từ đầu trên Windows PowerShell:

```powershell
Remove-Item -Recurse -Force `
  terraform\lambda_api\fastapi, `
  terraform\lambda_api\starlette, `
  terraform\lambda_api\pydantic, `
  terraform\lambda_api\pydantic_core, `
  terraform\lambda_api\annotated_doc, `
  terraform\lambda_api\annotated_types, `
  terraform\lambda_api\anyio, `
  terraform\lambda_api\idna, `
  terraform\lambda_api\mangum, `
  terraform\lambda_api\multipart, `
  terraform\lambda_api\python_multipart, `
  terraform\lambda_api\typing_inspection, `
  terraform\lambda_api\bin, `
  terraform\lambda_api\*.dist-info, `
  terraform\lambda_api\typing_extensions.py, `
  terraform\lambda_api\api_backend.zip, `
  terraform\lambda_placeholder\build_text_extract, `
  terraform\lambda_placeholder\*.zip `
  -ErrorAction SilentlyContinue
```

---

## Team workflow (avoid conflicts)

This repo is designed **local-first**:
- Local dev should use `.env` with `AI_BACKEND=local`, `STORAGE_BACKEND=local`, `USERSTORE_BACKEND=sqlite`, `VECTOR_BACKEND=local`.
- Only flip to AWS backends for shared dev / staging / prod environments.

Frontend config rules:
- `frontend/config.js` is **runtime config** and must not contain any secrets (API keys, credentials).
- For local dev with `SERVE_FRONTEND=true`, keep `window.API_BASE_URL = \"\"` (same-origin).
- For AWS, set `window.API_BASE_URL` to the `ApiEndpoint` output from SAM.

Recommended dev setup options:
1) **Shared dev stack**: one AWS stack (e.g. `studybot-dev`) and everyone points FE to it.
   - Use a per-user prefix/namespace in S3 keys (and optionally DynamoDB sort keys) to avoid overwriting each other.
2) **Per-developer stack**: each dev deploys their own stack (`studybot-dev-<name>`) and points FE to their own `ApiEndpoint`.

---

## What's in the code

```
src/
├── app.py               FastAPI app + routes. Runs in Lambda, ECS, EC2, App Runner.
├── config.py            Reads ALL settings from env vars. No hardcoded service names.
├── handlers.py          Business logic for Bank -> Folder -> Topic -> Session -> Quiz.
└── adapters/
    ├── ai.py            BedrockAI (real Bedrock Converse + KB RAG) | LocalAI (stub)
    ├── storage.py       S3Storage | LocalStorage (filesystem)
    ├── sqlite_store.py  Normalized local SQLite store for the workspace MVP
    ├── userstore.py     Non-local adapters kept for future DynamoDB / SQL backends
    ├── vector.py        BedrockKBVector | LocalVector (in-memory keyword index)
    └── factory.py       Reads config → instantiates the chosen adapter
```

---

## 9 deployment decisions you still make

When you deploy, every one of these is YOUR call (set in `.env`):

| # | Decision | Env var | Choices |
|---|----------|---------|---------|
| 1 | Compute runtime | (deploy-time) | Lambda (via Mangum) / ECS Fargate / EC2 / App Runner |
| 2 | DB backend | `USERSTORE_BACKEND` | `dynamodb` / `postgres` / `sqlite` |
| 3 | Vector store | `VECTOR_BACKEND` + KB config | Bedrock KB on OpenSearch Serverless / S3 Vectors / Aurora pgvector |
| 4 | Frontend hosting | (deploy-time) | CloudFront+S3 / Amplify / served by backend / ALB+EC2 |
| 5 | Identity | populating `X-User-Id` header | Cognito JWT / hardcoded / signed URL / custom Lambda |
| 6 | VPC topology | (deploy-time) | Subnet layout, SG rules, NAT vs VPC Endpoints |
| 7 | IaC | (deploy-time) | Console / CFN / CDK / Terraform / SAM |
| 8 | Observability | (deploy-time) | CloudWatch dashboard, alarms, custom metrics |
| 9 | Cost optimization | (deploy-time) | Instance sizing, on-demand vs reserved, single-AZ |

Trainers will ask **WHY** for each.

---

## Deploy to AWS — env flip

Once your AWS resources are provisioned, edit `.env`:

```diff
- AI_BACKEND=local
+ AI_BACKEND=bedrock
+ AI_MODEL_ID=global.amazon.nova-2-lite-v1:0

- STORAGE_BACKEND=local
+ STORAGE_BACKEND=s3
+ STORAGE_BUCKET=studybot-uploads-g<N>-<accountid>

- USERSTORE_BACKEND=sqlite
+ USERSTORE_BACKEND=dynamodb           # OR postgres — your call
+ USERSTORE_TABLE=studybot-users

- VECTOR_BACKEND=local
+ VECTOR_BACKEND=bedrock_kb
+ VECTOR_BEDROCK_KB_ID=ABCDEFG123      # from your Bedrock KB
```

Then deploy with your chosen IaC.

**Lambda packaging example:**
```python
# In your Lambda entry file, e.g. lambda_entry.py
from mangum import Mangum
from src.app import app
handler = Mangum(app)
```
Add `mangum>=0.17` to requirements + zip everything + upload.

**ECS Fargate / EC2 / App Runner:**
```
uvicorn src.app:app --host 0.0.0.0 --port 8000
```
Wrap in a Dockerfile of your choice.

---

## Customization ideas (for Criterion I — 10%)

The provided code is the baseline. To earn the Original Architecture criterion you should ADD something on top:

- **Spaced repetition** — track which doc/chunk a user has reviewed and surface stale ones
- **Difficulty levels** — generate quizzes at "easy / medium / hard"
- **Multi-language** — detect input language, prompt accordingly
- **Audio input** — accept .mp3 via S3 + Transcribe → ingest transcript
- **Folder retrieval modes** — toggle between all-doc retrieval and folder-only retrieval with evidence
- **Citation viewer** — frontend highlights the source chunk in the original PDF

Document your customization in `docs/W7_evidence.md` section 7.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: No module named 'src'` | Run uvicorn from the `studybot/` directory, not from `src/` |
| `[LOCAL_AI_STUB]` in answer | You're still in local mode. Set `AI_BACKEND=bedrock` + AWS creds. |
| `AccessDeniedException` on Bedrock | Enable model access in Bedrock console first (Haiku + Titan Embeddings v2) |
| `botocore.exceptions.NoCredentialsError` | Set AWS creds: `aws configure` or env `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` |
| Bedrock KB returns empty | KB ingestion job hasn't run. Sync the KB in console after uploading docs to its S3 source. |
| SQLite "database is locked" | Don't run multiple uvicorn workers against SQLite. Use DynamoDB or Postgres in production. |
