from google.genai import types


def turn_off_safety() -> list[types.SafetySetting]:
    """Returns a list of SafetySettings with all categories set to OFF."""
    categories = {
        'HARM_CATEGORY_HARASSMENT': 'OFF',
        'HARM_CATEGORY_HATE_SPEECH': 'OFF',
        'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'OFF',
        'HARM_CATEGORY_DANGEROUS_CONTENT': 'OFF',
        'HARM_CATEGORY_CIVIC_INTEGRITY': 'BLOCK_NONE'
    }
    return [types.SafetySetting(category=category, threshold=threshold) 
            for category, threshold in categories.items()]