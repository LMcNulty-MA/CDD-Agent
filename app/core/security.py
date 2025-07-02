import base64
import json
import logging
import struct
from typing import Any, Optional
from urllib.parse import urljoin
import jwt
import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from fastapi.exceptions import HTTPException
from fastapi.requests import Request
from fastapi.security import HTTPBearer
from jwt.exceptions import InvalidSignatureError

# In house imports
from app.config import settings
from .models import Entitlement, PermissionsData, TokenData

log = logging.getLogger(__name__)


def jwt_token_data(request: Request) -> Optional[TokenData]:
    """
    Retrieves the raw JWT token and its decoded payload from the request's state.

    :param request: The current HTTP request
    :return: The JWT token attached to the request and its decoded payload
    """
    return request.state.jwt

def permissions_data(request: Request) -> Optional[PermissionsData]:
    """
    Retrieves the permission data from the request's state.

    :param request: The current HTTP request
    :return: The Permission data
    """
    return request.state.permissions

class _PublicKeys:
    """ Class responsible for retrieving and holding the list of trusted public keys of the Single Sign-On API. """
    _public_keys: Optional[dict[Any, bytes]]

    def __init__(self):
        self._public_keys = None

    def __call__(self) -> dict[Any, bytes]:
        """ :returns: The list of trusted public keys of the Single Sign-on API """
        if not self._public_keys:
            self._public_keys = self._get_public_keys()

        return self._public_keys

    def _get_public_keys(self):
        """ :returns: The list of trusted public keys of the Single Sign-on API """
        response = requests.get(urljoin(settings.GLOBAL_SSO_SERVICE_URL, 'sso-api/auth/certs'))
        response.raise_for_status()

        jwks = json.loads(response.content.decode(response.encoding))

        return dict([(jwk['kid'], self._get_authentication_public_key(jwk)) for jwk in jwks['keys']])

    def _get_authentication_public_key(self, authentication_public_license):
        modulus = self._base64_to_long(authentication_public_license['n'])
        exponent = self._base64_to_long(authentication_public_license['e'])

        public_key = RSAPublicNumbers(exponent, modulus).public_key(default_backend())

        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

    @staticmethod
    def _base64_to_long(data):
        if isinstance(data, str):
            data = data.encode('ascii')

        _d = base64.urlsafe_b64decode(bytes(data) + b'==')
        _arr = struct.unpack('%sB' % len(_d), _d)

        return int(''.join(['%02x' % byte for byte in _arr]), 16)


class JWTBearer(HTTPBearer):
    """
    An implementation of :class:`HTTPBearer` which provides a JWT token signature validation and store the decoded
    payload at current request scope.
    """
    _public_keys = _PublicKeys()
    _options = {
        'verify_signature': True,
        'verify_exp': True,
        'verify_nbf': True,
        'verify_iat': True,
        'verify_aud': False,
        'require_exp': True,
        'require_iat': True,
        'require_nbf': False
    }

    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)

    async def __call__(self, request: Request) -> Optional[TokenData]:
        """
        Validates the caller's identity and authorizations then return the decoded token.
        The token is also stored in the request state for potential further usage within the routers.

        An :class:`HTTPException` with a 403 error code is thrown if any of the following condition is met :
          - No authorization is provided by the client
          - The authorization type is not 'Bearer Token'
          - The token has expired or is invalid

        :param request: The current HTTP request
        :return: The raw JWT token and its decoded payload
        :raises: An HTTPException with a 403 error code if no authentication header is provided
        """
        authorization_scheme_param = await super().__call__(request)

        token_data = TokenData(
            token=authorization_scheme_param.credentials, payload=self._decode(authorization_scheme_param.credentials)
        )

        request.state.jwt = token_data
        return token_data

    def _decode(self, token) -> dict[str, Any]:
        """
        Decodes the provided JWT token using any of the trusted public keys and returns the decoded payload.

        An :class:`HTTPException` with a 401 error code is thrown if none of the trusted public keys successfully allow
        to validate and parse the token's signature.

        :param token: The token to be decoded
        :return: The decoded token's payload
        """
        for k, jwk in self._public_keys().items():
            try:
                return jwt.decode(token, key=jwk, options=self._options, algorithms='RS256')
            except InvalidSignatureError:
                log.info('JWK %s cannot be used for token: %s', k, token)
            except Exception as err:
                log.info('Error "%s" when parsing token %s', err, token)

        raise HTTPException(
            status_code=401, detail='Invalid authorization token', headers={'WWW-Authenticate': 'Bearer'}
        )

class Permissions:

    def __init__(self, entitlements: set[str] = None, roles: set[str] = None) -> None:
        self._entitlements = entitlements
        self._roles = roles

    def __call__(self, request: Request) -> Optional[PermissionsData]:
        """
        Validates the caller permissions

        :param request: The current HTTP request
        :return: The different types of permissions
        :raises: An HTTPException with a 403 error code if permissions are not satisfied
        """
        token_data = jwt_token_data(request)
        self._get_entitlements_and_roles(token_data.token)
        
        if self._entitlements:
            self._check_entitlements()

        if self._roles:
            self._check_roles()

        permissions_data = PermissionsData(entitlements=self._user_entitlements, roles=self._user_roles)

        request.state.permissions = permissions_data
        return permissions_data

    def _get_entitlements_and_roles(self, token: str) -> None:
        url = urljoin(settings.GLOBAL_SSO_SERVICE_URL, 'entitlement/v2/userinfo')
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        response = requests.get(url=url, headers=headers)
        response.raise_for_status()

        self._user_roles = response.json().get("roles", [])
        entitlements = response.json().get("entitlements", [])
        self._user_entitlements = [Entitlement(**entitlement) for entitlement in entitlements]

    def _check_entitlements(self):
        entitlements_cache = {entitlement.name: entitlement for entitlement in self._user_entitlements}
        common_entitlements = set(entitlements_cache.keys()).intersection(self._entitlements)
        if not common_entitlements:
            raise HTTPException(
                status_code=403, detail="Invalid application entitlements", headers={'WWW-Authenticate': 'Bearer'}
            )

    def _check_roles(self):
        common_roles = set(self._user_roles).intersection(self._roles)
        if not common_roles:
            raise HTTPException(status_code=403, detail="Invalid user roles", headers={'WWW-Authenticate': 'Bearer'})


oauth2_scheme = JWTBearer()
""" See :class:`JWTBearer`. """

permissions_cdd = Permissions(entitlements={"CDD-AI-Agent"})
""" CDD AI Agent permissions """ 