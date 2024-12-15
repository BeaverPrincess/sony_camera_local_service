import json
from json import JSONDecodeError

def convert_params(params: list[str])->list:
  """
  A check to convert params that contain list of dict as string to a list of dict. 
  """
  try:
      converted_list = [json.loads(item) for item in params]
      if all(isinstance(obj, dict) for obj in converted_list):
          return converted_list
      else:
          return params
  except (JSONDecodeError, TypeError):
      return params