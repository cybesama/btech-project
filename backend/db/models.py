from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from datetime import datetime
from backend.db.database import Base


class SavedRoute(Base):
    __tablename__ = "saved_routes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    destination_name = Column(String, nullable=False)
    start_lat = Column(Float, nullable=False)
    start_lng = Column(Float, nullable=False)
    end_lat = Column(Float, nullable=False)
    end_lng = Column(Float, nullable=False)
    waypoints_json = Column(Text, default="[]")
    use_count = Column(Integer, default=1)
    last_used = Column(DateTime, default=datetime.utcnow)


class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    relationship = Column(String, default="")
