# import modal


# app = modal.App("llm-tools")


# @app.function()
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression"""
    import json

    try:
        result = eval(expression)
        return json.dumps({"result": result})
    except Exception as e:
        return json.dumps({"error": f"Invalid expression: {e}"})
