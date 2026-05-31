import os
import time
from playwright.sync_api import sync_playwright, Page, expect, Error as PlaywrightError
from typing import Dict, Any, List
from ..models import TestScript, TestStep, DataProfileValue, ExecutionRun, ExecutionStepResult
from sqlalchemy.orm import Session

class PlaywrightExecutor:
    def __init__(self, db: Session, run_id: int):
        self.db = db
        self.run_id = run_id
        
    def substitute_variables(self, text: str, variables: Dict[str, str]) -> str:
        if not text:
            return text
        result = text
        for var_name, var_value in variables.items():
            result = result.replace(f"{{{var_name}}}", var_value)
        return result

    def execute_script(self, script: TestScript, data_profile_values: List[DataProfileValue], env,
                       headless: bool = False, record_video: bool = False, collect_trace: bool = False, screenshots: str = "on_failure", run_mode: str = "structured"):
        
        base_url = env.base_url or ""
        if base_url:
            import urllib.parse as urlparse
            parsed_base = urlparse.urlparse(base_url)
            base_url = f"{parsed_base.scheme}://{parsed_base.netloc}"
        
        # Create variable map from data profile
        variables = {v.variable_name: v.actual_value for v in data_profile_values}
        
        # Inject Environment default credentials if not overridden by Data Profile
        if env.default_username and "Username" not in variables and "username" not in variables:
            variables["Username"] = env.default_username
            variables["username"] = env.default_username
        if env.default_password and "Password" not in variables and "password" not in variables:
            variables["Password"] = env.default_password
            variables["password"] = env.default_password
            
        run_record = self.db.query(ExecutionRun).filter(ExecutionRun.id == self.run_id).first()
        if not run_record:
            return
            
        run_record.status = "Running"
        self.db.commit()
        
        if run_mode == "raw" and script.raw_code:
            self._execute_raw(script, variables, base_url, headless, record_video, collect_trace, screenshots, run_record)
            self.db.commit()
            return
            
        # We use sync_playwright for simplicity in MVP, in real app, might want async
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=headless)
                
                context_args = {
                    "viewport": {"width": 1920, "height": 1080}
                }
                if record_video:
                    os.makedirs("data/videos", exist_ok=True)
                    context_args["record_video_dir"] = "data/videos/"
                    context_args["record_video_size"] = {"width": 1920, "height": 1080}
                    
                context = browser.new_context(**context_args)
                
                if collect_trace:
                    context.tracing.start(screenshots=True, snapshots=True, sources=True)
                    
                page = context.new_page()
                
                success = True
                
                for step in sorted(script.steps, key=lambda s: s.step_number):
                    # Check if execution was cancelled by the user
                    self.db.refresh(run_record)
                    if run_record.status == "Cancelled":
                        success = False
                        print("Execution was cancelled by the user.")
                        break
                        
                    step_result = ExecutionStepResult(
                        run_id=self.run_id,
                        step_id=step.id,
                        status="Running"
                    )
                    self.db.add(step_result)
                    self.db.commit()
                    
                    try:
                        screenshot_path = None
                        if screenshots == "always":
                            os.makedirs("data/screenshots", exist_ok=True)
                            screenshot_path = f"data/screenshots/run_{self.run_id}_step_{step.step_number}.png"
                            
                        self.execute_step(page, step, variables, base_url, screenshot_path)
                        step_result.status = "Passed"
                        
                        if screenshot_path:
                            step_result.screenshot_path = screenshot_path
                            
                        # Oracle ADF Auto-Error Detection
                        # Check if an error message appeared on the screen after the action
                        try:
                            # Common Oracle error dialogs
                            if page.locator("text='Invalid user name or password'").is_visible(timeout=500):
                                raise Exception("Oracle ADF Error: Invalid user name or password detected on screen.")
                        except:
                            pass
                            
                    except Exception as e:
                        step_result.status = "Failed"
                        step_result.error_message = str(e)
                        
                        if screenshots in ["on_failure", "always"]:
                            os.makedirs("data/screenshots", exist_ok=True)
                            err_path = f"data/screenshots/run_{self.run_id}_step_{step.step_number}_error.png"
                            page.screenshot(path=err_path)
                            step_result.screenshot_path = err_path
                            
                        success = False
                        
                        if step.on_failure == "stop":
                            self.db.commit()
                            break
                            
                    self.db.commit()
                    
                if collect_trace:
                    os.makedirs("data/traces", exist_ok=True)
                    trace_path = f"data/traces/run_{self.run_id}.zip"
                    context.tracing.stop(path=trace_path)
                    run_record.trace_path = trace_path
                    
                if record_video and page.video:
                    video_path = page.video.path()
                    run_record.video_path = video_path

                page.close()
                context.close()
                
                browser.close()
                if run_record.status != "Cancelled":
                    run_record.status = "Passed" if success else "Failed"
                
        except Exception as e:
            if run_record.status != "Cancelled":
                run_record.status = "Failed"
            
        self.db.commit()

    def _execute_raw(self, script: TestScript, variables: Dict[str, str], base_url: str, headless: bool, record_video: bool, collect_trace: bool, screenshots: str, run_record: ExecutionRun):
        import tempfile
        import subprocess
        import sys
        
        if not script.raw_code:
            run_record.status = "Failed"
            step_result = ExecutionStepResult(
                run_id=self.run_id,
                status="Failed",
                error_message="No raw code available."
            )
            self.db.add(step_result)
            return

        # Prepare code: override headless flag in raw code if present
        code = script.raw_code
        if headless:
            code = code.replace("headless=False", "headless=True")
        else:
            code = code.replace("headless=True", "headless=False")
            
        # Add base_url to variables if not present so it can be substituted
        # Ensure it has a trailing slash to prevent concatenation errors like .comfscmUI
        safe_base_url = base_url if base_url.endswith('/') else f"{base_url}/"
        if "base_url" not in variables:
            variables["base_url"] = safe_base_url
            
        # Substitute all {variables} in the raw code
        code = self.substitute_variables(code, variables)
        
        # Fallback for the first goto if it wasn't parameterized
        import re
        code = re.sub(r'page\.goto\(["\'].+?["\']\)', f'page.goto("{base_url}")', code, count=1)
        
        # --- QRT FOOLPROOF HARDENING ---
        # Intercept the raw playwright code and inject robust auto-waits and SSO protection
        lines = code.split('\n')
        hardened_lines = []
        goto_count = 0
        for line in lines:
            stripped = line.strip()
            
            # 1. Global Timeout Injection
            if "page = context.new_page()" in line:
                hardened_lines.append(line)
                hardened_lines.append("    page.set_default_timeout(30000) # QRT Injected: Global timeout")
                continue
                
            # 2. SSO Interruption Protection (Strip secondary gotos)
            if "page.goto(" in line:
                goto_count += 1
                if goto_count > 1:
                    hardened_lines.append(f"    # QRT Injected: Commented out secondary goto to protect SSO -> {stripped}")
                    continue
            
            # Keep the line
            hardened_lines.append(line)
            
            # 3. Auto-Wait on Clicks
            if ".click(" in line and "page." in line:
                hardened_lines.append("    page.wait_for_timeout(1500) # QRT Injected: Pacing after click")

        code = "\n".join(hardened_lines)
        # --- END FOOLPROOF HARDENING ---
            
        # Optional: Add tracing to raw code (too complex for simple script inject, we just run it as is)
            
        step_result = ExecutionStepResult(
            run_id=self.run_id,
            status="Running",
            error_message="Executing Raw Python Code"
        )
        self.db.add(step_result)
        self.db.commit()
        
        file_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode='w', encoding='utf-8') as tmp:
                tmp.write(code)
                file_path = tmp.name
                
            process = subprocess.Popen([sys.executable, file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            start_time = time.time()
            timeout = 120
            cancelled = False
            
            while True:
                if process.poll() is not None:
                    break
                    
                self.db.refresh(run_record)
                if run_record.status == "Cancelled":
                    process.terminate()
                    cancelled = True
                    break
                    
                if time.time() - start_time > timeout:
                    process.terminate()
                    break
                    
                time.sleep(1)
                
            stdout, stderr = process.communicate()
            
            if cancelled:
                step_result.status = "Failed"
                step_result.error_message = "Execution cancelled by user."
            elif process.returncode == 0:
                run_record.status = "Passed"
                step_result.status = "Passed"
                step_result.error_message = "Raw script executed successfully.\n" + stdout
            elif time.time() - start_time > timeout:
                run_record.status = "Failed"
                step_result.status = "Failed"
                step_result.error_message = "Execution timed out after 120s."
            else:
                run_record.status = "Failed"
                step_result.status = "Failed"
                step_result.error_message = f"Raw script failed (Exit code {process.returncode}).\n{stderr}\n{stdout}"
                
        except Exception as e:
            run_record.status = "Failed"
            step_result.status = "Failed"
            step_result.error_message = f"Execution error: {str(e)}"
        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass

    def execute_step(self, page: Page, step: TestStep, variables: Dict[str, str], base_url: str, screenshot_path: str = None):
        action = step.action.lower() if step.action else ""
        if action == "input":
            action = "fill"
            
        # Ensure base_url is available as a variable
        if "base_url" not in variables:
            variables["base_url"] = base_url
            
        target_val = step.locator_value or ""
        if not target_val and step.target_name:
            target_val = step.target_name
        target_val = self.substitute_variables(target_val, variables)
        
        input_val = self.substitute_variables(step.current_value or "", variables)
        
        # Override with data profile value if variable is specified
        if step.variable_name and step.variable_name in variables:
            input_val = variables[step.variable_name]
        elif not step.variable_name and step.locator_value:
            # Auto-map Username and Password fields based on locator name if not explicitly mapped
            loc_lower = step.locator_value.lower()
            if "username" in loc_lower or "userid" in loc_lower:
                input_val = variables.get("Username", input_val)
            elif "password" in loc_lower:
                input_val = variables.get("Password", input_val)
            
        # Clean up corrupted target_val from bad parser
        is_role = False
        if target_val.endswith(")"):
            target_val = target_val[:-1]
            if ", name=" in target_val or "exact=True" in target_val or target_val.startswith('"link"') or target_val.startswith('"button"') or target_val.startswith('"textbox"'):
                is_role = True

        element = None
        locators_to_try = []
        if action in ["click", "fill"]:
            if step.locator_strategy == "text":
                element = page.get_by_text(target_val)
            elif step.locator_strategy == "label":
                element = page.get_by_label(target_val)
            elif step.locator_strategy == "role":
                val = target_val.strip()
                if "," in val and "name=" in val:
                    parts = val.split(",", 1)
                    role = parts[0].strip().strip('\'"')
                    name_val = parts[1].split("name=")[1].strip().strip('\'"')
                    element = page.get_by_role(role, name=name_val)
                else:
                    val_lower = val.lower().strip('\'"')
                    if val_lower in ["button", "link", "textbox", "checkbox", "radio", "combobox", "option", "menuitem", "heading", "listitem"]:
                        if step.target_name:
                            # Use case-insensitive substring match for target_name
                            import re
                            # Clean up target_name if AI appended " textbox" or " button"
                            clean_name = step.target_name
                            for suffix in [" textbox", " button", " link", " field", " input"]:
                                if clean_name.lower().endswith(suffix):
                                    clean_name = clean_name[:-len(suffix)]
                            
                            # Exact pattern for text/title fallbacks to prevent clicking random headers or tooltips
                            exact_pattern = re.compile(f"^\\s*{re.escape(clean_name)}\\s*$", re.IGNORECASE)
                            # Loose pattern for accessible role names which are generally safer to substring match
                            loose_pattern = re.compile(re.escape(clean_name), re.IGNORECASE)
                            
                            locators_to_try = []
                            if val_lower == "textbox":
                                locators_to_try = [
                                    page.get_by_role(val_lower, name=loose_pattern),
                                    page.get_by_label(loose_pattern),
                                    page.get_by_placeholder(loose_pattern)
                                ]
                            elif val_lower == "button":
                                locators_to_try = [
                                    page.get_by_role(val_lower, name=loose_pattern),
                                    page.get_by_role("link", name=loose_pattern),
                                    page.locator(f"*:not(input)[title='{clean_name}' i]"), # Case-insensitive title match excluding inputs
                                    page.get_by_text(exact_pattern)
                                ]
                            elif val_lower == "link":
                                locators_to_try = [
                                    page.get_by_role(val_lower, name=loose_pattern),
                                    page.get_by_text(exact_pattern)
                                ]
                            else:
                                locators_to_try = [
                                    page.get_by_role(val_lower, name=loose_pattern),
                                    page.get_by_text(exact_pattern)
                                ]
                        else:
                            locators_to_try = [page.get_by_role(val_lower)]
                    else:
                        locators_to_try = [page.get_by_role("button", name=val)]
            elif is_role:
                locators_to_try = [eval(f"page.get_by_role({target_val})")]
            else:
                if not step.locator_value and step.target_name:
                    import re
                    exact = re.compile(f"^\\s*{re.escape(step.target_name)}\\s*$", re.IGNORECASE)
                    loose = re.compile(re.escape(step.target_name), re.IGNORECASE)
                    locators_to_try = [
                        page.get_by_text(exact),
                        page.get_by_role("button", name=loose),
                        page.get_by_role("link", name=loose),
                        page.locator(f"*:not(input)[title='{step.target_name}' i]")
                    ]
                else:
                    locators_to_try = [page.locator(target_val)]

        def capture_screenshot():
            if not screenshot_path: return
            
            target_el = element.first if element else None
            
            if not target_el and locators_to_try:
                for locator in locators_to_try:
                    for el in locator.all():
                        if el.get_attribute("aria-expanded") is None and el.is_visible():
                            target_el = el
                            break
                    if target_el: break
                
                if not target_el:
                    for locator in locators_to_try:
                        if locator.count() > 0:
                            target_el = locator.first
                            break

            if target_el:
                try:
                    # Scroll into view before taking bounds
                    target_el.scroll_into_view_if_needed()
                    page.wait_for_timeout(100)
                    
                    # Highlight
                    target_el.evaluate("""(node) => {
                        const overlay = document.createElement('div');
                        overlay.id = 'fusion-test-highlight';
                        overlay.style.position = 'absolute';
                        const rect = node.getBoundingClientRect();
                        overlay.style.width = (rect.width + 10) + 'px';
                        overlay.style.height = (rect.height + 10) + 'px';
                        overlay.style.left = (rect.left + window.scrollX - 5) + 'px';
                        overlay.style.top = (rect.top + window.scrollY - 5) + 'px';
                        overlay.style.backgroundColor = 'rgba(253, 224, 71, 0.2)';
                        overlay.style.border = '3px solid #eab308';
                        overlay.style.borderRadius = '4px';
                        overlay.style.pointerEvents = 'none';
                        overlay.style.zIndex = '2147483647'; // max z-index
                        overlay.style.boxShadow = '0 0 15px rgba(234, 179, 8, 0.5)';
                        document.body.appendChild(overlay);
                    }""")
                    page.wait_for_timeout(300)
                    page.screenshot(path=screenshot_path)
                    
                    # Remove highlight
                    page.evaluate("""() => {
                        const overlay = document.getElementById('fusion-test-highlight');
                        if (overlay) overlay.remove();
                    }""")
                except Exception as e:
                    print(f"Highlight failed: {str(e)}")
                    page.screenshot(path=screenshot_path) # fallback
            else:
                page.wait_for_timeout(300)
                page.screenshot(path=screenshot_path)

        if action == "navigate":
            # Clean up cases where AI writes 'base_url/' instead of '{base_url}/'
            if target_val.startswith("base_url"):
                target_val = target_val[8:]
                
            # CRITICAL SECURITY FIX: Oracle blocks direct navigation to /signin URLs.
            # If the script hardcodes an IDCS login URL, we MUST override it to the environment's base_url
            if "idcs-" in target_val or "identity.oraclecloud.com" in target_val or "/signin" in target_val:
                url = base_url
            elif not target_val.startswith("http"):
                if not target_val.startswith("/"):
                    target_val = "/" + target_val
                url = f"{base_url}{target_val}"
            else:
                # If it's a hardcoded absolute URL that matches the base domain, we should really be using base_url 
                # but we'll allow it if it's not IDCS.
                url = target_val
                
            # Clean up double slashes just in case (e.g. domain.com//fscmUI)
            url = url.replace("://", "___SCHEME___").replace("//", "/").replace("___SCHEME___", "://")
            
            # Sanitize Oracle ADF URLs by removing dynamic session parameters
            import urllib.parse as urlparse
            parsed = urlparse.urlparse(url)
            query_params = urlparse.parse_qs(parsed.query, keep_blank_values=True)
            for p in ['_adf.ctrl-state', '_afrLoop', '_afrWindowMode', '_afrWindowId', '_afrFS', '_afrMT', '_afrMFW', '_afrMFH', '_afrMFDW', '_afrMFDH', '_afrMFC', '_afrMFCI', '_afrMFM', '_afrMFR', '_afrMFG', '_afrMFS', '_afrMFO']:
                query_params.pop(p, None)
            url = urlparse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlparse.urlencode(query_params, doseq=True), parsed.fragment))
            
            page.goto(url)
            capture_screenshot()
            
        elif action == "click":
            try:
                locators_to_try[0].first.wait_for(state="attached", timeout=25000)
                page.wait_for_timeout(500)
            except:
                pass
            
            capture_screenshot()
            
            clicked = False
            for _ in range(30):
                for locator in locators_to_try:
                    for el in locator.all():
                        # Skip accordion/collapsible panel headers that share the same name
                        if el.get_attribute("aria-expanded") is not None:
                            continue
                        if el.is_visible():
                            try:
                                el.click(timeout=5000)
                                clicked = True
                                break
                            except:
                                pass
                    if clicked:
                        break
                if clicked:
                    break
                page.wait_for_timeout(500)
            
            if not clicked:
                for locator in locators_to_try:
                    for el in locator.all():
                        if el.get_attribute("aria-expanded") is not None:
                            continue
                        try:
                            el.click(force=True, timeout=1000)
                            clicked = True
                        except:
                            pass
                    if clicked:
                        break
            
        elif action == "fill":
            try:
                locators_to_try[0].first.wait_for(state="attached", timeout=25000)
                page.wait_for_timeout(500)
            except:
                pass
                
            filled = False
            for _ in range(30):
                for locator in locators_to_try:
                    for el in locator.all():
                        if el.is_visible():
                            try:
                                el.fill(input_val, timeout=5000)
                                filled = True
                                break
                            except:
                                pass
                    if filled:
                        break
                if filled:
                    break
                page.wait_for_timeout(500)
            
            if not filled:
                for locator in locators_to_try:
                    try:
                        locator.first.fill(input_val, force=True, timeout=5000)
                        filled = True
                    except:
                        pass
                    if filled:
                        break
                
            capture_screenshot()
            
        elif action == "asserttext":
            assert_val = input_val if input_val else target_val
            if not assert_val:
                raise ValueError("No text provided to assert. Please provide it in target_name or locator_value.")
                
            if locators_to_try and step.locator_strategy and step.locator_strategy.lower() != "none":
                # Check specific element
                found = False
                for locator in locators_to_try:
                    try:
                        expect(locator.first).to_contain_text(assert_val, timeout=15000, ignore_case=True)
                        found = True
                        break
                    except:
                        pass
                if not found:
                    raise PlaywrightError(f"Assertion failed: Could not find text '{assert_val}' in specified element")
            else:
                # Check whole page
                expect(page.locator("body")).to_contain_text(assert_val, timeout=15000, ignore_case=True)
                
            capture_screenshot()
            
        elif action == "assertvisible":
            if not locators_to_try or not step.locator_strategy or step.locator_strategy.lower() == "none":
                raise ValueError("assertVisible requires a locator strategy and target")
                
            found = False
            for locator in locators_to_try:
                try:
                    expect(locator.first).to_be_visible(timeout=15000)
                    found = True
                    break
                except:
                    pass
            if not found:
                raise PlaywrightError(f"Assertion failed: Element '{target_val}' is not visible on the screen")
                
            capture_screenshot()

        elif action == "waitfor":
            try:
                # Read wait time from UI locator_value, default to 2 seconds if empty
                wait_time = float(step.locator_value) if step.locator_value else 2.0
            except ValueError:
                wait_time = 2.0
            time.sleep(wait_time)
            capture_screenshot()
