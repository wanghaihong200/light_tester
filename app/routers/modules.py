from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Case, FeaturePoint, Module, Project

router = APIRouter(prefix="/api", tags=["modules"])


class ModuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: int | None = None


class ModuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: int | None = None


def _get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return project


def _module_dict(module: Module) -> dict:
    return {
        "id": module.id,
        "name": module.name,
        "children": [_module_dict(child) for child in module.children],
        "feature_points": [
            {
                "id": fp.id,
                "name": fp.name,
                "cases": [
                    {
                        "id": case.id,
                        "title": case.title,
                        "priority": case.priority,
                    }
                    for case in fp.cases
                ],
            }
            for fp in module.feature_points
        ],
    }


@router.get("/projects/{project_id}/tree")
def get_tree(project_id: int, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    roots = (
        db.query(Module)
        .filter(Module.project_id == project_id, Module.parent_id.is_(None))
        .order_by(Module.sort_order, Module.id)
        .all()
    )
    return [_module_dict(m) for m in roots]


@router.post("/projects/{project_id}/modules", status_code=status.HTTP_201_CREATED)
def create_module(project_id: int, payload: ModuleCreate, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)
    if payload.parent_id is not None:
        parent = db.get(Module, payload.parent_id)
        if parent is None or parent.project_id != project_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid parent_id")
    module = Module(project_id=project_id, **payload.model_dump())
    db.add(module)
    db.commit()
    db.refresh(module)
    return {"id": module.id, "name": module.name, "parent_id": module.parent_id}


def _is_descendant(db: Session, candidate_id: int, ancestor_id: int) -> bool:
    node = db.get(Module, candidate_id)
    while node is not None and node.parent_id is not None:
        if node.parent_id == ancestor_id:
            return True
        node = db.get(Module, node.parent_id)
    return False


@router.put("/modules/{module_id}")
def update_module(module_id: int, payload: ModuleUpdate, db: Session = Depends(get_db)):
    module = db.get(Module, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module not found")
    data = payload.model_dump(exclude_unset=True)
    if "parent_id" in data and data["parent_id"] is not None:
        if data["parent_id"] == module_id or _is_descendant(db, data["parent_id"], module_id):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot move under self/descendant")
    for field, value in data.items():
        setattr(module, field, value)
    db.commit()
    db.refresh(module)
    return {"id": module.id, "name": module.name, "parent_id": module.parent_id}


@router.delete("/modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_module(module_id: int, db: Session = Depends(get_db)):
    module = db.get(Module, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module not found")
    db.delete(module)
    db.commit()
