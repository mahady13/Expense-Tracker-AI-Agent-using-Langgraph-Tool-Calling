import os
import uuid
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
import sqlite3
import langgraph
import aiosqlite
import cursor
from langchain_core.messages import SystemMessage
from langgraph.graph import START,StateGraph,MessagesState,END
from langgraph.prebuilt import interrupt
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel
from fastapi import FastAPI
from langgraph.types import RunnableConfig,Command

load_dotenv()

db_name="expenses.db"
def get_connection():
    return sqlite3.connect(db_name)

def create_database():
    connection=get_connection()
    cursor=connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses(
        expense_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        amount REAL NOT NULL,
        category TEXT NOT NULL,
        description TEXT,
        date TEXT 
        )
        """
    )
    connection.commit()
    connection.close()

def add_expense(user_id:str,amount:float,category:str,description:str,date:str):
    connection=get_connection()
    cursor=connection.cursor()
    cursor.execute(
        """
        INSERT INTO expenses(
        user_id,amount,category,description,date)
        VALUES (?,?,?,?,?)
        """,(user_id,amount,category,description,date)
    )
    expense=cursor.lastrowid
    connection.commit()
    connection.close()
    return f"Expense {expense} added successfully"

def list_expenses(user_id:str):
    connection=get_connection()
    cursor=connection.cursor()
    cursor.execute(
        """
        SELECT expense_id, amount, category, description, date FROM expenses WHERE user_id=? ORDER BY expense_id
        """,(user_id,)
    )
    expenses=cursor.fetchall()
    connection.close()
    return expenses

def get_expenses(user_id:str,expense_id):
    connection=get_connection()
    cursor=connection.cursor()

    cursor.execute(
        """
        SELECT * FROM expenses WHERE expense_id=? AND user_id=?
        """,(expense_id,user_id)
    )
    expense=cursor.fetchone()
    connection.close()

    return expense

def get_summary(user_id:str,category:str|None=None):
    connection=get_connection()
    cursor=connection.cursor()
    if user_id:
        if category:
            cursor.execute(
                """
                SELECT category,SUM(amount) FROM expenses WHERE category=? AND user_id=? GROUP BY category
                """,(category,user_id)
            )
        else:
            cursor.execute(
                """
                SELECT category,SUM(amount) FROM expenses WHERE user_id=? GROUP BY category
                """,(user_id,)
            )
        expense=cursor.fetchall()
        connection.close()
        return expense
    else:
        return "Provide user id please"

def delete_expense(user_id:str,expense_id:str):
    connection=get_connection()
    cursor=connection.cursor()

    cursor.execute(
        """
        DELETE FROM expenses WHERE expense_id=? AND user_id=?
        """,(expense_id,user_id)
    )
    expense=cursor.rowcount>0
    connection.commit()
    connection.close()
    return expense
create_database()

#langgraph state

class AgentState(MessagesState):
    confirmed:bool
    notice:str


#tools

@tool
def add_expense_tool(amount:float,category:str,description:str,date:str,config:RunnableConfig):
    """Add expense tool"""

    user_id=config["configurable"]["user_id"]

    return add_expense(user_id,amount,category,description,date)

@tool
def get_expense_tool(expense_id:str,config:RunnableConfig):
    """Get single expense tool"""

    user_id=config["configurable"]["user_id"]

    return get_expenses(user_id,expense_id)

@tool
def get_summary_tool(category:str|None=None,config:RunnableConfig=None):
    """get summary tool"""
    user_id=config["configurable"]["user_id"]

    return get_summary(user_id,category)

@tool
def delete_expense_tool(expense_id:str,config:RunnableConfig):
    """delete expense tool that prepares an expense for deletion"""
    user_id=config["configurable"]["user_id"]
    result=get_expenses(user_id,expense_id)
    if result:
        return {f"{expense_id} is ready for deletion"}
    return {f"{expense_id} is not available or user has no authority"}

@tool
def list_all_expenses_tool(config:RunnableConfig):
    """List every individual expense recorded for the current user.

    Use this tool when the user asks to:
    - show all expenses
    - list all expenses
    - see my expenses
    - show my expense history

    Do NOT use get_summary_tool for these requests."""
    print("list expesnses tool called")
    user_id=config["configurable"]["user_id"]
    result=list_expenses(user_id)
    print("result:",result)
    return result

tools=[add_expense_tool,get_expense_tool,get_summary_tool,delete_expense_tool,list_all_expenses_tool]

#llm
llm=ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    model="openrouter/free",
    max_tokens=300,
    temperature=0
)

llm_with_tools=llm.bind_tools(tools)
print("AVAILABLE TOOLS:")
for t in tools:
    print(t.name)
system_message = """
You are an expense management assistant.

Rules:
- Use tools for expense data. Never invent expenses or IDs.
- Use list_expenses_tool for listing/viewing expense history.
- Use get_summary_tool for totals and summaries.
- Use get_expense_tool for a specific expense ID.
- Use add_expense_tool only when the user explicitly asks to add an expense.
- All amounts are in BDT/TK, never USD.
- Keep responses concise.
"""

async def call_llm(state:AgentState):
    print("🔥🔥 CALL_LLM WAS CALLED 🔥🔥")
    message=[SystemMessage(content=system_message),*state["messages"][-4:]]

    response=await llm_with_tools.ainvoke(message)

    print("LLM RESPONSE:", response)
    print("TOOL CALLS:", response.tool_calls)
    
    return {"messages":[response]}

def delete_request(state:AgentState,config:RunnableConfig):
    message=state["messages"][-1]
    if not message.tool_calls:
        return END
    for tool_call in message.tool_calls:
        if tool_call["name"]=="delete_expense_tool":
            args=tool_call["args"]
            if "expense_id" not in args:
                return "tools"
            expense_id=args.get("expense_id")
            user_id=config["configurable"]["user_id"]
            available=get_expenses(user_id,expense_id)
            if available:
                return "confirm_delete"
            return "tools"
    return "tools"

def confirm_delete(state:AgentState):
    answer=langgraph.prebuilt.interrupt("Are you sure you want to delete this expense? Reply yes or no")
    confirmed=(answer.lower().strip()=="yes")

    return {"confirmed":confirmed}

def route_after_delete(state:AgentState):
    if state["confirmed"]:
        return "execute_delete"
    return "cancel_delete"

def execute_delete(state:AgentState,config:RunnableConfig):
    expense_id=None
    for message in reversed(state["messages"]):
        if hasattr(message,"tool_calls"):
            for tool_call in message.tool_calls:
                if tool_call["name"]=="delete_expense_tool":
                    args=tool_call["args"]
                    expense_id=args["expense_id"]
                    break

        if expense_id is not None:
            break

    if expense_id is None:
        return {
            "messages":[("assistant","i could not identify the expense")]
        }

    user_id=config["configurable"]["user_id"]
    deleted=delete_expense(user_id,expense_id)
    if deleted:
        return {
            "messages":[("assistant",f"{expense_id} has been deleted")]
        }
    return {
        "messages":[("assistant","the expense could not be deleted")]
    }

def cancel_delete(state:AgentState):
    return {"messages":[("assistant","Deletion cancelled")]}

builder=StateGraph(AgentState)

builder.add_node("llm",call_llm)
builder.add_node("tools",ToolNode(tools))
builder.add_node("execute_delete",execute_delete)
builder.add_node("confirm_delete",confirm_delete)
builder.add_node("cancel_delete",cancel_delete)

builder.add_conditional_edges("llm",delete_request,{
    "tools":"tools",
    "confirm_delete":"confirm_delete",
    END:END
})

builder.add_edge(START,"llm")
builder.add_edge("tools","llm")
builder.add_conditional_edges("confirm_delete",route_after_delete,{
    "execute_delete":"execute_delete",
    "cancel_delete":"cancel_delete"
})
builder.add_edge("execute_delete","llm")
builder.add_edge("cancel_delete","llm")

checkpoint_connection=aiosqlite.connect("checkpoint.db",check_same_thread=False)

checkpointer=AsyncSqliteSaver(checkpoint_connection)

graph=builder.compile(checkpointer=checkpointer)

#fastapi
app=FastAPI(title="Expense Tracker AI(Production Grade)")

class ChatRequest(BaseModel):
    message:str
    thread_id:str|None=None
    user_id:str


@app.post("/chat")
async def chat(request:ChatRequest):
    print("🔥 CHAT ENDPOINT REACHED")
    if request.thread_id:
        thread_id=request.thread_id
    else:
        thread_id=str(uuid.uuid4())

    config={
        "configurable":{
            "thread_id":thread_id,
            "user_id":request.user_id
        }
    }

    state=await graph.aget_state(config)
    if state.interrupts:
        result=await graph.ainvoke(Command(resume=request.message),config=config)

    else:
        result=await graph.ainvoke(
            {"messages":[("user",request.message)],
             "user_id":request.user_id,
             "confirmed":False,
             "notice":""},config=config
        )

    if "__interrupt__" in result:
        return {
            "thread_id":thread_id,
            "status":"confirmation required",
            "message":result["__interrupt__"][0].value
        }

    return {
        "thread_id":thread_id,
        "status":"completed",
        "message":result["messages"][-1].content
    }


