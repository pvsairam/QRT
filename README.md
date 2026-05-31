# QRT: AI-Powered Oracle Automation

Welcome to QRT. This project is an advanced, AI-driven web automation engine specifically designed to test and interact with Oracle Fusion applications. It translates natural language test cases into reliable, self-healing browser automation steps using Playwright.

## Project Overview

Testing enterprise applications like Oracle Fusion is notoriously difficult due to complex interfaces, hidden HTML elements, and dynamic loading. QRT solves this by combining the reasoning of AI with a robust execution engine. 

### Key Technical Features
* **FastAPI Backend:** A lightweight and incredibly fast Python web server that provides both the API and the user interface.
* **Intelligent Execution Engine:** Built on top of Microsoft Playwright, the engine dynamically parses the screen, handles Oracle's hidden CSS masks, and intelligently searches for buttons and links using a strict priority system.
* **AI Parser:** Automatically converts unstructured natural language test steps (like "Click Search") into structured JSON locator strategies.
* **SQLite Database:** A local, lightweight database managed by Alembic to store execution histories, test scripts, and data profiles.

---

## Complete Setup Instructions

Follow these steps to deploy and set up the QRT environment on a new machine.

### 1. Prerequisites
You will need to have the following installed on your machine:
* **Python 3.12 or newer**: Ensure that Python is added to your system PATH during installation.
* **Git**: To clone the repository.

### 2. Clone the Repository
Open your terminal or command prompt and download the project code:
```bash
git clone https://github.com/pvsairam/QRT.git
cd QRT/backend
```

### 3. Create a Virtual Environment
It is highly recommended to isolate the project dependencies. Create a virtual environment inside the `backend` directory:
```bash
python -m venv venv
```

Activate the virtual environment:
* On Windows: `venv\Scripts\activate`
* On Mac or Linux: `source venv/bin/activate`

### 4. Install Dependencies
With your virtual environment activated, install all the required Python libraries (like FastAPI, SQLAlchemy, and Playwright):
```bash
pip install -r requirements.txt
```

### 5. Install Playwright Browsers
The execution engine requires specific browser binaries to run the automation. Download them by running:
```bash
playwright install
```

### 6. Initialize the Database
The project uses Alembic to manage database schema migrations. To create your local SQLite database and build the tables, run:
```bash
alembic upgrade head
```

---

## How to Run the Application

Once your setup is complete, you can start the local web server. Make sure your virtual environment is activated, then run:

```bash
uvicorn app.main:app --reload
```

When you see the message "Application startup complete" in your terminal, the server is running. You can now access the web interface by opening a browser and navigating to:
`http://127.0.0.1:8000/ui/dashboard`

---

## How to Test the Tool

Testing the QRT automation engine is a straightforward process. The web interface is designed to help you configure and execute tests visually.

### Step 1: Create a Data Profile
To run tests, the engine needs valid Oracle credentials. 
1. Navigate to **Data Profiles** in the side menu.
2. Click **Add Profile** to create a new profile.
3. Securely enter your Oracle Cloud environment URL, username, and password. 

### Step 2: Configure a Test Script
Test scripts define the exact sequence of actions the engine will take.
1. Navigate to **Scripts** in the side menu.
2. You can either write a natural language script and ask the AI to parse it, or view an existing script like "Create Location".
3. Verify that the structured steps (like Navigate, Click, and Fill) look correct.

### Step 3: Run the Execution
1. Open the specific Test Script you want to run.
2. At the top of the page, select the Data Profile you created in Step 1.
3. Ensure the Execution Mode is set to "Structured Steps".
4. Click the **Run Execution** button.

The backend engine will immediately launch a Playwright browser window. It will inject your credentials, bypass any security bookmark errors, and autonomously execute the sequence of clicks and text inputs. You can watch the engine handle dynamic loads and accordion panels in real time as it completes the test.
