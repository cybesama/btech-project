from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.db.models import EmergencyContact
from backend.services.twilio_service import send_sos_sms

router = APIRouter(prefix="/emergency", tags=["emergency"])


class SOSRequest(BaseModel):
    lat: float
    lng: float


class ContactIn(BaseModel):
    name: str
    phone: str
    relationship: str = ""


@router.post("/sos")
async def send_sos(req: SOSRequest, db: Session = Depends(get_db)):
    contacts = db.query(EmergencyContact).all()
    if not contacts:
        raise HTTPException(
            status_code=400,
            detail="No emergency contacts saved. Add contacts first.",
        )
    contact_dicts = [{"name": c.name, "phone": c.phone} for c in contacts]
    results = send_sos_sms(contact_dicts, req.lat, req.lng)
    return {"message": "SOS dispatched", "outcomes": results}


@router.get("/contacts")
async def list_contacts(db: Session = Depends(get_db)):
    contacts = db.query(EmergencyContact).all()
    return [
        {"id": c.id, "name": c.name, "phone": c.phone, "relationship": c.relationship}
        for c in contacts
    ]


@router.post("/contacts")
async def add_contact(req: ContactIn, db: Session = Depends(get_db)):
    contact = EmergencyContact(**req.dict())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return {"id": contact.id, "message": f"Contact '{req.name}' added"}


@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    contact = db.query(EmergencyContact).filter(EmergencyContact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(contact)
    db.commit()
    return {"message": "Contact deleted"}
