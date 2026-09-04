import os
import uuid
from dotenv import load_dotenv
from langchain_core.tools import tool


from langchain_groq import ChatGroq
import sqlite3
import langgraph
import asyncpg
import uvicorn
from langchain_core.messages import SystemMessage
from langgraph.graph import START,StateGraph,MessagesState,END
from langgraph.types import interrupt
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from pydantic import BaseModel
from fastapi import FastAPI
from langgraph.types import RunnableConfig,Command

load_dotenv()

DATABASE_URL=os.getenv("DATABASE_URL")
class Database:
    """
    PostGresSql database handler for supabase
    """
    def __init__(self,dsn:str):
        self.dsn=dsn
        self._pool=None


    async def connect(self):
        """Create connection pool"""
        if self._pool is None:
            self._pool=await asyncpg.create_pool(
                self.dsn,
                min_size=1,
                max_size=5,
                command_timeout=30,
                max_inactive_connection_lifetime=300,
                statement_cache_size=0
            )
            return self._pool
    async def create_table(self):
        """Create expense table in PostGresSql"""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expenses(
                expense_id SERIAL PRIMARY KEY ,
                user_id TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                date TEXT NOT NULL
                )
                """
            )
            print("table_created")
    async def add_expense(self,user_id:str,amount:float,category:str,description:str,date:str):
        async with self._pool.acquire() as conn:
            result=await conn.fetchrow(
                """ INSERT INTO expenses(user_id,amount,category,description,date)
                VALUES($1,$2,$3,$4,$5) 
                RETURNING expense_id""",user_id,amount,category,description,date
            )
            return f"Expense {result['expense_id']} created successfully"

    async def get_summary(self,user_id:str,category:str|None=None):
        async with self._pool.acquire() as conn:
            if category:
                result=await conn.fetch(
                    """
                    SELECT category,SUM(amount) FROM expenses WHERE user_id=$1 AND category=$2
                    """,user_id,category
                )
            else:
                result=await conn.fetch(
                    """
                    SELECT category,SUM(amount) FROM expenses WHERE user_id=$1
                    """,user_id
                )
            return result

    async def get_expenses(self,user_id,expense_id:int):
        async with self._pool.acquire() as conn:
            result=await conn.fetchrow(
                """
                SELECT * FROM expenses WHERE user_id=$1 AND expense_id=$2
                """,user_id,expense_id
            )
            return result
    async def delete_expense(self,user_id:str,expense_id:int):
        async with self._pool.acquire() as conn:
            result=await conn.execute(
                """
                DELETE FROM expenses WHERE user_id=$1 AND expense_id=$2
                """,user_id,expense_id
            )
            return result != "DELETE 0"

    async def list_expenses(self,user_id:str):
        async with self._pool.acquire() as conn:
            results=await conn.fetch(
                """
                SELECT * FROM expenses WHERE user_id=$1
                """,user_id
            )
        return [(result['expense_id'],result['amount'],result['category'],result['description'],result['date']) for result in results]

    async def close(self):
        if self._pool:
            await self._pool.close()

db=Database(DATABASE_URL)

async def init_db():
    await db.connect()
    await db.create_table()


class AgentState(MessagesState):
    confirmed:bool
    notice:str


#tools

@tool
async def add_expense_tool(amount:float,category:str,description:str,date:str,config:RunnableConfig):
    """Add expense tool"""

    user_id=config["configurable"]["user_id"]

    return await db.add_expense(user_id,amount,category,description,date)

@tool
async def get_expense_tool(expense_id:int,config:RunnableConfig):
    """Get single expense tool"""

    user_id=config["configurable"]["user_id"]

    return await db.get_expenses(user_id,expense_id)

@tool
async def get_summary_tool(category:str|None=None,config:RunnableConfig=None):
    """get summary tool"""
    user_id=config["configurable"]["user_id"]

    return await db.get_summary(user_id,category)

@tool
async def delete_expense_tool(expense_id:int,config:RunnableConfig):
    """delete expense tool that prepares an expense for deletion"""
    user_id=config["configurable"]["user_id"]
    result=await db.get_expenses(user_id,expense_id)
    if result:
        return f"{expense_id} is ready for deletion"
    return f"{expense_id} is not available or user has no authority"

@tool
async def list_all_expenses_tool(config:RunnableConfig):
    """List every individual expense recorded for the current user."""

    user_id=config["configurable"]["user_id"]
    result=await db.list_expenses(user_id)
    if not result:
        return "no expenses found"
    formatted = "Your expenses:\n"
    for expense in result:
        formatted += f"- ID: {expense[0]}, Amount: {expense[1]}, Category: {expense[2]}, Description: {expense[3]}, Date: {expense[4]}\n"
    
    return formatted

tools=[add_expense_tool,get_expense_tool,get_summary_tool,delete_expense_tool,list_all_expenses_tool]


llm = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0,
    max_tokens=400,
    timeout=None,
    max_retries=2,
)

llm_with_tools=llm.bind_tools(tools)
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
    message=[SystemMessage(content=system_message),*state["messages"][-4:]]

    response=await llm_with_tools.ainvoke(message)
    
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
            return "confirm_delete"
    return "tools"

def confirm_delete(state:AgentState):
    answer=interrupt("Are you sure you want to delete this expense? Reply yes or no")
    confirmed=(answer.lower().strip()=="yes")

    return {"confirmed":confirmed}

def route_after_delete(state:AgentState):
    if state["confirmed"]:
        return "execute_delete"
    return "cancel_delete"

async def execute_delete(state:AgentState,config:RunnableConfig):
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
    available=await db.get_expenses(user_id,expense_id)
    if not available:
        return {"messages": [("assistant", f"Expense {expense_id} not found")]}
    deleted=await db.delete_expense(user_id,expense_id)
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


from contextlib import asynccontextmanager
checkpoint_connection=None
checkpointer=None
graph=None
@asynccontextmanager
async def lifespan(app:FastAPI):
    global checkpoint_connection,checkpointer,graph

    connection = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    checkpointer = AsyncPostgresSaver(connection)
    await checkpointer.setup()
    graph=builder.compile(checkpointer=checkpointer)
    await init_db()
    yield
    await db.close()
    
#fastapi
app=FastAPI(title="Expense Tracker AI(Production Grade)",lifespan=lifespan)

class ChatRequest(BaseModel):
    message:str
    thread_id:str|None=None
    user_id:str


@app.get("/health")
async def health_check():
    """SImple health check for render"""
    try:
        await db.connect()
        async with db._pool.acquire() as conn:
            await conn.fetch("SELECT 1")
        return {"status":"healthy","database":"connected"}
    except Exception as e:
        return {"status":"not connected","database":f"error:{str(e)}"}

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

    try:
        current_state=await graph.aget_state(config)
        if current_state.interrupts:
            result_state=await graph.ainvoke(Command(resume=request.message),config=config)

            new_state=await graph.aget_state(config)
            if new_state.interrupts:
                return {
                    "thread_id":thread_id,
                    "status":"confirmation_required",
                    "message":new_state.interrupts[0].value
                }
            return {
                "thread_id":thread_id,
                "status":"completed",
                "message":result_state["messages"][-1].content
            }
        else:
            result_state=await graph.ainvoke(
                {"messages":[("user",request.message)],
                "user_id":request.user_id,
                "confirmed":False,
                "notice":""},config=config
            )

            after_state=await graph.aget_state(config)
            if after_state.interrupts:
                return {
                    "thread_id":thread_id,
                    "status":"confirmation required",
                    "message":after_state.interrupts[0].value
                }

            return {
                "thread_id":thread_id,
                "status":"completed",
                "message":result_state["messages"][-1].content
            }

    except Exception as e:
        print(f"error: {str(e)}")
        import traceback
        traceback.print_exc() 
        return {
            "thread_id":thread_id,
            "status":"error",
            "message":f"Error occured : {str(e)}"
        }
