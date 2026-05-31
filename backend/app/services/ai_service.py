import json
import re
from typing import List
from ..models import LLMProviderConfig

def extract_json_from_text(text: str) -> dict | list:
    """Helper to extract JSON block from markdown formatted string."""
    # Attempt to find json block
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        json_str = text
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        # Fallback to finding first array or object if strict parsing fails
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                pass
        raise ValueError(f"Failed to parse JSON from AI response: {e}")

def generate_steps_from_text(text_content: str, provider_config: LLMProviderConfig) -> List[dict]:
    """
    Given unstructured text (e.g. from an uploaded file or raw playwright code),
    use the configured LLM to convert it into a structured list of test steps.
    """
    if not provider_config or not provider_config.is_active:
        raise ValueError("No active LLM provider configuration found.")
        
    prompt = """
You are an expert QA Automation Architect. Your task is to extract test steps from the provided input text and output a JSON object.
The output must be a valid JSON object containing a single key "steps", which is an array of objects, where each object matches the following schema:
{
  "action": "fill | click | select | searchLov | waitFor | assertText | navigate | screenshot",
  "business_description": "Business intent of the action",
  "target_name": "Name of the UI element (e.g., Location Name)",
  "locator_strategy": "label | role | text | css | xpath | aiSuggested",
  "locator_value": "The value for the locator",
  "variable_name": "Name of variable without braces, e.g. LocationName (optional)",
  "current_value": "The specific value to type/select (optional)",
  "is_sensitive": false,
  "expected_result": "What should happen after this step",
  "on_failure": "stop | continue"
}

Ensure that the output is strictly valid JSON without any additional text.

Input Text:
""" + text_content

    api_key = provider_config.api_key_secret
    provider = provider_config.provider_name.lower()
    
    if provider == "openai":
        try:
            import openai
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"} # We might need to wrap prompt to require `{ "steps": [...] }` if we use json_object, or just rely on raw output. Let's rely on standard parsing.
            )
            content = response.choices[0].message.content
        except ImportError:
            raise ImportError("openai module not installed.")
            
    elif provider == "anthropic":
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.content[0].text
        except ImportError:
            raise ImportError("anthropic module not installed.")
            
    elif provider == "gemini":
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.5-pro",
                contents=prompt
            )
            content = response.text
        except ImportError:
            try:
                # Fallback to requests if SDK not available
                import requests
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={api_key}"
                headers = {'Content-Type': 'application/json'}
                data = {
                    "contents": [{"parts": [{"text": prompt}]}]
                }
                res = requests.post(url, headers=headers, json=data)
                res.raise_for_status()
                json_res = res.json()
                content = json_res['candidates'][0]['content']['parts'][0]['text']
            except Exception as e:
                raise Exception(f"Failed to use Gemini via requests: {e}")
                
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    # Process the content and extract JSON array
    try:
        parsed_json = extract_json_from_text(content)
        
        # If the LLM returned { "steps": [...] }, unwrap it
        if isinstance(parsed_json, dict):
            if "steps" in parsed_json:
                return parsed_json["steps"]
            else:
                # Search the dictionary for any list that looks like steps
                for key, val in parsed_json.items():
                    if isinstance(val, list):
                        return val
                return [parsed_json] # fallback, maybe it returned a single step object
        elif isinstance(parsed_json, list):
            return parsed_json
        else:
            raise ValueError(f"Unexpected JSON format received from LLM: {type(parsed_json)}")
    except Exception as e:
        print(f"Error parsing AI response. Raw content was:\n{content}")
        raise e
