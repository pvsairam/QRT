# QRT - The Magic Oracle Automation Tool

Hello! Welcome to QRT. 

Think of this tool like a smart robot. Its job is to open a web browser, go to Oracle Cloud, log in for you, and click all the right buttons so you do not have to do the boring work yourself!

You can easily move this robot to a brand new computer and run it there. Here is exactly how to do it, step by step.

## How to Set Up the Robot on a New Computer

### Step 1: Install Python
Your computer needs to understand the language the robot speaks. This language is called Python.
1. Go to the official Python website (python.org) and download Python 3.12 or newer.
2. When installing, you must check the box that says "Add Python to PATH" before clicking Install. This is very important!

### Step 2: Download This Code
Copy all the files in this project to your new computer. You can download it from GitHub as a ZIP file or use git to clone it. Extract the folder somewhere easy to find, like your Desktop.

### Step 3: Open the Terminal
We need to give the robot a few commands. Open the command prompt (or terminal) on your new computer and navigate to the folder where you saved the code. Make sure you are inside the `backend` folder.

### Step 4: Create a Safe Space for the Robot
We want to keep the robot's tools separate from the rest of your computer. We do this by creating a virtual environment. Type this command and press Enter:
`python -m venv venv`

### Step 5: Turn on the Safe Space
Now we have to activate the space we just made. 
If you are on Windows, type:
`venv\Scripts\activate`

If you are on Mac or Linux, type:
`source venv/bin/activate`

### Step 6: Install the Robot's Tools
The robot needs some special tools to work. We have a list of them in a file called `requirements.txt`. Tell the computer to install them by typing:
`pip install -r requirements.txt`

### Step 7: Install the Web Browser
The robot uses a special version of web browsers (like Chrome or Edge) to do its clicking. Tell it to download these browsers by typing:
`playwright install`

### Step 8: Build the Robot's Brain
The robot needs a database to remember what tests to run and what passwords to use. Tell it to build its brain by typing:
`alembic upgrade head`

## How to Turn on the Tool

Once everything is installed, you can start the application! Make sure your virtual environment is still activated (from Step 5). 

Then, just type this command:
`uvicorn app.main:app --reload`

You will see some text scrolling by. Look for a line that says "Application startup complete". This means the robot is awake and ready!

Now, open your normal web browser (like Google Chrome) and type `http://127.0.0.1:8000/ui/dashboard` into the address bar at the top. You will see the main dashboard of the tool!

## How to Test the Tool

Testing the tool is super easy and fun!

1. **Go to the Dashboard**: Open your browser and go to `http://127.0.0.1:8000/ui/dashboard`.
2. **Set up a Data Profile**: Click on "Data Profiles" in the menu. This is where you securely save your Oracle username and password. Create a new profile and fill in your details.
3. **Go to Scripts**: Click on "Scripts" in the menu. This is where the magic test scripts live.
4. **Run a Test**: Click on one of your test scripts. 
5. **Watch the Magic**: Choose the data profile you made earlier, and then click the "Run Execution" button! 

The robot will immediately wake up, open a brand new browser window, and start typing and clicking all by itself. Keep your hands off the mouse and watch it do your work for you!
