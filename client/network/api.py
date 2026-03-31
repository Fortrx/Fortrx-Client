import httpx
from client.config import settings

_token: str|None = None

def set_token(token:str):
    global _token
    _token = token

def get_token():
    return _token

def _headers():
    if _token:
        return {"Authorization":f"Bearer {_token}"}
    return {}

def get(endpoint: str, **kwargs):
    url = settings.SERVER_URL + endpoint
    response = httpx.get(url,headers = _headers(),**kwargs)
    return response

def post(endpoint:str,json:dict=None,data:dict=None,**kwargs):
    url = settings.SERVER_URL + endpoint
    response = httpx.post(
        url,
        json=json,
        data=data,
        headers=_headers() | kwargs.pop("headers",{}),
        **kwargs)
    return response

def delete(endpoint:str,**kwargs):
    url = settings.SERVER_URL+endpoint
    response = httpx.delete(url,headers=_headers(),**kwargs)
    return response

def raise_for_status(response:httpx.Response,context:str=""):
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail",responnse.text)
        except Exception:
            detail = response.text
        raise FortrxAPIError(
            status_code = response.status_code,
            detail = detail,
            context=context
        )

class FortrxAPIError(Exception):
    def __init__(self,status_code:int,detail:str,context:str=""):
        self.status_code = status_code
        self.detail = detail
        self.context = context
        super().__init__(f"[{status_code}]{context}:{detail}")