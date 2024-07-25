import inspect
from typing import Callable, get_type_hints
import logging

logging.basicConfig(level=logging.INFO)


def generate_openai_function_schema(func: Callable):
    func_name = func.__name__
    func_doc = inspect.getdoc(func)
    func_params = inspect.signature(func).parameters
    type_hints = get_type_hints(func)

    schema = {
        "type": "function",
        "function": {
            "name": func_name,
            "description": func_doc,
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }

    for param_name, param in func_params.items():
        param_type = type_hints.get(param_name, str).__name__
        schema["function"]["parameters"]["properties"][param_name] = {
            "type": param_type,
            "description": f"The {param_name} to evaluate",
        }
        schema["function"]["parameters"]["required"].append(param_name)

    return schema


def generate_schemas_for_functions(functions: list[Callable]) -> list[dict]:
    schemas = [generate_openai_function_schema(func) for func in functions]
    return schemas


if __name__ == "__main__":
    from tools.calculate import calculate

    print(generate_schemas_for_functions([calculate]))
