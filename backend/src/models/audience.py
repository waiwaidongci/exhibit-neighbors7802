from sqlalchemy import Column, Integer, String, JSON
from ..config.database import Base


class AudienceProfile(Base):
    """客群构成版本：分组、边际占比、不可能组合与访客分组映射。

    每次更新整体插入新版本，历史版本不可变；
    对照任务在受理时锁定当时的版本号与快照。
    """
    __tablename__ = 'audience_profiles'
    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False)
    payload = Column(JSON, nullable=False)
    created_by = Column(String(120), nullable=False)
    created_at = Column(String(40), nullable=False)
