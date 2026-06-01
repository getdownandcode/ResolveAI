import os
import json
import threading
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel

from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware

from database import init_db, reset_db, query_db, execute_db
from agent import graph, get_gemini_client

app = FastAPI(title="ResolveAI Backend Gateway", version="1.0.0")

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local development, allow all. In production, restrict.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize SQLite database on startup
@app.on_event("startup")
def startup_event():
    init_db()

# Pydantic schemas for endpoints
class TicketCreate(BaseModel):
    title: str
    description: str

class HITLApproval(BaseModel):
    apiKey: Optional[str] = None

class HITLRejection(BaseModel):
    reason: str
    apiKey: Optional[str] = None

# Background worker to execute LangGraph ReAct loop
def execute_agent_thread(ticket_id: str, state_update: Optional[Dict[str, Any]] = None, api_key: Optional[str] = None):
    """
    Executes the LangGraph loop in a background thread so the HTTP server
    remains responsive.
    """
    # 1. Temporarily write api key to environment if passed dynamically from UI
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key
        
    config = {"configurable": {"thread_id": ticket_id}}
    
    try:
        if state_update:
            # Updating state after human interaction (Approved or Rejected)
            graph.update_state(config, state_update, as_node="pause_node")
            # Resume graph execution (input = None resumes from the interrupted node)
            for event in graph.stream(None, config):
                pass
        else:
            # Initial run of the support agent
            ticket_row = query_db("SELECT description FROM tickets WHERE ticket_id = ?", (ticket_id,), one=True)
            if not ticket_row:
                raise ValueError("Ticket not found in DB")
                
            desc = ticket_row["description"]
            initial_state = {
                "messages": [{"role": "user", "content": desc}],
                "ticket_id": ticket_id,
                "user_id": "",
                "pending_action": None,
                "action_approved": None,
                "action_rejected_reason": "",
                "confidence_score": 90,
                "logs": [{
                    "timestamp": datetime.now().isoformat(),
                    "type": "thought",
                    "message": "Ticket created. Agent processing initiated."
                }],
                "iterations": 0
            }
            
            # Start streaming the graph (input = initial_state)
            for event in graph.stream(initial_state, config):
                pass
                
    except Exception as e:
        import traceback
        error_msg = f"Execution Error: {str(e)}\n\n{traceback.format_exc()}"
        
        # Read current logs
        ticket_row = query_db("SELECT logs FROM tickets WHERE ticket_id = ?", (ticket_id,), one=True)
        logs = json.loads(ticket_row["logs"]) if ticket_row and ticket_row["logs"] else []
        
        logs.append({
            "timestamp": datetime.now().isoformat(),
            "type": "thought",
            "message": error_msg
        })
        
        # Mark ticket as REJECTED/FAILED due to error
        execute_db(
            "UPDATE tickets SET status = 'REJECTED', logs = ? WHERE ticket_id = ?",
            (json.dumps(logs), ticket_id)
        )

# --- REST Endpoints ---

@app.post("/api/tickets")
def create_ticket(ticket: TicketCreate, background_tasks: BackgroundTasks, x_api_key: Optional[str] = Header(None)):
    """
    Creates a new support ticket and triggers the LangGraph agent in the background.
    Supports a custom X-API-KEY header if passed from frontend.
    """
    ticket_id = f"TKT-{datetime.now().strftime('%Y%m%d')}-{os.urandom(2).hex().upper()}"
    created_at = datetime.now().isoformat()
    
    # Save ticket skeleton to Database
    execute_db(
        "INSERT INTO tickets (ticket_id, title, description, status, created_at, logs) VALUES (?, ?, ?, 'OPEN', ?, ?)",
        (ticket_id, ticket.title, ticket.description, created_at, json.dumps([]))
    )
    
    # Trigger background thread
    background_tasks.add_task(execute_agent_thread, ticket_id, None, x_api_key)
    
    return {"ticket_id": ticket_id, "status": "OPEN"}

@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    """
    Returns the full state of a ticket, including database details,
    real-time thought logs, pending approvals, and the final structured resolution.
    """
    ticket_row = query_db("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,), one=True)
    if not ticket_row:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    config = {"configurable": {"thread_id": ticket_id}}
    
    # Query LangGraph state via memory checkpointer
    graph_state = graph.get_state(config)
    
    pending_action = None
    is_paused = False
    confidence_score = 90
    final_resolution = None
    
    if graph_state and graph_state.values:
        values = graph_state.values
        pending_action = values.get("pending_action")
        confidence_score = values.get("confidence_score", 90)
        
        # Determine if graph is currently suspended at an interrupt node
        is_paused = "pause_node" in graph_state.next
        
        # Parse final response if available
        messages = values.get("messages", [])
        if messages:
            last_msg = messages[-1]
            is_model = False
            has_tool_calls = False
            content = ""
            
            if isinstance(last_msg, dict):
                is_model = last_msg.get("role") in ("model", "ai", "assistant")
                has_tool_calls = "function_calls" in last_msg or "tool_calls" in last_msg
                content = last_msg.get("content", "")
            else:
                is_model = getattr(last_msg, "type", "") == "ai"
                has_tool_calls = len(getattr(last_msg, "tool_calls", [])) > 0 or len(getattr(last_msg, "additional_kwargs", {}).get("tool_calls", [])) > 0
                content = getattr(last_msg, "content", "")
                
            if is_model and not has_tool_calls:
                try:
                    final_resolution = json.loads(content)
                except json.JSONDecodeError:
                    pass
                
    # Fallback logs from DB
    logs = json.loads(ticket_row["logs"]) if ticket_row["logs"] else []
    
    return {
        "ticket_id": ticket_row["ticket_id"],
        "title": ticket_row["title"],
        "description": ticket_row["description"],
        "status": ticket_row["status"],
        "created_at": ticket_row["created_at"],
        "logs": logs,
        "confidence_score": confidence_score,
        "pending_action": pending_action,
        "is_paused": is_paused,
        "final_resolution": final_resolution
    }

@app.post("/api/tickets/{ticket_id}/approve")
def approve_ticket_action(ticket_id: str, payload: HITLApproval, background_tasks: BackgroundTasks):
    """
    Human-in-the-Loop Approval: Sets action_approved = True in LangGraph state
    and resumes execution.
    """
    config = {"configurable": {"thread_id": ticket_id}}
    graph_state = graph.get_state(config)
    
    if not graph_state or "pause_node" not in graph_state.next:
        raise HTTPException(status_code=400, detail="Ticket is not awaiting approval")
        
    state_update = {
        "action_approved": True,
        "action_rejected_reason": ""
    }
    
    # Resume agent loop in background
    background_tasks.add_task(execute_agent_thread, ticket_id, state_update, payload.apiKey)
    
    return {"status": "resumed_approved"}

@app.post("/api/tickets/{ticket_id}/reject")
def reject_ticket_action(ticket_id: str, payload: HITLRejection, background_tasks: BackgroundTasks):
    """
    Human-in-the-Loop Rejection: Sets action_approved = False and adds custom feed back
    so the agent can reflect and self-correct.
    """
    config = {"configurable": {"thread_id": ticket_id}}
    graph_state = graph.get_state(config)
    
    if not graph_state or "pause_node" not in graph_state.next:
        raise HTTPException(status_code=400, detail="Ticket is not awaiting approval")
        
    state_update = {
        "action_approved": False,
        "action_rejected_reason": payload.reason
    }
    
    # Resume agent loop in background
    background_tasks.add_task(execute_agent_thread, ticket_id, state_update, payload.apiKey)
    
    return {"status": "resumed_rejected"}

@app.get("/api/database")
def get_database_snapshot():
    """
    Returns a snapshot of the mock CRM database tables (users, orders, emails_sent, tickets)
    to power the real-time DB viewer panel on the UI.
    """
    users = [dict(r) for r in query_db("SELECT * FROM users")]
    orders = [dict(r) for r in query_db("SELECT * FROM orders")]
    emails = [dict(r) for r in query_db("SELECT * FROM emails_sent ORDER BY sent_at DESC")]
    tickets = [dict(r) for r in query_db("SELECT ticket_id, title, status, created_at FROM tickets ORDER BY created_at DESC")]
    
    return {
        "users": users,
        "orders": orders,
        "emails": emails,
        "tickets": tickets
    }

@app.post("/api/database/reset")
def reset_database():
    """Resets SQLite tables to seed state."""
    reset_db()
    return {"status": "database_reset_successful"}
