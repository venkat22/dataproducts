import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

import models
from ai_assist import (
    generate_contract,
    generate_fields,
    improve_description,
    suggest_sources,
    suggest_tags,
    search_interpret,
    chat_with_product,
    find_similar_products,
    clarify_inputs,
)
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
    ImproveDescriptionRequest,
    ImproveDescriptionResponse,
    SuggestRequest,
    SuggestResponse,
    SearchRequest,
    SearchAssistResponse,
    SearchFilters,
    ChatRequest,
    ChatResponse,
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    SimilarProduct,
    ClarifyRequest,
    ClarifyResponse,
)

app = FastAPI(title="Data Products Registration Portal", version="1.0.0")

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_enabled": settings.ai_enabled}


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


@app.post("/api/assist/improve-description", response_model=ImproveDescriptionResponse)
def assist_improve_description(req: ImproveDescriptionRequest):
    improved, note = improve_description(req.name, req.domain, req.description)
    return ImproveDescriptionResponse(improved=improved, note=note)


@app.post("/api/assist/suggest-sources", response_model=SuggestResponse)
def assist_suggest_sources(req: SuggestRequest):
    suggestions, note = suggest_sources(req.name, req.domain, req.description)
    return SuggestResponse(suggestions=suggestions, note=note)


@app.post("/api/assist/suggest-tags", response_model=SuggestResponse)
def assist_suggest_tags(req: SuggestRequest):
    suggestions, note = suggest_tags(req.name, req.domain, req.description, req.source_systems)
    return SuggestResponse(suggestions=suggestions, note=note)


@app.post("/api/assist/search", response_model=SearchAssistResponse)
def assist_search(req: SearchRequest, db: Session = Depends(get_db)):
    products = db.query(models.DataProduct).all()
    catalog = [{"id": p.id, "name": p.name, "domain": p.domain, "tags": p.tags,
                "classification": p.classification, "description": p.description} for p in products]
    filters, note = search_interpret(req.query, catalog)
    return SearchAssistResponse(
        filters=SearchFilters(**filters),
        note=note,
    )


@app.post("/api/assist/chat", response_model=ChatResponse)
def assist_chat(req: ChatRequest, db: Session = Depends(get_db)):
    product = db.get(models.DataProduct, req.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Data product not found")
    product_dict = {c.name: getattr(product, c.name) for c in product.__table__.columns}
    contract_dict = None
    if product.contract:
        c = product.contract
        contract_dict = {
            "schema_fields": [{"name": f.name, "type": f.type} for f in c.schema_fields] if hasattr(c, "schema_fields") else [],
            "slo_availability": c.slo_availability,
            "slo_freshness": c.slo_freshness,
        }
    reply, note = chat_with_product(product_dict, contract_dict, req.message)
    return ChatResponse(reply=reply, note=note)


@app.post("/api/assist/clarify", response_model=ClarifyResponse)
def assist_clarify(req: ClarifyRequest):
    ok, questions, improved, message = clarify_inputs(
        req.name, req.description, req.domain, req.source_systems, req.answers
    )
    return ClarifyResponse(ok=ok, questions=questions, improved=improved, message=message)


@app.post("/api/assist/check-duplicate", response_model=DuplicateCheckResponse)
def assist_check_duplicate(req: DuplicateCheckRequest, db: Session = Depends(get_db)):
    products = db.query(models.DataProduct).all()
    catalog = [{"id": p.id, "name": p.name, "domain": p.domain, "description": p.description} for p in products]
    similar, warning = find_similar_products(req.name, req.description, req.domain, req.source_systems, catalog)
    return DuplicateCheckResponse(
        similar=[SimilarProduct(**s) for s in similar],
        warning=warning,
    )


# --- Static frontend ---------------------------------------------------------
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
