# host_app/app/services/fallback_llm.py
from typing import List, Dict
from langchain_openai import ChatOpenAI
from host_app.app import config

async def get_fallback_response(history: List[Dict]) -> str:
    """
    Generates a standard, non-monetized response using the app's own LLM.
    The 'history' provided to this function includes the system prompt from the UI.
    """
    print("---FALLBACK: Generating response using host app's LLM...---")
    
    try:
        # Initialize the language model
        llm = ChatOpenAI(
            model="gpt-4o", 
            temperature=0.7, 
            api_key=config.OPENAI_API_KEY
        )
        
        # The history already contains the system prompt as the first message.
        # We just need to invoke the model with it.
        response = await llm.ainvoke(history)
        
        return response.content

    except Exception as e:
        print(f"An error occurred in get_fallback_response: {e}")
        # Return a generic error message if the LLM fails
        return "I'm sorry, I've encountered an error and can't respond right now."