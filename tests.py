from app import app, get_llm_response, update_conversation_summary

@app.local_entrypoint()
def test_llm():
    response = get_llm_response.remote(
        message={
            "content": "Analyze the major themes in George Orwell's 1984 and their relevance to modern society.",
            "metadata": {
                "from": {"first_name": "John", "last_name": "Doe"},
                "chat": {"type": "group"},
            }
        },
    )
    print(response)


@app.local_entrypoint()
def test_update_conversation_summary():
    response = update_conversation_summary.remote(
        current_summary="John Doe is a nice guy.",
        user_message={
            "content": "Analyze the major themes in George Orwell's 1984 and their relevance to modern society.",
            "metadata": {
                "from": {"first_name": "John", "last_name": "Doe"},
                "chat": {"type": "group"},
            }
        },
        assistant_messages=[],
    )
    print(response)