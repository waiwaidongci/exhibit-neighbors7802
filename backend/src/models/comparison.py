from sqlalchemy import Column, Integer, String, JSON, ForeignKey
from ..config.database import Base
from ..config.settings import CONFIG


class Comparison(Base):
    """两份已完成研究的准确度对照结论。

    profile_version / profile_snapshot 为受理时锁定的同版客群数据，
    后续客群数据并发更新不影响已受理对照的口径与结论。
    """
    __tablename__ = 'comparisons'
    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False)
    run_a_id = Column(Integer, ForeignKey(CONFIG['run_table'] + '.id'), nullable=False)
    run_b_id = Column(Integer, ForeignKey(CONFIG['run_table'] + '.id'), nullable=False)
    profile_version = Column(Integer, nullable=False)
    profile_snapshot = Column(JSON, nullable=False)
    result = Column(JSON, nullable=False)
    verdict = Column(String(20), nullable=False)
    created_by = Column(String(120), nullable=False)
    created_at = Column(String(40), nullable=False)
