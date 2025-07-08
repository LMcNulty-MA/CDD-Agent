import logging
from fastapi import HTTPException, status, Request
from app.core.security import oauth2_scheme

logger = logging.getLogger(__name__)

async def auth_dependency(request: Request):
    """
    Custom authentication dependency that handles expired tokens gracefully
    
    Returns the token data if authentication is successful, otherwise raises
    an HTTPException with a user-friendly error message.
    """
    try:
        return await oauth2_scheme(request)
    except HTTPException as e:
        # Re-raise with more user-friendly error message for expired tokens
        if "expired" in str(e.detail).lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Your authentication token has expired. Please log in again to continue.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        elif e.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed. Please check your credentials and try again.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        else:
            # Re-raise other HTTP exceptions as-is
            raise
    except Exception as e:
        # Handle any other authentication errors
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication service temporarily unavailable. Please try again later.",
            headers={"WWW-Authenticate": "Bearer"}
        )

def get_token_from_auth_dependency(auth_data) -> str:
    """
    Extract the token string from the authentication dependency result
    
    Args:
        auth_data: The result from auth_dependency (TokenData object)
        
    Returns:
        str: The token string
    """
    if hasattr(auth_data, 'token'):
        return auth_data.token
    return str(auth_data)

async def token_dependency(request: Request) -> str:
    """
    Custom authentication dependency that returns the token string directly
    and handles expired tokens gracefully
    
    This is useful for endpoints that need the token string directly rather
    than the full TokenData object.
    """
    try:
        token_data = await oauth2_scheme(request)
        # Extract the token string from the TokenData object
        if token_data and hasattr(token_data, 'token'):
            return token_data.token
        return str(token_data) if token_data else ""
    except HTTPException as e:
        # Re-raise with more user-friendly error message for expired tokens
        if "expired" in str(e.detail).lower():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Your authentication token has expired. Please log in again to continue.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        elif e.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed. Please check your credentials and try again.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        else:
            # Re-raise other HTTP exceptions as-is
            raise
    except Exception as e:
        # Handle any other authentication errors
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication service temporarily unavailable. Please try again later.",
            headers={"WWW-Authenticate": "Bearer"}
        ) 