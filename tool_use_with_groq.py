import json
from modal import App, Image, Secret
import logging
from utils.func_schema_generator import generate_schemas_for_functions
from tools.calculate import calculate


logging.basicConfig(level=logging.INFO)

app = App("groq-tool-use")

image = Image.debian_slim(python_version="3.12").run_commands(["pip install groq"])


@app.function(image=image, secrets=[Secret.from_name("groq")])
def run_conversation(user_prompt):
    from groq import Groq

    client = Groq()
    MODEL = "llama3-groq-70b-8192-tool-use-preview"
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant. Use the provided tools when needed.",
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]
    tools = generate_schemas_for_functions([calculate])
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
        tool_choice="required",  # "required" for testing, "auto" for production (default)
        max_tokens=4096,
    )

    response_message = response.choices[0].message
    logging.info(response_message)
    tool_calls = response_message.tool_calls
    if tool_calls:
        messages.append(response_message)
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_to_call = globals()[function_name]  # access function by its name
            function_args = json.loads(tool_call.function.arguments)
            function_response = function_to_call(
                expression=function_args.get("expression")
            )
            messages.append(
                {
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                }
            )
        second_response = client.chat.completions.create(model=MODEL, messages=messages)
        logging.info(second_response)
        return second_response.choices[0].message.content
    else:
        return response_message.content


@app.local_entrypoint()
def main():
    user_prompt = "What is (25 * 4 + 10000*324342342)/234324324?"
    print(run_conversation.remote(user_prompt))
