from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import Case, FeaturePoint, Module, Step, User
from app.permissions import ensure_project_access
from app.schemas import CaseCreate, CaseOut, CaseUpdate, FeaturePointCreate, FeaturePointOut

router = APIRouter(prefix="/api", tags=["cases"], dependencies=[Depends(get_current_user)])


def _case_or_404(db: Session, case_id: int) -> Case:
    case = db.get(Case, case_id, options=[selectinload(Case.steps)])
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "case not found")
    return case


def _replace_steps(db: Session, case: Case, steps: list) -> None:
    case.steps.clear()
    for index, step_in in enumerate(steps, start=1):
        # Handle both Pydantic objects (from create) and dicts (from update)
        if hasattr(step_in, "model_dump"):
            step_dict = step_in.model_dump()
        else:
            step_dict = step_in
        case.steps.append(Step(step_no=index, action=step_dict["action"], expected=step_dict["expected"]))


@router.post("/modules/{module_id}/feature-points", response_model=FeaturePointOut, status_code=status.HTTP_201_CREATED)
def create_feature_point(
    module_id: int, payload: FeaturePointCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    module = db.get(Module, module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "module not found")
    ensure_project_access(db, current, module.project_id, "editor")
    fp = FeaturePoint(module_id=module_id, name=payload.name)
    db.add(fp)
    db.commit()
    db.refresh(fp)
    return fp


@router.put("/feature-points/{fp_id}", response_model=FeaturePointOut)
def update_feature_point(
    fp_id: int, payload: FeaturePointCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    fp = db.get(FeaturePoint, fp_id)
    if fp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "feature point not found")
    ensure_project_access(db, current, fp.module.project_id, "editor")
    fp.name = payload.name
    db.commit()
    db.refresh(fp)
    return fp


@router.delete("/feature-points/{fp_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feature_point(fp_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    fp = db.get(FeaturePoint, fp_id)
    if fp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "feature point not found")
    ensure_project_access(db, current, fp.module.project_id, "editor")
    db.delete(fp)
    db.commit()


@router.post("/feature-points/{fp_id}/cases", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    fp_id: int, payload: CaseCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    fp = db.get(FeaturePoint, fp_id)
    if fp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "feature point not found")
    ensure_project_access(db, current, fp.module.project_id, "editor")
    case = Case(
        feature_point_id=fp_id,
        title=payload.title,
        priority=payload.priority,
        precondition=payload.precondition,
        remark=payload.remark,
    )
    db.add(case)
    db.flush()
    _replace_steps(db, case, payload.steps)
    db.commit()
    db.refresh(case)
    return case


@router.get("/cases/{case_id}", response_model=CaseOut)
def get_case(case_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    case = _case_or_404(db, case_id)
    ensure_project_access(db, current, case.feature_point.module.project_id, "viewer")
    return case


@router.put("/cases/{case_id}", response_model=CaseOut)
def update_case(
    case_id: int, payload: CaseUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    case = _case_or_404(db, case_id)
    ensure_project_access(db, current, case.feature_point.module.project_id, "editor")
    data = payload.model_dump(exclude_unset=True)
    steps = data.pop("steps", None)
    for field, value in data.items():
        setattr(case, field, value)
    if steps is not None:
        _replace_steps(db, case, steps)
    db.commit()
    db.refresh(case)
    return case


class ExecutionPatch(BaseModel):
    executed_pass: bool | None


@router.patch("/cases/{case_id}/execution", response_model=CaseOut)
def toggle_execution(
    case_id: int, payload: ExecutionPatch, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    case = _case_or_404(db, case_id)
    ensure_project_access(db, current, case.feature_point.module.project_id, "editor")
    case.executed_pass = payload.executed_pass
    db.commit()
    db.refresh(case)
    return case


@router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(case_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    case = _case_or_404(db, case_id)
    ensure_project_access(db, current, case.feature_point.module.project_id, "editor")
    db.delete(case)
    db.commit()
