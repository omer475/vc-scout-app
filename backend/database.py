import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean,
    DateTime, Table, ForeignKey,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./vc_scout.db")
# Strip any whitespace/newlines that sneak in when pasting wrapped URLs
DATABASE_URL = "".join(DATABASE_URL.split())
# Some providers still hand out the legacy postgres:// scheme
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

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


class FirmDoc(Base):
    """A piece of the firm's own knowledge: a thesis doc, a past memo,
    a pass reason, a portfolio list. This is what new decks get judged against."""
    __tablename__ = "firm_docs"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(300), nullable=False)
    doc_type = Column(String(40), default="other")  # thesis | memo | pass_reason | portfolio | other
    content = Column(Text, nullable=False)
    source_filename = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class FitMemo(Base):
    """The output: an AI-written assessment of one pitch deck against the firm's knowledge."""
    __tablename__ = "fit_memos"
    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String(300), nullable=True)
    one_liner = Column(Text, nullable=True)
    verdict = Column(String(40), nullable=True)  # strong_fit | possible_fit | weak_fit | pass
    fit_score = Column(Integer, nullable=True)   # 0-100
    memo_markdown = Column(Text, nullable=True)
    deck_filename = Column(String(300), nullable=True)
    deck_excerpt = Column(Text, nullable=True)
    docs_used = Column(Integer, default=0)
    model = Column(String(80), nullable=True)
    status = Column(String(40), default="completed")  # completed | failed
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
