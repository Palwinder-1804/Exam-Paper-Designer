from fastapi import APIRouter, HTTPException

from app.core.template_engine import list_templates, load_template

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("")
def get_templates():
    return {"templates": list_templates()}


@router.get("/{template_id}")
def get_template(template_id: str):
    try:
        data = load_template(template_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")
    return data
