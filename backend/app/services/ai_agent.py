import os
import time
import json
from playwright.sync_api import sync_playwright, Page
from typing import List, Dict, Any
from ..models import TestScript, TestStep, Environment, LLMProviderConfig
from ..database import SessionLocal
from .ai_service import generate_steps_from_text

DOM_EXTRACTION_SCRIPT = """
() => {
    const elements = document.querySelectorAll('button, a, input, select, textarea, [role="button"], [role="link"], [role="menuitem"], [role="tab"]');
    const interactive = [];
    elements.forEach(el => {
        const rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden') {
            let label = el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || el.name || el.id || '';
            label = label.toString().replace(/\n/g, ' ').trim().substring(0, 50);
            const tag = el.tagName.toLowerCase();
            const role = el.getAttribute('role') || '';
            const type = el.getAttribute('type') || '';
            interactive.push(`<${tag} id="${el.id}" name="${el.name || ''}" type="${type}" role="${role}">${label}</${tag}>`);
        }
    });
    return interactive.join('\\n');
}
"""

def extract_interactive_dom(page: Page) -> str:
    try:
        # Wait for network idle or timeout to ensure dynamic content loads
        page.wait_for_timeout(2000)
        return page.evaluate(DOM_EXTRACTION_SCRIPT)
    except Exception as e:
        return f"Error extracting DOM: {e}"

def prompt_agent_for_action(instruction, dom_context, provider_config, previous_error=None):
    prompt = f"""
You are an autonomous web agent executing a specific test instruction.
Instruction: {instruction.get('business_description')}
Target Name (if known): {instruction.get('target_name')}
Target Action: {instruction.get('action')}

Here is a simplified version of the current page DOM:
```html
{dom_context}
```

Based on the DOM, find the target element to accomplish the goal.
Respond strictly in JSON with the exact Playwright locator and action.
If the goal requires multiple steps (like opening a menu first), output the first action and set goal_status to "in_progress".

CRITICAL ORACLE RULES:
1. If the element uses `title` or `aria-label` attributes (e.g. `<a title="My Client Groups">`), you MUST use `css` strategy like `[title='My Client Groups']` or `[aria-label='My Client Groups']`. The `text` strategy WILL FAIL on attributes!
2. Only use `text` strategy if the text is literally between the HTML tags (e.g. `<span>Text</span>`).
"""
    if previous_error:
        prompt += f"""
CRITICAL WARNING: Your previous attempt failed with the following error:
{previous_error}
YOU MUST NOT use the exact same locator strategy and value again. Try a completely different locator (e.g. switch from text to css) or look for a different element.
"""

    prompt += """
Schema:
{
  "action": "click | fill | select | wait",
  "locator_strategy": "text | label | role | css | xpath",
  "locator_value": "The exact locator string",
  "input_value": "Value to type if action is fill",
  "reasoning": "Briefly explain why you chose this element",
  "goal_status": "completed | in_progress"
}}
"""
    api_key = provider_config.api_key_secret
    provider = provider_config.provider_name.lower()
    
    # We will use the raw string parsing logic similar to ai_service
    content = ""
    if provider == "openai":
        import openai
        client = openai.OpenAI(api_key=api_key)
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        content = res.choices[0].message.content
    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        res = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        content = res.content[0].text
    elif provider == "gemini":
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            res = client.models.generate_content(model="gemini-2.5-pro", contents=prompt)
            content = res.text
        except Exception:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key={api_key}"
            data = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(url, headers={'Content-Type': 'application/json'}, json=data)
            content = res.json()['candidates'][0]['content']['parts'][0]['text']
            
    # Extract JSON
    import re
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
    if match:
        content = match.group(1)
    
    start = content.find('{')
    end = content.rfind('}')
    if start != -1 and end != -1:
        return json.loads(content[start:end+1])
    return json.loads(content)


def execute_agent_action(page, action_data: dict):
    strategy = action_data.get('locator_strategy') or ''
    strategy = strategy.lower()
    val = action_data.get('locator_value') or ''
    action = action_data.get('action') or 'click'
    action = action.lower()
    
    if action == 'wait':
        page.wait_for_timeout(3000)
        return
        
    if not val:
        raise ValueError("Locator value is empty. Cannot perform action without a target.")
    
    el = None
    if strategy == 'text':
        el = page.get_by_text(val)
    elif strategy == 'label':
        el = page.get_by_label(val)
    elif strategy == 'role':
        # Default to button if role not specified in val, else just use role. 
        # (AI sometimes just gives the name)
        el = page.get_by_role('button', name=val)
    elif strategy in ['css', 'xpath']:
        el = page.locator(val)
    else:
        el = page.locator(val)
        
    # Wait for the element to be attached to the DOM before acting on it
    el.first.wait_for(state="attached", timeout=5000)
        
    # Pick first matching element if multiple
    if el.count() > 1:
        el = el.first
        
    if action == 'fill':
        # Clear first, then fill
        el.fill("")
        el.fill(action_data.get('input_value', ''))
    elif action == 'click':
        el.click()
    else:
        time.sleep(2)

def run_autonomous_recording(script_id: int, file_content: str, env_id: int, provider_config: LLMProviderConfig):
    db = SessionLocal()
    try:
        # 1. Parse the high-level intent from the file
        target_instructions = generate_steps_from_text(file_content, provider_config)
        
        env = db.query(Environment).filter(Environment.id == env_id).first()
        script = db.query(TestScript).filter(TestScript.id == script_id).first()
        if not env or not script:
            return
            
        base_url = env.base_url or ""
        if base_url:
            import urllib.parse as urlparse
            parsed = urlparse.urlparse(base_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            
        with sync_playwright() as p:
            # Run visibly so the user can watch the AI agent work
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            
            # Initial navigation and login
            if base_url:
                page.goto(base_url)
                
                # Auto-login if default credentials exist
                if env.default_username and env.default_password:
                    # Oracle Fusion can take a long time to redirect to IDCS login
                    try:
                        # Wait for either the username field (if not logged in) or the dashboard (if already logged in)
                        page.wait_for_selector("input[type='text'], input[name*='sername'], input[name*='serid'], input[id*='ser'], [aria-label*='Username']", timeout=15000)
                    except Exception:
                        pass # Might already be on the dashboard
                        
                        # Wait until at least one visible input appears on the screen
                        try:
                            page.wait_for_selector("input:visible", timeout=15000)
                        except Exception:
                            pass # Timeout, but we'll try anyway
                            
                        # Try multiple common username selectors for Oracle, forcing visibility
                        username_selectors = [
                            "input[name*='user' i]:visible",
                            "input[id*='user' i]:visible",
                            "input[name*='id' i]:visible",
                            "input[aria-label*='User' i]:visible",
                            "input[type='email']:visible",
                            "input[type='text']:visible",
                            "input:not([type='password']):not([type='hidden']):visible"
                        ]
                        
                        username_filled = False
                        for sel in username_selectors:
                            try:
                                loc = page.locator(sel).first
                                if loc.is_visible(timeout=500):
                                    loc.click()
                                    page.wait_for_timeout(200)
                                    loc.press_sequentially(env.default_username, delay=50)
                                    page.wait_for_timeout(200)
                                    username_filled = True
                                    break
                            except Exception:
                                pass
                                
                        if username_filled:
                            # Only click 'Next' if the password field is NOT already visible (multi-step login)
                            password_locator = page.locator("input[type='password']:visible").first
                            if not password_locator.is_visible(timeout=1000):
                                next_button = page.locator("button:has-text('Next'):visible, button[id*='next' i]:visible").first
                                if next_button.is_visible(timeout=1000):
                                    next_button.click()
                                    page.wait_for_timeout(2000)
                                    
                        password_locator = page.locator("input[type='password']:visible").first
                        if password_locator.is_visible(timeout=5000):
                            # Click first to focus, then type sequentially to ensure any anti-bot or JS framework registers it
                            password_locator.click()
                            page.wait_for_timeout(200)
                            password_locator.press_sequentially(env.default_password, delay=50)
                            page.wait_for_timeout(500)
                            
                        # Look for Sign In or Login buttons
                        login_button = page.locator("button:has-text('Sign In'):visible, button:has-text('Login'):visible, input[type='submit']:visible").first
                        if login_button.is_visible(timeout=2000):
                            login_button.click()
                        
                        # Wait for dashboard to load after login
                        try:
                            # Oracle Fusion is very heavy, wait up to 25 seconds for network to settle
                            page.wait_for_load_state('networkidle', timeout=25000)
                        except Exception:
                            page.wait_for_timeout(10000) # fallback
                    except Exception as e:
                        print(f"Agent Auto-login attempt failed (might already be logged in): {e}")

            # For each target instruction, prompt the agent and execute
            step_num = len(script.steps) + 1
            raw_python_code = ""
            
            for instruction in target_instructions:
                # We skip login steps in the file since we already logged in
                biz_desc = instruction.get('business_description', '').lower()
                if 'login' in biz_desc or 'username' in biz_desc or 'password' in biz_desc:
                    continue
                    
                goal_completed = False
                steps_for_instruction = 0
                
                while not goal_completed and steps_for_instruction < 5:
                    steps_for_instruction += 1
                    attempts = 0
                    success = False
                    previous_error = None
                    
                    while attempts < 3 and not success:
                        attempts += 1
                        try:
                            dom = extract_interactive_dom(page)
                            action_data = prompt_agent_for_action(instruction, dom, provider_config, previous_error)
                            
                            execute_agent_action(page, action_data)
                            
                            # Determine if this instruction is fully complete
                            if action_data.get('goal_status', 'completed').lower() == 'completed':
                                goal_completed = True
                                
                            # Save step to DB if it wasn't a wait
                            if action_data.get('action') != 'wait':
                                new_step = TestStep(
                                    script_id=script.id,
                                    step_number=step_num,
                                    action=action_data.get('action', instruction.get('action', 'click')),
                                    business_description=instruction.get('business_description', action_data.get('reasoning')),
                                    target_name=instruction.get('target_name', action_data.get('locator_value')),
                                    locator_strategy=action_data.get('locator_strategy'),
                                    locator_value=action_data.get('locator_value'),
                                    variable_name=instruction.get('variable_name', ''),
                                    current_value=instruction.get('current_value', ''),
                                    expected_result=instruction.get('expected_result', 'Success')
                                )
                                db.add(new_step)
                                db.commit()
                                
                                # Append raw python code
                                if action_data.get('action') == 'fill':
                                    raw_python_code += f"page.locator('{action_data.get('locator_value')}').fill('{instruction.get('current_value', '')}')\n"
                                else:
                                    raw_python_code += f"page.locator('{action_data.get('locator_value')}').click()\n"
                                    
                                step_num += 1
                            
                            success = True
                        except Exception as e:
                            print(f"Agent step attempt {attempts} failed: {e}")
                            previous_error = str(e)
                            page.wait_for_timeout(2000)
                            
                    if not success:
                        print(f"Failed all 3 attempts for this sub-step. Aborting instruction: {instruction.get('business_description')}")
                        if instruction.get('on_failure', 'stop').lower() == 'stop':
                            print("Step marked as stop on failure. Aborting entire script execution.")
                            return
                        break # Give up on this instruction but continue to next
            
            # Update raw code
            if script.raw_code:
                script.raw_code += "\n" + raw_python_code
            else:
                script.raw_code = raw_python_code
            db.commit()
            
            browser.close()
    except Exception as e:
        print(f"Autonomous agent failed: {e}")
    finally:
        db.close()
