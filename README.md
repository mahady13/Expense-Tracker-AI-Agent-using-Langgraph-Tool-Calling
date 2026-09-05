# Expense Tracker AI Assistant

An AI-powered expense management application built with **Python,
LangGraph, LangChain, FastAPI, Streamlit, SQLite, Docker, GitHub
Actions, and Render**.

The project demonstrates how to take an LLM-based tool-calling
application from local development to a containerized, CI/CD-enabled
deployment.
## 🚀 Features

-   Add expenses using natural language
-   Retrieve a specific expense by ID
-   List all expenses for the current user
-   Generate expense summaries by category
-   Delete expenses with a human confirmation step
-   Persistent conversation state using LangGraph checkpoints
-   User-scoped expense data
-   LLM tool calling with LangGraph
-   FastAPI backend
-   Streamlit frontend
-   SQLite database for the learning/project implementation
-   Docker containerization
-   GitHub Actions CI/CD
-   Render deployment configuration
-   Environment-variable based API configuration

## 🏗️ Architecture

``` text
                    ┌──────────────────────┐
                    │      User            │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Streamlit Frontend  │
                    │    streamlit.py      │
                    └──────────┬───────────┘
                               │ HTTP POST /chat
                               ▼
                    ┌──────────────────────┐
                    │    FastAPI Backend   │
                    │     allinone.py      │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │      LangGraph       │
                    │   Agent Workflow     │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │         LLM          │
                    │   Tool Calling       │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼─────────────────┐
              ▼                ▼                 ▼
        Add Expense       Get Expense       List Expenses
              │                │                 │
              └────────────────┼─────────────────┘
                               ▼
                         ┌───────────┐
                         │  SQLite   │
                         │ expenses  │
                         └───────────┘

              Delete Flow
                    │
                    ▼
             Human Approval
                    │
              ┌─────┴─────┐
             Yes          No
              │            │
              ▼            ▼
           Delete       Cancel
```

## 🧰 Tech Stack

### Backend

-   Python
-   FastAPI
-   LangGraph
-   LangChain
-   Pydantic
-   SQLite
-   aiosqlite

### AI

-   LLM API through LangChain
-   Tool calling
-   Structured tool execution
-   Human-in-the-loop workflow for deletion

### Frontend

-   Streamlit
-   Python `requests`

### DevOps

-   Docker
-   Docker Hub
-   GitHub Actions
-   Render
-   CI/CD

## 📂 Project Structure

``` text
.
├── allinone.py
├── streamlit.py
├── Dockerfile
├── Dockerfile.backend
├── render.yaml
├── requirements.txt
├── .gitignore
├── .github/
│   └── workflows/
│       └── ci.yml
└── LanggraphExpenseAgent.ipynb
```

### Important files

**`allinone.py`**

Contains the FastAPI backend, LangGraph agent, tools, database
functions, checkpointing, and API endpoint.

**`streamlit.py`**

Provides the chat-based frontend and sends requests to the FastAPI
backend.

**`Dockerfile`**

Defines the container image used for deployment.

**`render.yaml`**

Contains the Render deployment configuration.

**`.github/workflows/ci.yml`**

Defines the GitHub Actions CI/CD workflow.

**`requirements.txt`**

Contains the Python dependencies required by the application.

## 🔧 Expense Tools

The agent currently exposes five tools:

1.  `add_expense_tool`
2.  `get_expense_tool`
3.  `get_summary_tool`
4.  `delete_expense_tool`
5.  `list_all_expenses_tool`

The system prompt instructs the LLM to select the appropriate tool based
on the user's request.

For example:

``` text
User: Show me all my expenses
        ↓
list_all_expenses_tool
        ↓
SQLite query
        ↓
Expense records
        ↓
LLM response
```

While:

``` text
User: Show me my food spending
        ↓
get_summary_tool
        ↓
SQLite aggregation
        ↓
Summary
```

## 🗄️ Database

The project currently uses SQLite:

``` text
expenses.db
```

The expense table contains:

``` text
expense_id
user_id
amount
category
description
date
```

SQLite was intentionally used as a lightweight database for this project
and learning environment.

For a larger production system, the database layer can later be migrated
to a server-based relational database such as PostgreSQL without
changing the overall agent architecture.

## 🧠 LangGraph Workflow

The application uses a graph-based workflow:

``` text
START
  │
  ▼
 LLM
  │
  ├── No tool call ───────────────► END
  │
  └── Tool call
          │
          ▼
        Tools
          │
          ▼
         LLM
```

Deletion has an additional human-approval flow:

``` text
User requests deletion
        │
        ▼
delete_expense_tool
        │
        ▼
Confirm with user
        │
     ┌──┴──┐
    Yes    No
     │      │
     ▼      ▼
  Delete   Cancel
```

LangGraph checkpointing is used to maintain conversation/workflow state.

## ▶️ Run Locally

### 1. Clone the repository

``` bash
git clone <your-repository-url>
cd Expense-Tracker-AI-Agent-using-Langgraph-Tool-Calling
```

### 2. Create a virtual environment

Windows:

``` bash
python -m venv .venv
.venv\Scripts\activate
```

Linux/macOS:

``` bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

``` bash
pip install -r requirements.txt
```

### 4. Start the FastAPI backend

``` bash
uvicorn allinone:app --reload
```

The backend runs on:

``` text
http://127.0.0.1:8000
```

### 5. Start Streamlit

In another terminal:

``` bash
streamlit run streamlit.py
```

The frontend will normally be available at:

``` text
http://localhost:8501
```

The Streamlit application reads the backend URL from:

``` env
API_URL
```

## 🐳 Docker

The application is containerized with Docker.

Build the image:

``` bash
docker build -t mahady13/expense_tracker_ai_agent .
```

Run it:

``` bash
docker run -p 8502:8502 mahady13/expense_tracker_ai_agent
```

The image is published to Docker Hub under:

``` text
mahady13/expense_tracker_ai_agent
```

## 🔄 CI/CD

This project uses **GitHub Actions + Docker Hub + Render** to automate
deployment.

High-level pipeline:

``` text
Developer
    │
    ▼
Git push
    │
    ▼
GitHub Repository
    │
    ▼
GitHub Actions
    │
    ├── Install dependencies
    ├── Run CI checks
    ├── Build Docker image
    └── Push image to Docker Hub
                │
                ▼
          Docker Hub
                │
                ▼
             Render
                │
                ▼
          Deployed App
```

The workflow configuration is located at:

``` text
.github/workflows/ci.yml
```

Render deployment configuration is located at:

``` text
render.yaml
```

This means changes can be pushed to GitHub and processed automatically
instead of manually rebuilding and deploying every change.

## ☁️ Deployment

The application is designed to use:

-   **GitHub** for source control
-   **GitHub Actions** for automation
-   **Docker Hub** for container images
-   **Render** for cloud deployment

Secrets such as API keys should be configured through the deployment
platform's environment-variable/secrets settings rather than committed
to the repository.

## 🧪 Example Usage

``` text
User:
Show me all my expenses

Assistant:
ID    Date        Category    Description       Amount
1     2025-08-14  Food        Burger             200.00
2     2026-08-08  Food        Tea                 30.00
3     2026-08-08  Food        Coffee              25.00
...
```

Other supported requests include:

``` text
Add 50 BDT for lunch today

Show me expense ID 3

Show my food expense summary

Delete expense ID 2
```

Deletion requires confirmation before the record is removed.

## 📈 What This Project Demonstrates

This project was built as a practical learning implementation of
production-oriented AI engineering concepts:

-   LLM application architecture
-   Agentic workflows
-   LangGraph state management
-   Tool calling
-   RAG/AI-system development foundations
-   REST API development
-   Database interaction
-   Human-in-the-loop controls
-   Containerization
-   Environment-based configuration
-   CI/CD automation
-   Cloud deployment
-   Debugging local-vs-cloud deployment issues

The implementation intentionally starts with simple infrastructure so
the core engineering concepts can be understood before introducing more
complex infrastructure.

## 🔮 Future Improvements

Possible next steps include:

-   Replace SQLite with PostgreSQL
-   Add authentication and proper user management
-   Add automated unit/integration tests
-   Add API validation and structured error handling
-   Add production logging and observability
-   Add database migrations
-   Add Redis or another production-grade state/cache layer where
    appropriate
-   Add stronger security controls
-   Add automated deployment approvals
-   Add monitoring and health checks
-   Improve agent evaluation and tool-call reliability

## 👨‍💻 Author

**Mohiuddin Mahady**

Built as a hands-on AI engineering and DevOps project focused on
learning how to move an LLM-powered application from local development
toward production-style deployment.
