import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.config import settings
from app.auth import get_current_user
from app.database import get_db
from app.models import Document, Project, User
from app.permissions import ensure_project_access

router = APIRouter(prefix="/api", tags=["documents"], dependencies=[Depends(get_current_user)])


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    uploaded_at: datetime


@router.get("/projects/{project_id}/documents", response_model=list[DocumentOut])
def list_documents(project_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "viewer")
    if db.get(Project, project_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return (
        db.query(Document)
        .filter(Document.project_id == project_id)
        .order_by(Document.id.desc())
        .all()
    )


@router.post("/projects/{project_id}/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    project_id: int, file: UploadFile, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    ensure_project_access(db, current, project_id, "editor")
    if db.get(Project, project_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    if not file.filename or not file.filename.lower().endswith(".md"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "only .md files are accepted")

    target_dir: Path = settings.uploads_dir / str(project_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename).name
    storage_path = target_dir / f"{uuid.uuid4().hex}_{safe_name}"
    storage_path.write_bytes(file.file.read())

    doc = Document(project_id=project_id, filename=file.filename, storage_path=str(storage_path), created_by=current.id)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/documents/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    ensure_project_access(db, current, doc.project_id, "editor")
    return FileResponse(doc.storage_path, filename=doc.filename, media_type="text/markdown")


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    ensure_project_access(db, current, doc.project_id, "editor")
    Path(doc.storage_path).unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
