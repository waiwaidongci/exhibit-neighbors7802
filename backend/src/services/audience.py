import math
from fastapi import HTTPException
from sqlalchemy import select
from ..models.audience import AudienceProfile
from ..utils.serialization import row, now
from .audit import log

MAX_GROUPS = 60
MAX_VISITOR_CELLS = 100000


def _validate_group(raw, kind):
    key = str(raw.get('key', '')).strip()
    label = str(raw.get('label', '')).strip()
    if not key or len(key) > 60:
        raise ValueError(kind + '的 key 不能为空且最多60字符')
    if not label or len(label) > 120:
        raise ValueError(kind + ' ' + key + ' 的名称不能为空且最多120字符')
    share = raw.get('share')
    if isinstance(share, bool):
        raise ValueError(kind + ' ' + key + ' 的占比必须为数值')
    try:
        share = float(share)
    except (TypeError, ValueError):
        raise ValueError(kind + ' ' + key + ' 的占比必须为数值')
    if not math.isfinite(share) or share < 0:
        raise ValueError(kind + ' ' + key + ' 的占比必须为非负有限数值')
    return {'key': key, 'label': label, 'share': share}


def validate_payload(data):
    """校验客群构成版本。占比合计是否归一、两侧是否相等不在此处拒绝，
    留待对照计算时作为可行构成冲突报告。"""
    ages, seen = [], set()
    for raw in data.age_groups:
        g = _validate_group(raw.model_dump(), '年龄段')
        if g['key'] in seen:
            raise ValueError('年龄段 key 重复：' + g['key'])
        seen.add(g['key'])
        ages.append(g)
    methods, mseen = [], set()
    for raw in data.visit_methods:
        g = _validate_group(raw.model_dump(), '来访方式')
        if g['key'] in mseen:
            raise ValueError('来访方式 key 重复：' + g['key'])
        mseen.add(g['key'])
        methods.append(g)
    if not ages or not methods:
        raise ValueError('至少一个年龄段与一个来访方式')
    if len(ages) > MAX_GROUPS or len(methods) > MAX_GROUPS:
        raise ValueError('分组数量过多（每类最多60）')
    if sum(g['share'] for g in ages) <= 0 or sum(g['share'] for g in methods) <= 0:
        raise ValueError('年龄段与来访方式的占比合计都必须大于0')
    forbidden, fseen = [], set()
    for pair in data.forbidden:
        age, method = pair.age, pair.method
        if age not in seen:
            raise ValueError('不可能组合引用了未知年龄段：' + str(age))
        if method not in mseen:
            raise ValueError('不可能组合引用了未知来访方式：' + str(method))
        if (age, method) not in fseen:
            fseen.add((age, method))
            forbidden.append({'age': age, 'method': method})
    visitor_cells = {}
    cells_in = data.visitor_cells or {}
    if len(cells_in) > MAX_VISITOR_CELLS:
        raise ValueError('访客分组映射过多（最多10万条）')
    for visitor, cell in cells_in.items():
        v = str(visitor).strip()
        if not v or len(v) > 120:
            raise ValueError('访客编号不能为空且最多120字符')
        age, method = getattr(cell, 'age', None), getattr(cell, 'method', None)
        if age not in seen or method not in mseen:
            raise ValueError('访客 ' + v + ' 的分组引用了未知年龄段或来访方式')
        visitor_cells[v] = {'age': age, 'method': method}
    return {'age_groups': ages, 'visit_methods': methods,
            'forbidden': forbidden, 'visitor_cells': visitor_cells}


def current_version(db):
    return db.scalar(select(AudienceProfile).order_by(AudienceProfile.id.desc()).limit(1))


def get_version(db, id):
    p = db.get(AudienceProfile, id)
    if not p:
        raise HTTPException(404, '未找到客群构成版本')
    return row(p)


def audience_overview(db):
    versions = [{k: v for k, v in row(p).items() if k != 'payload'}
                for p in db.scalars(select(AudienceProfile).order_by(AudienceProfile.id.desc()))]
    current = current_version(db)
    return {'current': row(current) if current else None, 'versions': versions}


def create_version(db, user, data):
    try:
        payload = validate_payload(data)
    except ValueError as e:
        raise HTTPException(422, str(e))
    p = AudienceProfile(name=data.name, payload=payload,
                        created_by=user.email, created_at=now())
    db.add(p)
    db.flush()
    log(db, user, 'audience.version_created', p.id,
        data.name + ' · 年龄段' + str(len(payload['age_groups'])) + ' · 来访方式' + str(len(payload['visit_methods'])))
    db.commit()
    return row(p)
