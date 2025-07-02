import logging
import requests
from time import sleep

logger = logging.getLogger(__name__)


class SSOHandler:
    def __init__(self, sso_url):
        self.sso_url = sso_url.strip().rstrip('/')
    
    def get_sso_token(self, sso_id, sso_secret):
        token = ""
        retry_count = 0
        parameters = {
            "username": "",
            "password": "",
            "grant_type": "client_credentials",
            "scope": "openid",
            "client_id": sso_id,
            "client_secret": sso_secret,
            "redirect_uri": "",
            "code": ""
        }

        url = f"{self.sso_url}/sso-api/v1/token"
        while not token and retry_count < 3:
            try:
                retry_count += 1
                response = requests.post(url, data=parameters)
                response.raise_for_status()
                token = response.json()['id_token']
            except requests.exceptions.RequestException as e:
                if response:
                    logger.warning(f"Failed to generate an SSO Token - Attempt {retry_count}. "
                                f"Status Code: {response.status_code}, Response: {response.text}, "
                                f"Headers: {response.headers}. Exception: {e}")
                else:
                    logger.warning(f"Request failed with no response. Exception: {e}")
        if not token:
            raise Exception("Unable to generate an SSO token.")
        return token

    def get_one_time_token(self, ott_id, ott_secret, sso_token):
        token = ""
        retry_count = 0
        payload = {
            "clientId": ott_id,
            "clientSecret": ott_secret,
            "duration": 1
        }
        url = f"{self.sso_url}/sso-api/auth/onetimetoken"
        while not token and retry_count < 5:
            try:
                retry_count += 1
                headers = {'Authorization': f'Bearer {sso_token}'}
                response = requests.post(url, json=payload, headers=headers)
                response.raise_for_status()
                token = response.json()['id_token']
            except Exception as e:
                logger.warning(f"Failed to generate an SSO One Time Token - Attempt {retry_count}. Exception: {e}.")
                sleep(3)
        if not token:
            raise Exception("Unable to generate an SSO One Time Token")
        return token 