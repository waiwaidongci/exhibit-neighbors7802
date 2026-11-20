from fastapi import APIRouter, Depends
from ..config.database import db_session
from ..schemas.compare import ComparisonInput
from ..services.auth import current_user, writer
from ..controllers.compare import CompareController as C

router = APIRouter()


@router.get('/comparisons')
def comparisons(db=Depends(db_session), u=Depends(current_user)):
    return C.list(db)


@router.post('/comparisons')
def create(data: ComparisonInput, db=Depends(db_session), u=Depends(writer)):
    return C.create(db, u, data)


@router.get('/comparisons/{id}')
def detail(id: int, db=Depends(db_session), u=Depends(current_user)):
    return C.get(db, id)
