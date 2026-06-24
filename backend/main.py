import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

import models
from ai_assist import generate_fields
from config import settings
from database import get_db, init_db
from schemas import (
    CLASSIFICATIONS,
    FORMATS,
    FREQUENCIES,
    AssistRequest,
    AssistResponse,
    DataProductCreate,
    DataProductOut,
    DataProductUpdate,
)

app = FastAPI(title="Data Products Registration Portal", version="1.0.0")

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_enabled": bool(settings.anthropic_api_key)}


@app.get("/api/options")
def options():
    return {
        "classifications": CLASSIFICATIONS,
        "frequencies": FREQUENCIES,
        "formats": FORMATS,
    }


@app.get("/api/data-products", response_model=list[DataProductOut])
def list_products(db: Session = Depends(get_db)):
    return db.query(models.DataProduct).order_by(models.DataProduct.id.desc()).all()


@app.get("/api/data-products/{product_id}", response_model=DataProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(models.DataProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Data product not found")
    return product


@app.post("/api/data-products", response_model=DataProductOut, status_code=201)
def create_product(payload: DataProductCreate, db: Session = Depends(get_db)):
    product = models.DataProduct(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@app.put("/api/data-products/{product_id}", response_model=DataProductOut)
def update_product(
    product_id: int, payload: DataProductUpdate, db: Session = Depends(get_db)
):
    product = db.get(models.DataProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Data product not found")
    for key, value in payload.model_dump().items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return product


@app.delete("/api/data-products/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(models.DataProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Data product not found")
    db.delete(product)
    db.commit()
    return None


@app.post("/api/assist", response_model=AssistResponse)
def assist(req: AssistRequest):
    fields, source, note = generate_fields(req.prompt)
    return AssistResponse(fields=fields, source=source, note=note)


# --- Static frontend ---------------------------------------------------------
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
