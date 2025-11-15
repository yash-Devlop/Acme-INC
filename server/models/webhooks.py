# models/webhooks.py
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

WebhookBase = declarative_base()

class Webhook(WebhookBase):
    __tablename__ = "webhooks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    url = Column(String(500), nullable=False)
    event_type = Column(String(100), nullable=False)
    enabled = Column(Boolean, default=True)
    secret_key = Column(String(255), nullable=True)
    headers = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_triggered_at = Column(DateTime, nullable=True)
    last_status_code = Column(Integer, nullable=True)
    last_response_time = Column(Integer, nullable=True)