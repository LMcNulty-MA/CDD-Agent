from fastapi import APIRouter
from app.core.models import HealthResponse
import os

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
                    'version': open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "ver.txt")).read().strip() if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "ver.txt")) else "unknown"
                }
            }
        }
    }}
)
async def ping():
    # Read version from the root ver.txt file
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ver_path = os.path.join(root_dir, "ver.txt")
    try:
        with open(ver_path, "r") as f:
            version = f.read().strip()
        return HealthResponse(status="OK", version=version)
    except FileNotFoundError:
        return HealthResponse(status="OK", version="unknown") 