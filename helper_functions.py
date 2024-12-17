import json
from json import JSONDecodeError


def convert_params(param: str) -> str:
    """
    A check to convert params that contain list of dict as string to a list of dict.
    """
    try:
        return json.loads(param)
    except (JSONDecodeError, TypeError):
        return param


def split_param(param: str) -> list | str:
    if "," not in param:
        return param
    return param.split(",")
