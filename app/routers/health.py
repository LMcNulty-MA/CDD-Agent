from fastapi import APIRouter
from app.core.models import HealthResponse

router = APIRouter()
router.tags = ['Health monitoring']

@router.get(
    path='/ping',
    summary='Health monitoring',
    description='Checks if the service is alive and returns version',
    response_model=HealthResponse,
    responses={200: {
        'content': {
            'application/json': {
                'example': {
                    'status': 'OK',
                    'version': '1.0.0'
                }
            }
        }
    }}
)
async def ping():
    try:
        with open("ver.txt", "r") as f:
            version = f.read().strip()
        return HealthResponse(status="OK", version=version)
    except FileNotFoundError:
        return HealthResponse(status="OK", version="unknown") 