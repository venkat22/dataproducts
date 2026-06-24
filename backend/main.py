import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

import models
from ai_assist import generate_contract, generate_fields
from config import settings
from database import get_db, init_db
from schemas import (
    CLASSIFICATIONS,
    CONTRACT_STATUSES,
    FIELD_TYPES,
    FORMATS,
    FREQUENCIES,
    RULE_TYPES,
    AssistContractResponse,
    AssistRequest,
    AssistResponse,
    DataContractOut,
    DataContractUpsert,
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
        "field_types": FIELD_TYPES,
        "rule_types": RULE_TYPES,
        "contract_statuses": CONTRACT_STATUSES,
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


# --- Data contracts ----------------------------------------------------------
def _require_product(product_id: int, db: Session) -> models.DataProduct:
    product = db.get(models.DataProduct, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Data product not found")
    return product


@app.get("/api/data-products/{product_id}/contract", response_model=DataContractOut)
def get_contract(product_id: int, db: Session = Depends(get_db)):
    product = _require_product(product_id, db)
    if not product.contract:
        raise HTTPException(status_code=404, detail="No contract for this data product")
    return product.contract


@app.put("/api/data-products/{product_id}/contract", response_model=DataContractOut)
def upsert_contract(
    product_id: int, payload: DataContractUpsert, db: Session = Depends(get_db)
):
    product = _require_product(product_id, db)
    data = payload.model_dump()
    contract = product.contract
    if contract is None:
        contract = models.DataContract(product_id=product.id)
        db.add(contract)
    for key, value in data.items():
        setattr(contract, key, value)
    db.commit()
    db.refresh(contract)
    return contract


@app.delete("/api/data-products/{product_id}/contract", status_code=204)
def delete_contract(product_id: int, db: Session = Depends(get_db)):
    product = _require_product(product_id, db)
    if not product.contract:
        raise HTTPException(status_code=404, detail="No contract for this data product")
    db.delete(product.contract)
    db.commit()
    return None


@app.post("/api/assist/contract", response_model=AssistContractResponse)
def assist_contract(req: AssistRequest):
    contract, source, note = generate_contract(req.prompt)
    return AssistContractResponse(contract=contract, source=source, note=note)


# --- Static frontend ---------------------------------------------------------
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
