from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean,
    DateTime, Table, ForeignKey,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = "sqlite:///./vc_scout.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

company_topics = Table(
    "company_topics",
    Base.metadata,
    Column("company_id", Integer, ForeignKey("companies.id")),
    Column("topic_id", Integer, ForeignKey("topics.id")),
)


class Source(Base):
    __tablename__ = "sources"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    url = Column(String(500), nullable=False, unique=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_scraped_at = Column(DateTime, nullable=True)


class Topic(Base):
    __tablename__ = "topics"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    is_active = Column(Boolean, default=True)


class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    website = Column(String(500), nullable=True)
    source_url = Column(String(500), nullable=True)
    source_name = Column(String(200), nullable=True)
    page_url = Column(String(500), nullable=True)
    industry = Column(String(200), nullable=True)
    location = Column(String(200), nullable=True)
    founded_year = Column(Integer, nullable=True)
    founders = Column(Text, nullable=True)
    funding_stage = Column(String(100), nullable=True)
    seeking_amount = Column(String(100), nullable=True)
    is_raising = Column(Boolean, default=False)
    activity_type = Column(String(30), nullable=True)  # raising | recent_round | demo_day
    raising_evidence = Column(Text, nullable=True)
    is_seen = Column(Boolean, default=False)
    is_new = Column(Boolean, default=True)
    discovered_at = Column(DateTime, default=datetime.utcnow)
    topics = relationship("Topic", secondary=company_topics, backref="companies")


class ScanLog(Base):
    __tablename__ = "scan_logs"
    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    sources_scanned = Column(Integer, default=0)
    new_companies_found = Column(Integer, default=0)
    pages_crawled = Column(Integer, default=0)
    status = Column(String(50), default="running")


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
