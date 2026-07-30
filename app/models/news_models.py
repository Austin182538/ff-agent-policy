"""
Fantasy news stub. Deliberately minimal for now (per project scope) -- just a
table and a no-op-friendly fetch function in app/integrations/news_client.py.
Not wired into a scheduled job yet.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, UniqueConstraint
from app.core.database import Base
from datetime import datetime


class NewsItem(Base):
    __tablename__ = "news_items"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, default="FantasyPros")
    external_id = Column(String, index=True, nullable=True)  # source's own item id
    player_name = Column(String, index=True, nullable=True)
    team_abbr = Column(String(4), index=True, nullable=True)
    category = Column(String, index=True, nullable=True)  # injury/recap/transaction/rumor/breaking
    title = Column(String, nullable=False)
    url = Column(String, nullable=True)
    raw_text = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_news_item_source_external_id"),
    )
