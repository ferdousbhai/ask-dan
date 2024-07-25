from modal import Dict

conversation_dict = Dict.from_name("dan-conversation-state", create_if_missing=True)


print(conversation_dict[284568525])
