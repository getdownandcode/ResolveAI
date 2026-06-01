import json
from datetime import datetime
from typing import TypedDict, Annotated, List, Dict, Any
from pydantic import BaseModel, Field

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from config import get_gemini_client
from database import execute_db, query_db
import tools

# State definition
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    ticket_id: str
    user_id: str
    pending_action: Dict[str, Any]       # Info about action waiting for approval
    action_approved: bool                # True = approved, False = rejected
    action_rejected_reason: str          # Feedback if rejected
    confidence_score: int                # 0-100 confidence
    logs: List[Dict[str, Any]]           # Step-by-step logs: {"timestamp": ..., "type": "thought"|"action"|"observation", "message": ...}
    iterations: int                      # Iteration tracker to prevent infinite loops

# Define the structured final resolution schema
class FinalResolution(BaseModel):
    status: str = Field(description="The status of the ticket: RESOLVED, REJECTED, or ESCALATED")
    action_taken: str = Field(description="Detailed summary of all operations executed during resolution")
    needs_human: bool = Field(description="True if a human must perform manual follow-up work, else False")
    resolution_summary: str = Field(description="A friendly message to show the customer explaining the outcome")

# List of python tools available to the client
GEMINI_TOOLS = [
    tools.search_knowledge_base,
    tools.get_user_account,
    tools.add_loyalty_points,
    tools.get_order_details,
    tools.unlock_user_account,
    tools.issue_refund,
    tools.send_support_email,
    tools.web_search
]

def run_tool_by_name(name: str, args: dict) -> str:
    """Executes the tool by name with arguments."""
    try:
        if name == "search_knowledge_base":
            return tools.search_knowledge_base.invoke(args)
        elif name == "get_user_account":
            return tools.get_user_account.invoke(args)
        elif name == "add_loyalty_points":
            return tools.add_loyalty_points.invoke(args)
        elif name == "get_order_details":
            return tools.get_order_details.invoke(args)
        elif name == "unlock_user_account":
            return tools.unlock_user_account.invoke(args)
        elif name == "issue_refund":
            return tools.issue_refund.invoke(args)
        elif name == "send_support_email":
            return tools.send_support_email.invoke(args)
        elif name == "web_search":
            return tools.web_search.invoke(args)
        else:
            return f"Error: Tool '{name}' not found."
    except Exception as e:
        return f"Error executing tool '{name}': {str(e)}"

def convert_messages_to_gemini(messages_list):
    """Converts local state messages (dict or LangChain objects) to Gemini Content format."""
    from google.genai import types
    gemini_contents = []
    
    for msg in messages_list:
        parts = []
        
        # 1. Handle dictionary-based messages
        if isinstance(msg, dict):
            role = msg.get("role")
            content = msg.get("content", "")
            function_calls = msg.get("function_calls", [])
            
            if role == "tool":
                part = types.Part.from_function_response(
                    name=msg.get("name"),
                    response={"result": content}
                )
                gemini_contents.append(types.Content(role="user", parts=[part]))
                continue
            elif function_calls:
                for call in function_calls:
                    part = types.Part.from_function_call(
                        name=call["name"],
                        args=call["args"]
                    )
                    parts.append(part)
                gemini_contents.append(types.Content(role="model", parts=parts))
                continue
            else:
                gemini_role = "model" if role in ("ai", "assistant", "model") else "user"
                parts.append(types.Part.from_text(text=content))
                gemini_contents.append(types.Content(role=gemini_role, parts=parts))
        
        # 2. Handle LangChain message objects (HumanMessage, AIMessage, ToolMessage)
        else:
            msg_type = getattr(msg, "type", "")
            content = getattr(msg, "content", "")
            
            if msg_type == "tool":
                part = types.Part.from_function_response(
                    name=getattr(msg, "name", ""),
                    response={"result": content}
                )
                gemini_contents.append(types.Content(role="user", parts=[part]))
                continue
            elif msg_type == "ai":
                # Check for tool/function calls in AIMessage
                tool_calls = getattr(msg, "tool_calls", [])
                if tool_calls:
                    for tc in tool_calls:
                        part = types.Part.from_function_call(
                            name=tc["name"],
                            args=tc["args"]
                        )
                        parts.append(part)
                    gemini_contents.append(types.Content(role="model", parts=parts))
                else:
                    parts.append(types.Part.from_text(text=content))
                    gemini_contents.append(types.Content(role="model", parts=parts))
                continue
            else:
                # human or other types
                parts.append(types.Part.from_text(text=content))
                gemini_contents.append(types.Content(role="user", parts=parts))
            
    return gemini_contents

# --- Nodes ---

def reasoner(state: AgentState):
    """
    Main thinking node. Decides if a tool is needed, calculates confidence,
    and returns thoughts or function calls.
    """
    # 1. Initialize logs and iterations if not present
    logs = state.get("logs") or []
    iterations = state.get("iterations", 0)
    ticket_id = state.get("ticket_id")
    
    # 2. Prevent infinite loops (guardrail)
    if iterations >= 5:
        logs.append({
            "timestamp": datetime.now().isoformat(),
            "type": "thought",
            "message": "Iteration limit reached. Forcing final resolution."
        })
        system_instruction = (
            "System Notice: You have hit the limit of 5 tool cycles. "
            "Do not call any more tools. Summarize your findings and formulate the final response."
        )
        return {
            "messages": [{"role": "user", "content": system_instruction}],
            "logs": logs,
            "iterations": iterations
        }
        
    # 3. Compile instructions for Gemini
    system_instruction = (
        "You are ResolveAI, an autonomous IT/Customer Support Agent. "
        "Your task is to resolve the user's support ticket efficiently and safely.\n\n"
        "Instructions:\n"
        "1. First, search for user accounts or order histories to understand the customer context.\n"
        "2. If you need knowledge, search the knowledge base.\n"
        "3. You must state your current thought in natural language (prefixed with 'Thought:') "
        "before performing any tool calls or responses.\n"
        "4. Carefully check IDs: all account actions require the format USR-XXXX. If the user provided "
        "a malformed ID or name, try to look up or fix it. If the tool returns an error, self-correct.\n"
        "5. Estimate your internal confidence score (0-100) for resolving this issue.\n"
        "6. Do not perform sensitive actions like unlocking accounts or issuing refunds > $20 "
        "without administrative approval. Choose the tool, and the system will automatically handle "
        "approval routing."
    )
    
    # 4. Invoke Gemini client
    # Retrieve dynamic API key if saved in thread config (passed via state or FastAPI app)
    # We will pass it in the thread configuration
    client = get_gemini_client()
    
    # Prepare contents history
    gemini_contents = convert_messages_to_gemini(state["messages"])
    
    from google.genai import types
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=GEMINI_TOOLS,
        temperature=0.1
    )
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=gemini_contents,
        config=config
    )
    
    # Parse output candidate safely
    candidate = None
    if response.candidates:
        candidate = response.candidates[0]
        
    model_message = {"role": "ai", "content": ""}
    
    # Extract text content (Thoughts) safely
    thought_text = ""
    if candidate and candidate.content and candidate.content.parts:
        for part in candidate.content.parts:
            if part.text:
                thought_text += part.text
                
    if thought_text:
        model_message["content"] = thought_text
        logs.append({
            "timestamp": datetime.now().isoformat(),
            "type": "thought",
            "message": thought_text.strip()
        })
        
    # Extract function calls
    function_calls = []
    if response.function_calls:
        for call in response.function_calls:
            function_calls.append({
                "name": call.name,
                "args": call.args
            })
        model_message["function_calls"] = function_calls
        
        # Log tool selection
        for fc in function_calls:
            logs.append({
                "timestamp": datetime.now().isoformat(),
                "type": "action",
                "message": f"Decided to call Tool '{fc['name']}' with arguments: {fc['args']}"
            })
            
    # Estimate confidence score (simple heuristic or LLM-extracted, default to 85)
    # Since we want to display it, we'll try to find a number in the thought or default to 90.
    confidence = 90
    for line in thought_text.split("\n"):
        if "confidence" in line.lower():
            nums = [int(s) for s in line.split() if s.isdigit()]
            if nums:
                confidence = min(100, max(0, nums[0]))
                break
                
    # Update SQLite ticket logs for live UI tracking
    execute_db(
        "UPDATE tickets SET logs = ?, status = 'OPEN' WHERE ticket_id = ?",
        (json.dumps(logs), ticket_id)
    )
    
    return {
        "messages": [model_message],
        "logs": logs,
        "confidence_score": confidence,
        "iterations": iterations
    }

def pause_node(state: AgentState):
    """
    Pause node. This serves as the target of interrupt_before.
    When we resume here, we will look at action_approved:
    - If approved: We clear pending_action and proceed to executor.
    - If rejected: We clear pending_action, append a system/user notification message, and route back to reasoner.
    """
    logs = state.get("logs") or []
    ticket_id = state.get("ticket_id")
    
    # Check if approved or rejected
    approved = state.get("action_approved")
    rejected_reason = state.get("action_rejected_reason", "No reason provided.")
    pending = state.get("pending_action")
    
    if approved is True:
        logs.append({
            "timestamp": datetime.now().isoformat(),
            "type": "thought",
            "message": f"🔒 Action Approved by Admin: Proceeding with {pending.get('name')}."
        })
        execute_db(
            "UPDATE tickets SET status = 'OPEN', logs = ? WHERE ticket_id = ?",
            (json.dumps(logs), ticket_id)
        )
        return {
            "logs": logs
        }
    elif approved is False:
        # Rejected! Inject rejection message
        logs.append({
            "timestamp": datetime.now().isoformat(),
            "type": "thought",
            "message": f"❌ Action REJECTED by Admin: {rejected_reason}. Re-evaluating."
        })
        feedback_msg = {
            "role": "user",
            "content": f"System Alert: Admin rejected your request to execute '{pending.get('name')}'. Reason: {rejected_reason}. Choose an alternative action."
        }
        execute_db(
            "UPDATE tickets SET status = 'OPEN', logs = ? WHERE ticket_id = ?",
            (json.dumps(logs), ticket_id)
        )
        return {
            "messages": [feedback_msg],
            "pending_action": None,
            "action_approved": None,
            "logs": logs
        }
        
    return state

def executor(state: AgentState):
    """
    Runs the tool calls from the last message in state,
    and appends observation messages to the state.
    """
    logs = state.get("logs") or []
    ticket_id = state.get("ticket_id")
    
    # Extract tool calls from the last assistant message
    last_msg = state["messages"][-1]
    tool_messages = []
    
    # Extract tool calls safely depending on type
    tool_calls = []
    if isinstance(last_msg, dict):
        tool_calls = last_msg.get("function_calls", [])
    else:
        tool_calls = getattr(last_msg, "tool_calls", [])
    
    if tool_calls:
        for tc in tool_calls:
            name = tc["name"]
            args = tc["args"]
            
            # Execute tool
            observation = run_tool_by_name(name, args)
            
            # Add to state messages
            tool_messages.append({
                "role": "tool",
                "name": name,
                "content": observation
            })
            
            # Add to logs
            logs.append({
                "timestamp": datetime.now().isoformat(),
                "type": "observation",
                "message": f"Observation from '{name}': {observation}"
            })
            
    # If the tool call was approved, we reset the approval states
    execute_db(
        "UPDATE tickets SET logs = ? WHERE ticket_id = ?",
        (json.dumps(logs), ticket_id)
    )
    
    return {
        "messages": tool_messages,
        "logs": logs,
        "iterations": state.get("iterations", 0) + 1,
        "pending_action": None,
        "action_approved": None
    }

def responder(state: AgentState):
    """
    Final node. Asks Gemini to generate a structured JSON response
    compliant with our FinalResolution Pydantic schema.
    """
    logs = state.get("logs") or []
    ticket_id = state.get("ticket_id")
    
    client = get_gemini_client()
    
    # 1. Request structured JSON from Gemini using the schema
    gemini_contents = convert_messages_to_gemini(state["messages"])
    
    from google.genai import types
    config = types.GenerateContentConfig(
        system_instruction=(
            "Based on the conversation history and actions taken, generate the final ticket resolution "
            "in strict JSON format conforming to the requested schema. Ensure status is RESOLVED, REJECTED, "
            "or ESCALATED."
        ),
        response_mime_type="application/json",
        response_schema=FinalResolution,
        temperature=0.1
    )
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=gemini_contents,
        config=config
    )
    
    # Parse resolution details safely
    resolution_text = ""
    try:
        resolution_text = response.text or "{}"
        resolution_data = json.loads(resolution_text)
    except Exception:
        resolution_data = {
            "status": "ESCALATED",
            "action_taken": "Safety filter block or API connection issue occurred.",
            "needs_human": True,
            "resolution_summary": "I was unable to complete this query automatically due to a safety check or connection error. I have escalated this ticket to a human manager."
        }
        resolution_text = json.dumps(resolution_data)
        
    # Log the final completion
    logs.append({
        "timestamp": datetime.now().isoformat(),
        "type": "thought",
        "message": f"Resolution Formulated. Status: {resolution_data.get('status')}. Summary: {resolution_data.get('resolution_summary')}"
    })
    
    # Write to SQL DB
    execute_db(
        "UPDATE tickets SET status = ?, logs = ? WHERE ticket_id = ?",
        (resolution_data.get("status", "ESCALATED"), json.dumps(logs), ticket_id)
    )
    
    # Append structured output back into the message history
    model_response = {
        "role": "ai",
        "content": resolution_text  # The JSON string
    }
    
    return {
        "messages": [model_response],
        "logs": logs
    }

# --- Conditional Edge Functions ---

def route_after_reasoner(state: AgentState):
    """
    Routes the agent after the reasoner:
    - If no tool calls: go to responder
    - If tool calls exist: check if they contain a sensitive action requiring HITL
    """
    last_msg = state["messages"][-1]
    
    tool_calls = []
    if isinstance(last_msg, dict):
        tool_calls = last_msg.get("function_calls", [])
    else:
        tool_calls = getattr(last_msg, "tool_calls", [])
        
    if not tool_calls:
        return "respond"
        
    # Check for sensitive actions
    for fc in tool_calls:
        name = fc["name"]
        args = fc["args"]
        
        is_sensitive = False
        reason = ""
        
        if name == "unlock_user_account":
            is_sensitive = True
            reason = "Unlocking customer accounts is a security-sensitive action."
        elif name == "issue_refund":
            amount = args.get("amount", 0.0)
            if amount > 20.0:
                is_sensitive = True
                reason = f"Refunding ${amount:.2f} exceeds the autonomous threshold of $20.00."
                
        if is_sensitive:
            # If the admin has already approved this, we don't need to pause again!
            if state.get("action_approved") is True:
                continue
                
            # Otherwise, we pause!
            # Record details of the pending action in state
            state["pending_action"] = {
                "name": name,
                "args": args,
                "reason": reason
            }
            # Set ticket status in DB to PENDING_APPROVAL
            execute_db(
                "UPDATE tickets SET status = 'PENDING_APPROVAL' WHERE ticket_id = ?",
                (state["ticket_id"],)
            )
            # Log the pause
            logs = state.get("logs") or []
            logs.append({
                "timestamp": datetime.now().isoformat(),
                "type": "thought",
                "message": f"⏸️ Sensitive Action Intercepted ({name}). Awaiting human approval..."
            })
            execute_db(
                "UPDATE tickets SET logs = ? WHERE ticket_id = ?",
                (json.dumps(logs), state["ticket_id"])
            )
            
            # Route to pause
            return "pause"
            
    # All actions standard or pre-approved
    return "execute"

def route_after_pause(state: AgentState):
    """
    Routes the agent after pause node:
    - If action was approved: go to execute
    - If action was rejected: go back to reasoner to find an alternative
    """
    if state.get("action_approved") is True:
        return "execute"
    else:
        return "reason"

# --- Graph Construction ---

workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("reasoner", reasoner)
workflow.add_node("pause_node", pause_node)
workflow.add_node("executor", executor)
workflow.add_node("responder", responder)

# Set Entrance
workflow.add_edge(START, "reasoner")

# Add Conditional Edges
workflow.add_conditional_edges(
    "reasoner",
    route_after_reasoner,
    {
        "execute": "executor",
        "pause": "pause_node",
        "respond": "responder"
    }
)

workflow.add_conditional_edges(
    "pause_node",
    route_after_pause,
    {
        "execute": "executor",
        "reason": "reasoner"
    }
)

# Connect Executor back to Reasoner
workflow.add_edge("executor", "reasoner")
workflow.add_edge("responder", END)

# Compile Graph with checkpointer
# We interrupt before entering the pause_node!
# This gives the API a clean hook to catch the state before execution
checkpointer = MemorySaver()
graph = workflow.compile(checkpointer=checkpointer, interrupt_before=["pause_node"])
