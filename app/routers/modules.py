from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Case, FeaturePoint, Module, Project

router = APIRouter(prefix="/api", tags=["modules"], dependencies=[Depends(get_current_user)])


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


@router.get("/projects/{project_id}/tree")
def get_tree(project_id: int, db: Session = Depends(get_db)):
    _get_project_or_404(db, project_id)

    # Single query: all modules for the project
    all_modules = (
        db.query(Module)
        .filter(Module.project_id == project_id)
        .order_by(Module.sort_order, Module.id)
        .all()
    )
    module_ids = [m.id for m in all_modules]
    modules_by_id: dict[int, dict] = {}
    children_by_parent: dict[int | None, list[dict]] = {}

    for m in all_modules:
        d = {"id": m.id, "name": m.name, "children": [], "feature_points": []}
        modules_by_id[m.id] = d
        children_by_parent.setdefault(m.parent_id, []).append(d)

    # Wire children into their parent module dicts
    for m in all_modules:
        modules_by_id[m.id]["children"] = children_by_parent.get(m.id, [])

    if module_ids:
        # Single query: all feature points for these modules
        all_fps = (
            db.query(FeaturePoint)
            .filter(FeaturePoint.module_id.in_(module_ids))
            .order_by(FeaturePoint.sort_order, FeaturePoint.id)
            .all()
        )
        fp_ids = [fp.id for fp in all_fps]
        fps_by_id: dict[int, dict] = {}
        cases_by_fp: dict[int, list[dict]] = {}

        for fp in all_fps:
            fp_dict: dict = {"id": fp.id, "name": fp.name, "cases": []}
            fps_by_id[fp.id] = fp_dict
            cases_by_fp.setdefault(fp.id, [])

        if fp_ids:
            # Single query: all cases for these feature points
            all_cases = (
                db.query(Case)
                .filter(Case.feature_point_id.in_(fp_ids))
                .order_by(Case.sort_order, Case.id)
                .all()
            )
            for case in all_cases:
                cases_by_fp[case.feature_point_id].append(
                    {
                        "id": case.id,
                        "title": case.title,
                        "priority": case.priority,
                        "executed_pass": case.executed_pass,
                    }
                )

        for fp in all_fps:
            fps_by_id[fp.id]["cases"] = cases_by_fp.get(fp.id, [])

        for fp in all_fps:
            if fp.module_id in modules_by_id:
                modules_by_id[fp.module_id]["feature_points"].append(fps_by_id[fp.id])

    # Roots are modules with no parent, already ordered
    roots = children_by_parent.get(None, [])
    return roots


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
        parent = db.get(Module, data["parent_id"])
        if parent is None or parent.project_id != module.project_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid parent_id")
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
