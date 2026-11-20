from fastapi import APIRouter, Depends
from ..config.database import db_session
from ..schemas.audience import AudienceInput
from ..services.auth import current_user, writer
from ..controllers.audience import AudienceController as C

router = APIRouter()


@router.get('/audience')
def overview(db=Depends(db_session), u=Depends(current_user)):
    return C.overview(db)


@router.post('/audience')
def create(data: AudienceInput, db=Depends(db_session), u=Depends(writer)):
    return C.create(db, u, data)


@router.get('/audience/{id}')
def detail(id: int, db=Depends(db_session), u=Depends(current_user)):
    return C.get(db, id)
