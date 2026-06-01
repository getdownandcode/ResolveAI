import sqlite3
import re
from datetime import datetime
from langchain_core.tools import tool
from database import get_db_connection

# Mock Knowledge Base for RAG tool
KNOWLEDGE_BASE = {
    "returns_policy": (
        "Return Policy: Customers can return items within 30 days of delivery. "
        "Items must be in original condition. Standard return shipping is free "
        "for domestic orders. International orders must cover return shipping fees. "
        "Refunds take 5-7 business days to process once the item is received."
    ),
    "account_lock_policy": (
        "Account Lockout: Accounts are locked after 3 failed login attempts. "
        "To unlock a customer account, a support agent must execute the unlock tool. "
        "Unlock operations require administrative approval (HITL) before execution."
    ),
    "loyalty_points_policy": (
        "Loyalty Program: Members earn 1 point per $1 spent. Points can be redeemed "
        "for store credit (100 points = $10). Support agents can manually credit missing "
        "points to accounts up to a limit of 500 points per transaction. Point additions "
        "over 500 points require administrator review."
    ),
    "shipping_info": (
        "Shipping Options: Standard delivery takes 3-5 business days. Express shipping "
        "takes 1-2 business days. Free shipping is automatically applied to orders over $50."
    )
}

@tool
def search_knowledge_base(query: str) -> str:
    """
    Searches the internal company knowledge base (RAG) for return policies,
    shipping info, account lockout terms, and loyalty program rules.
    """
    # Simple semantic/keyword matcher for RAG demonstration
    query_lower = query.lower()
    matches = []
    for key, doc in KNOWLEDGE_BASE.items():
        # Check overlaps of words
        overlap_keywords = [w for w in query_lower.split() if len(w) > 3 and w in doc.lower()]
        if overlap_keywords:
            matches.append((len(overlap_keywords), doc))
            
    if not matches:
        return "No exact knowledge match found. Try searching for 'return policy', 'account lockout', 'points', or 'shipping'."
        
    # Return document with the highest overlap
    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[0][1]

@tool
def get_user_account(user_id: str) -> str:
    """
    Retrieves account profile, name, email, lockout status, and loyalty points for a user.
    Input must be a valid User ID (e.g. USR-1001).
    """
    # Self-correction check: enforce USR-XXXX format
    if not re.match(r"^USR-\d{4}$", user_id):
        # Malformed ID error to test Agent self-correction
        return (
            f"Error: Invalid User ID format '{user_id}'. Account lookups require "
            "the official format: 'USR-' followed by 4 digits, e.g., 'USR-1001'."
        )
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return f"Error: User with ID '{user_id}' was not found in the database."
        
    return (
        f"User Details:\n"
        f"- ID: {row['user_id']}\n"
        f"- Name: {row['name']}\n"
        f"- Email: {row['email']}\n"
        f"- Status: {row['status']}\n"
        f"- Loyalty Points: {row['loyalty_points']}"
    )

@tool
def add_loyalty_points(user_id: str, points: int) -> str:
    """
    Manually adds loyalty points to a user's account.
    """
    if not re.match(r"^USR-\d{4}$", user_id):
        return f"Error: Invalid User ID format. Must be USR-XXXX."
        
    if points <= 0:
        return "Error: Points must be a positive integer."
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return f"Error: User '{user_id}' not found."
        
    current_points = row['loyalty_points']
    new_points = current_points + points
    
    cursor.execute("UPDATE users SET loyalty_points = ? WHERE user_id = ?", (new_points, user_id))
    conn.commit()
    conn.close()
    
    return f"Successfully added {points} points to user {user_id}. New balance is {new_points} points."

@tool
def get_order_details(order_id: int) -> str:
    """
    Retrieves information on an order: order ID, user ID, item name, price, and shipping status.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return f"Error: Order #{order_id} not found."
        
    return (
        f"Order Details:\n"
        f"- Order ID: {row['order_id']}\n"
        f"- User ID: {row['user_id']}\n"
        f"- Item: {row['item_name']}\n"
        f"- Price: ${row['price']:.2f}\n"
        f"- Status: {row['status']}"
    )

@tool
def unlock_user_account(user_id: str) -> str:
    """
    [ADMIN] Unlocks a customer account. This is a sensitive action that requires administrative approval.
    """
    if not re.match(r"^USR-\d{4}$", user_id):
        return f"Error: Invalid User ID format. Must be USR-XXXX."
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return f"Error: User '{user_id}' not found."
        
    if row['status'] == 'ACTIVE':
        conn.close()
        return f"Account '{user_id}' is already ACTIVE."
        
    cursor.execute("UPDATE users SET status = 'ACTIVE' WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    return f"Success: Account '{user_id}' has been unlocked and status is set to ACTIVE."

@tool
def issue_refund(order_id: int, amount: float) -> str:
    """
    [ADMIN] Issues a partial or full refund for an order.
    Refunding amounts > $20 is a sensitive action requiring administrative approval.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return f"Error: Order #{order_id} not found."
        
    if row['status'] == 'REFUNDED':
        conn.close()
        return f"Error: Order #{order_id} is already REFUNDED."
        
    if amount > row['price']:
        conn.close()
        return f"Error: Refund amount ${amount:.2f} cannot exceed order total of ${row['price']:.2f}."
        
    cursor.execute("UPDATE orders SET status = 'REFUNDED' WHERE order_id = ?", (order_id,))
    conn.commit()
    conn.close()
    
    return f"Success: Issued refund of ${amount:.2f} for order #{order_id} (Status updated to REFUNDED)."

@tool
def send_support_email(user_id: str, recipient: str, subject: str, body: str) -> str:
    """
    Sends an official support email to a customer.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    sent_at = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO emails_sent (user_id, recipient, subject, body, sent_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, recipient, subject, body, sent_at)
    )
    conn.commit()
    conn.close()
    
    return f"Success: Email sent to '{recipient}' with subject '{subject}'."

@tool
def web_search(query: str) -> str:
    """
    Queries external search engines for recent information (mocked).
    """
    query_lower = query.lower()
    if "weather" in query_lower:
        return "Weather Report: Current weather in Seattle, WA is 62°F, Rain. Expected high of 65°F."
    elif "fedex" in query_lower or "tracking" in query_lower:
        return "Package Tracking Mock API: Package is currently transit. Location: Seattle Hub. Expected delivery: 1 business day."
    else:
        return f"Search result for '{query}': No exact results found online. Check shipping provider dashboards for direct queries."
