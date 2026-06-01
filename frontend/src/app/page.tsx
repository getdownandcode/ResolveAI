"use client";

import { useState, useEffect, useRef } from "react";
import {
  Sparkles,
  Database,
  Inbox,
  Send,
  Check,
  X,
  Settings,
  Key,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  ChevronRight,
  User,
  Bot
} from "lucide-react";
import "./dashboard.css";

const BACKEND_URL = "http://127.0.0.1:8000";

// Pre-configured Scenarios
const DEMO_SCENARIOS = [
  {
    id: "lockout-points",
    title: "Locked Account & Missing Points",
    shortDesc: "Alice Smith (USR-1001) is locked out & missing 150 points.",
    tag: "Account Lock",
    titleText: "Unlock Alice Smith (USR-1001) and credit points",
    description: "Customer Alice Smith (ID: USR-1001) contacted support. Her account status is currently LOCKED. She also noticed that she was never credited the 150 loyalty points from her order #201 from last week. Please unlock her account and add the missing 150 loyalty points to her profile. Send her an email confirming everything is resolved."
  },
  {
    id: "large-refund",
    title: "Refund > $20 (Bob)",
    shortDesc: "Bob Johnson (USR-1002) wants $85.00 refund (HITL trigger).",
    tag: "Admin Approval",
    titleText: "Process Bob Johnson (USR-1002) refund for $85.00",
    description: "Bob Johnson (USR-1002) is requesting a full refund of $85.00 for order #202 (Ergonomic Office Chair). He says it arrived with a cracked armrest. Verify his order details in the database and issue a refund of $85.00. Send him a confirmation email when done. (Refund > $20 should pause for approval!)."
  },
  {
    id: "small-refund",
    title: "Autonomous Refund (Charlie)",
    shortDesc: "Charlie Brown (USR-1003) wants $12.00 refund (Auto-approved).",
    tag: "Auto Refund",
    titleText: "Process Charlie Brown (USR-1003) refund for $12.00",
    description: "Charlie Brown (USR-1003) wants a refund of $12.00 for order #204 (Leather Cable Organizer) because he doesn't need it. Check his order, refund the $12.00, and send him an email. (This should run autonomously because it's <= $20!)."
  },
  {
    id: "rag-query",
    title: "Policy Query (Diana)",
    shortDesc: "Diana Prince (USR-1004) asks return policy (RAG lookup).",
    tag: "Policy Lookup",
    titleText: "Answer return policy question for Diana Prince",
    description: "Diana Prince (USR-1004) is asking: 'What is your return policy for international orders? Also, how long do refunds take to process?' Search the knowledge base and respond to her."
  },
  {
    id: "self-correction",
    title: "ID Form Self-Correction",
    shortDesc: "Agent handles malformed ID inputs by self-correction.",
    tag: "Self-Correction",
    titleText: "Retrieve points for customer with invalid ID format",
    description: "A customer named Alice Smith wants to check her profile. She provided her user ID as 'alice-smith-1001-profile' instead of the standard format. Query the database using her info, handle any format errors, find her correct account details, and report her point balance."
  }
];

interface Log {
  type: string;
  timestamp: string;
  message: string;
}

interface TicketDetails {
  ticket_id: string;
  title: string;
  status: string;
  description: string;
  confidence_score?: number;
  is_paused?: boolean;
  pending_action?: {
    name: string;
    args: Record<string, unknown>;
    reason: string;
  };
  final_resolution?: {
    status: string;
    action_taken: string;
    needs_human: boolean;
    resolution_summary: string;
  };
  logs: Log[];
}

interface User {
  user_id: string;
  name: string;
  status: string;
  loyalty_points: number;
}

interface Order {
  order_id: string;
  user_id: string;
  item_name: string;
  price: number;
  status: string;
}

interface Email {
  email_id: string;
  user_id: string;
  recipient: string;
  subject: string;
  body: string;
  sent_at: string;
}

interface Ticket {
  ticket_id: string;
  title: string;
  status: string;
}

interface DbSnapshot {
  users: User[];
  orders: Order[];
  emails: Email[];
  tickets: Ticket[];
}

export default function Home() {
  const [mounted, setMounted] = useState(false);
  const [apiKey, setApiKey] = useState<string>("");
  const [showApiKeyInput, setShowApiKeyInput] = useState<boolean>(false);

  // Tickets list & selected ticket
  const [activeTicketId, setActiveTicketId] = useState<string | null>(null);
  const [ticketDetails, setTicketDetails] = useState<TicketDetails | null>(null);
  
  // Database tables snapshots
  const [dbSnapshot, setDbSnapshot] = useState<DbSnapshot>({
    users: [],
    orders: [],
    emails: [],
    tickets: []
  });
  const [activeDbTab, setActiveDbTab] = useState<string>("users");
  const [dbResetFlash, setDbResetFlash] = useState(false);

  // Form Inputs
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null);
  const [customTitle, setCustomTitle] = useState("");
  const [customDesc, setCustomDesc] = useState("");

  // HITL state inputs
  const [rejectionReason, setRejectionReason] = useState("");
  
  // View mode for center panel: "trace" (ReAct graph logs) or "chat" (final message layout)
  const [centerViewMode, setCenterViewMode] = useState<"trace" | "chat">("trace");

  // Loading indicator states
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isHITLWorking, setIsHITLWorking] = useState(false);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [isOnline, setIsOnline] = useState(true);

  // Scroll ref for logs
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Fetch Database Snapshot (Declared above useEffect hooks to prevent accessed-before-declaration)
  const fetchDatabaseSnapshot = async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/database`);
      if (res.ok) {
        const data = await res.json() as DbSnapshot;
        setDbSnapshot(data);
        setBackendError(null);
        setIsOnline(true);
      } else {
        setIsOnline(false);
        setBackendError("Failed to fetch database snapshot from backend API.");
      }
    } catch {
      setIsOnline(false);
      setBackendError("Backend API is offline. Please start the FastAPI backend server on port 8000.");
    }
  };

  // Fetch Ticket Details
  const fetchTicketDetails = async (id: string, callback?: (data: TicketDetails) => void) => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/tickets/${id}`);
      if (res.ok) {
        const data = await res.json() as TicketDetails;
        setTicketDetails(data);
        setIsOnline(true);
        if (callback) callback(data);
      } else {
        setIsOnline(false);
        setBackendError("Failed to load ticket details from backend API.");
      }
    } catch {
      setIsOnline(false);
      setBackendError("Backend API is offline. Please start the FastAPI backend server on port 8000.");
    }
  };

  // Load API Key from local storage on mount
  useEffect(() => {
    const savedKey = localStorage.getItem("resolve_ai_gemini_key");
    if (savedKey) {
      setApiKey(savedKey);
    } else {
      setShowApiKeyInput(true);
    }
    setTimeout(() => {
      setMounted(true);
    }, 0);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchDatabaseSnapshot();
  }, []);

  // Save API Key to local storage
  const handleSaveApiKey = (key: string) => {
    setApiKey(key);
    localStorage.setItem("resolve_ai_gemini_key", key);
    setShowApiKeyInput(false);
  };

  // Poll ticket details and DB snapshots if agent is actively running
  useEffect(() => {
    if (!activeTicketId || !isOnline) return;

    // Direct initial fetch
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchTicketDetails(activeTicketId);
    void fetchDatabaseSnapshot();

    const interval = setInterval(() => {
      fetchTicketDetails(activeTicketId, (data) => {
        // If ticket completed, we stop polling
        if (data.status === "RESOLVED" || data.status === "REJECTED" || (data.status === "OPEN" && !data.is_paused && data.logs && data.logs.length > 0 && data.logs[data.logs.length - 1].message.includes("Resolution Formulated"))) {
          clearInterval(interval);
        }
      });
      fetchDatabaseSnapshot();
    }, 1000);

    return () => clearInterval(interval);
  }, [activeTicketId, isOnline]);

  // Scroll to bottom of agent logs whenever they change
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [ticketDetails?.logs]);

  // Reconnect Helper
  const handleReconnect = async () => {
    setBackendError(null);
    try {
      const res = await fetch(`${BACKEND_URL}/api/database`);
      if (res.ok) {
        setIsOnline(true);
        const data = await res.json() as DbSnapshot;
        setDbSnapshot(data);
        if (activeTicketId) {
          fetchTicketDetails(activeTicketId);
        }
      }
    } catch {
      setIsOnline(false);
      setBackendError("Connection failed. Please ensure the FastAPI backend is running on http://127.0.0.1:8000");
    }
  };

  // Reset Mock Database snapshot
  const handleResetDatabase = async () => {
    if (!isOnline) {
      setBackendError("Cannot reset database while backend is offline.");
      return;
    }
    try {
      const res = await fetch(`${BACKEND_URL}/api/database/reset`, { method: "POST" });
      if (res.ok) {
        fetchDatabaseSnapshot();
        setDbResetFlash(true);
        setTimeout(() => setDbResetFlash(false), 2000);
      }
    } catch {
      setIsOnline(false);
      setBackendError("Failed to reset database. Connection lost.");
    }
  };

  // Submit Support Ticket
  const handleSubmitTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    setBackendError(null);

    let title = customTitle;
    let description = customDesc;

    // Use selected scenario if applicable
    if (selectedScenarioId) {
      const scenario = DEMO_SCENARIOS.find(s => s.id === selectedScenarioId);
      if (scenario) {
        title = scenario.titleText;
        description = scenario.description;
      }
    }

    if (!description.trim()) return;

    setIsSubmitting(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/tickets`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-KEY": apiKey
        },
        body: JSON.stringify({ title: title || "Support Ticket", description })
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to launch agent");
      }

      const data = await res.json();
      setActiveTicketId(data.ticket_id);
      setSelectedScenarioId(null);
      setCustomTitle("");
      setCustomDesc("");
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : "Failed to start agent. Please ensure FastAPI is running.";
      setBackendError(errMsg);
    } finally {
      setIsSubmitting(false);
    }
  };

  // HITL: Approve Action
  const handleApproveAction = async () => {
    if (!activeTicketId) return;
    setIsHITLWorking(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/tickets/${activeTicketId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ apiKey })
      });
      if (res.ok) {
        fetchTicketDetails(activeTicketId);
      } else {
        setIsOnline(false);
        setBackendError("Failed to approve action. Server response error.");
      }
    } catch {
      setIsOnline(false);
      setBackendError("Failed to approve action. Connection lost.");
    } finally {
      setIsHITLWorking(false);
    }
  };

  // HITL: Reject Action
  const handleRejectAction = async () => {
    if (!activeTicketId || !rejectionReason.trim()) return;
    setIsHITLWorking(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/tickets/${activeTicketId}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: rejectionReason, apiKey })
      });
      if (res.ok) {
        setRejectionReason("");
        fetchTicketDetails(activeTicketId);
      } else {
        setIsOnline(false);
        setBackendError("Failed to reject action. Server response error.");
      }
    } catch {
      setIsOnline(false);
      setBackendError("Failed to reject action. Connection lost.");
    } finally {
      setIsHITLWorking(false);
    }
  };

  // Load a scenario into input fields
  const handleSelectScenario = (id: string) => {
    setSelectedScenarioId(id);
    const scenario = DEMO_SCENARIOS.find(s => s.id === id);
    if (scenario) {
      setCustomTitle(scenario.titleText);
      setCustomDesc(scenario.description);
    }
  };

  return (
    <div className="flex flex-col min-h-screen">
      {/* Navbar Header */}
      <header className="navbar">
        <div className="logo-section">
          <Sparkles size={18} className="text-primary" />
          <div>
            <h1>ResolveAI</h1>
            <span className="system-title">Multi-Agent Support Gateway</span>
          </div>
        </div>

        <div className="settings-section">
          {/* Active indicator */}
          <div className="status-badge">
            <span className={`indicator-dot ${ticketDetails?.is_paused ? "paused" : activeTicketId && ticketDetails?.status === "OPEN" ? "active" : "idle"}`} />
            <span>
              {ticketDetails?.is_paused ? "Awaiting Approval" : activeTicketId && ticketDetails?.status === "OPEN" ? "Agent Running" : "System Idle"}
            </span>
          </div>

          <button
            className="btn-secondary"
            onClick={() => setShowApiKeyInput(!showApiKeyInput)}
          >
            <Settings size={14} className={showApiKeyInput ? "spin" : ""} />
            <span>{!mounted ? "Enter Gemini Key" : apiKey ? "Gemini Key Active" : "Enter Gemini Key"}</span>
          </button>
        </div>
      </header>

      {/* Backend offline warning banner */}
      {backendError && (
        <div className="alert-bar animate-fadeIn">
          <AlertTriangle size={16} className="text-accent shrink-0" />
          <p className="flex-1 font-medium">{backendError}</p>
          {!isOnline && (
            <button 
              onClick={handleReconnect}
              className="btn-secondary"
              style={{ padding: "4px 8px", borderRadius: "6px", fontSize: "11px" }}
            >
              <RefreshCw size={10} className="spinner" />
              Reconnect Gateway
            </button>
          )}
          <button onClick={() => setBackendError(null)} className="text-secondary hover:text-white font-bold px-2" style={{ background: 'none', border: 'none', cursor: 'pointer' }}>✕</button>
        </div>
      )}

      {/* API Key Modal Drawer */}
      {mounted && showApiKeyInput && (
        <div className="modal-drawer animate-fadeIn">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg text-primary" style={{ background: 'rgba(10, 132, 255, 0.1)' }}>
              <Key size={18} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white">Gemini API Key Required</h3>
              <p className="text-muted" style={{ fontSize: '13px' }}>Please provide a Google Gemini API Key. It is only stored locally in your browser.</p>
            </div>
          </div>
          <div className="flex-1 flex gap-2">
            <input
              type="password"
              placeholder="AIzaSy..."
              className="form-input flex-1"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
            <button
              onClick={() => handleSaveApiKey(apiKey)}
              className="btn-primary"
              disabled={!apiKey}
            >
              Save Configuration
            </button>
          </div>
        </div>
      )}

      {/* Dashboard Three-Panel Layout */}
      <main className="dashboard flex-1">
        
        {/* Left Column: Launcher */}
        <section className="panel">
          <div className="panel-header">
            <h2 className="panel-title">
              <Inbox size={16} className="text-secondary" />
              <span>Launch Support Ticket</span>
            </h2>
          </div>

          <div className="panel-body flex flex-col gap-4">
            {/* Scenario selector */}
            <div>
              <span className="system-title">Preset Demo Scenarios</span>
              {DEMO_SCENARIOS.map((scenario) => (
                <div
                  key={scenario.id}
                  className={`scenario-card ${selectedScenarioId === scenario.id ? "active" : ""}`}
                  onClick={() => handleSelectScenario(scenario.id)}
                >
                  <div className="flex justify-between items-center gap-2">
                    <span className="scenario-tag">{scenario.tag}</span>
                    <ChevronRight size={12} className="text-muted" />
                  </div>
                  <h4>{scenario.title}</h4>
                  <p>{scenario.shortDesc}</p>
                </div>
              ))}
            </div>

            <div style={{ borderTop: '1px solid var(--border-color)', margin: '8px 0' }} />

            {/* Custom ticket input */}
            <form onSubmit={handleSubmitTicket} className="custom-ticket-form flex-1 flex flex-col">
              <span className="system-title">Ticket Prompt</span>
              
              <input
                type="text"
                placeholder="Ticket Title (e.g. Broken headphone query)"
                className="form-input"
                value={customTitle}
                onChange={(e) => {
                  setCustomTitle(e.target.value);
                  setSelectedScenarioId(null);
                }}
              />

              <textarea
                placeholder="Describe the customer's request here..."
                rows={5}
                className="form-input flex-1 resize-none"
                style={{ minHeight: '120px' }}
                value={customDesc}
                onChange={(e) => {
                  setCustomDesc(e.target.value);
                  setSelectedScenarioId(null);
                }}
                required
              />

              <button
                type="submit"
                className="btn-primary w-full flex justify-center items-center gap-2"
                style={{ justifyContent: 'center' }}
                disabled={isSubmitting || !customDesc.trim()}
              >
                {isSubmitting ? (
                  <>
                    <RefreshCw size={14} className="spin" />
                    <span>Launching Agent...</span>
                  </>
                ) : (
                  <>
                    <Send size={14} />
                    <span>Run ResolveAI Agent</span>
                  </>
                )}
              </button>
            </form>
          </div>
        </section>

        {/* Center Column: Live Agent Trace Visualizer */}
        <section className="panel">
          <div className="panel-header">
            <h2 className="panel-title">
              <Sparkles size={16} className="text-secondary" />
              <span>Live Agentic Execution</span>
              {activeTicketId && (
                <span className="badge badge-open font-mono ml-2">
                  {activeTicketId}
                </span>
              )}
            </h2>

            {/* View Mode selector */}
            <div className="segmented-control">
              <button
                onClick={() => setCenterViewMode("trace")}
                className={`segmented-control-btn ${centerViewMode === "trace" ? "active" : ""}`}
              >
                Trace Logs
              </button>
              <button
                onClick={() => setCenterViewMode("chat")}
                className={`segmented-control-btn ${centerViewMode === "chat" ? "active" : ""}`}
              >
                Customer Chat
              </button>
            </div>
          </div>

          <div className="panel-body">
            {!activeTicketId ? (
              <div className="flex-1 flex flex-col justify-center items-center text-center p-8" style={{ minHeight: '300px' }}>
                <Bot size={40} className="text-muted" style={{ marginBottom: '16px' }} />
                <h3 className="font-semibold text-secondary">No Active Agent Execution</h3>
                <p className="text-muted" style={{ marginTop: '8px', maxWidth: '300px', fontSize: '0.9rem', lineHeight: '1.5' }}>Select a preset demo scenario on the left or enter a ticket description to spin up an autonomous LangGraph agent.</p>
              </div>
            ) : (
              <div className="flex-1 flex flex-col">
                {/* Visual state headers */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '14px', marginBottom: '18px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="text-muted" style={{ fontSize: '0.88rem' }}>Status:</span>
                    <span className={`badge ${
                      ticketDetails?.status === "OPEN" && ticketDetails?.is_paused ? "badge-pending" :
                      ticketDetails?.status === "OPEN" ? "badge-open" :
                      ticketDetails?.status === "RESOLVED" ? "badge-resolved" : "badge-rejected"
                    }`}>
                      {ticketDetails?.status === "OPEN" && ticketDetails?.is_paused ? "PENDING APPROVAL" : ticketDetails?.status}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className="text-muted" style={{ fontSize: '0.88rem' }}>Confidence:</span>
                    <span className={`font-mono text-sm font-semibold ${
                      (ticketDetails?.confidence_score || 90) >= 80 ? "text-success" : "text-accent"
                    }`}>
                      {ticketDetails?.confidence_score || 90}%
                    </span>
                  </div>
                </div>

                {/* View 1: Trace Timeline (Thought -> Action -> Observation) */}
                {centerViewMode === "trace" && (
                  <div className="flex-1 flex flex-col justify-between">
                    <div className="trace-timeline" style={{ flex: 1 }}>
                      {ticketDetails?.logs && ticketDetails.logs.length > 0 ? (
                        ticketDetails.logs.map((log: Log, idx: number) => (
                          <div key={idx} className="trace-step">
                            <span className={`trace-dot ${log.type}`} />
                            <div className="trace-header">
                              <span className={`trace-label ${log.type}`}>{log.type}</span>
                              <span className="font-mono text-muted" style={{ fontSize: '0.8rem' }}>
                                {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                              </span>
                            </div>
                            <div className="trace-body">{log.message}</div>
                          </div>
                        ))
                      ) : (
                        <div className="text-muted" style={{ fontStyle: 'italic', padding: '16px 0' }}>Initializing state logs...</div>
                      )}
                      
                      {/* Active running loading node */}
                      {activeTicketId && ticketDetails?.status === "OPEN" && !ticketDetails?.is_paused && (
                        <div className="trace-step">
                          <span className="trace-dot">
                            <span className="animate-pulse absolute inset-0 rounded-full bg-primary" style={{ display: 'block', width: '100%', height: '100%' }}></span>
                          </span>
                          <div className="trace-header">
                            <span className="trace-label text-primary" style={{ fontStyle: 'italic' }}>ResolveAI is reasoning...</span>
                          </div>
                          <div className="trace-body" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <RefreshCw size={13} className="spin text-primary" />
                            <span>Thinking, querying databases or evaluating tools...</span>
                          </div>
                        </div>
                      )}
                      
                      <div ref={logsEndRef} />
                    </div>

                    {/* Final Resolution structure visualizer */}
                    {ticketDetails?.final_resolution && (
                      <div className="resolution-card">
                        <div className="resolution-title">
                          <CheckCircle size={16} className="text-success" />
                          <span>Structured Resolution Reached</span>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                          <div className="resolution-field">
                            <span className="resolution-field-label">Status:</span>{" "}
                            <span className="badge badge-resolved font-mono">{ticketDetails.final_resolution?.status}</span>
                          </div>
                          <div className="resolution-field">
                            <span className="resolution-field-label">Action Taken:</span>{" "}
                            <span className="text-white">{ticketDetails.final_resolution?.action_taken}</span>
                          </div>
                          <div className="resolution-field">
                            <span className="resolution-field-label">Needs Escalation:</span>{" "}
                            <span className={`font-mono font-semibold ${ticketDetails.final_resolution?.needs_human ? "text-accent" : "text-success"}`}>
                              {ticketDetails.final_resolution?.needs_human ? "YES ⚠️" : "NO ✓"}
                            </span>
                          </div>
                          <div style={{ borderTop: '1px solid var(--border-color)', marginTop: '12px', paddingTop: '12px' }}>
                            <span className="system-title" style={{ marginBottom: '8px' }}>Message to Customer</span>
                            <div className="resolution-summary">
                              {ticketDetails.final_resolution?.resolution_summary}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* View 2: Customer Conversation Mock Chat View */}
                {centerViewMode === "chat" && (
                  <div className="flex-1 flex flex-col justify-between gap-4">
                    <div className="chat-thread" style={{ overflowY: 'auto', maxHeight: '480px' }}>
                      {/* Ticket Description as User initial message */}
                      <div className="chat-bubble-container">
                        <div className="chat-bubble-label">
                          <User size={12} />
                          <span>Customer Ticket</span>
                        </div>
                        <div className="chat-bubble user">
                          <p>{ticketDetails?.description}</p>
                        </div>
                      </div>

                      {/* Emails sent mapped as Agent interactions */}
                      {dbSnapshot.emails
                        .filter((e: Email) => e.user_id && ticketDetails?.description?.includes(e.user_id))
                        .map((email: Email) => (
                          <div key={email.email_id} className="chat-bubble-container" style={{ alignItems: 'flex-end' }}>
                            <div className="chat-bubble-label text-primary">
                              <Bot size={12} />
                              <span>Official Email Sent</span>
                            </div>
                            <div className="chat-bubble agent">
                              <strong style={{ display: 'block', fontSize: '0.94rem', marginBottom: '6px' }}>Subject: {email.subject}</strong>
                              <p style={{ whiteSpace: 'pre-wrap', opacity: 0.9 }}>{email.body}</p>
                            </div>
                          </div>
                        ))}

                      {/* Agent Final Output if ticket resolved */}
                      {ticketDetails?.final_resolution && (
                        <div className="chat-bubble-container" style={{ alignItems: 'flex-end' }}>
                          <div className="chat-bubble-label text-primary">
                            <Bot size={12} />
                            <span>ResolveAI Final Resolution</span>
                          </div>
                          <div className="chat-bubble agent">
                            <p>{ticketDetails.final_resolution.resolution_summary}</p>
                            <div className="badge badge-active font-mono" style={{ marginTop: '12px', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', background: 'rgba(255,255,255,0.1)' }}>
                              Status: {ticketDetails.final_resolution.status}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>

        {/* Right Column: Database Snapshot & HITL approval console */}
        <section className="panel" style={{ background: 'none', border: 'none', gap: '24px' }}>
          
          {/* HITL approvals dashboard if paused */}
          {ticketDetails?.is_paused && ticketDetails?.pending_action && (
            <div className="hitl-container animate-fadeIn">
              <div className="hitl-header">
                <AlertTriangle size={18} />
                <span>Administrative Approval Requested</span>
              </div>
              <div className="hitl-body">
                <p style={{ marginBottom: '10px' }}>
                  The agent requires authorization for a sensitive transaction:
                </p>
                <div className="console-box">
                  <strong>Action:</strong> {ticketDetails.pending_action?.name}<br />
                  <strong>Arguments:</strong> {JSON.stringify(ticketDetails.pending_action?.args)}<br />
                  <strong>Reason:</strong> {ticketDetails.pending_action?.reason}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--text-muted)' }}>
                  <span>Safety Policy: Mandatory HITL</span>
                  <span>Confidence: {ticketDetails.confidence_score}%</span>
                </div>
              </div>

              {/* Notes / Feedback input */}
              <input
                type="text"
                placeholder="Authorization notes or rejection reason..."
                className="hitl-input"
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
              />

              <div className="hitl-actions">
                <button
                  onClick={handleApproveAction}
                  className="btn-success"
                  style={{ flex: 1, justifyContent: 'center' }}
                  disabled={isHITLWorking}
                >
                  {isHITLWorking ? <RefreshCw size={12} className="spin" /> : <Check size={14} />}
                  <span>Approve Action</span>
                </button>
                <button
                  onClick={handleRejectAction}
                  className="btn-danger"
                  style={{ flex: 1, justifyContent: 'center' }}
                  disabled={isHITLWorking || !rejectionReason.trim()}
                >
                  {isHITLWorking ? <RefreshCw size={12} className="spin" /> : <X size={14} />}
                  <span>Reject</span>
                </button>
              </div>
            </div>
          )}

          {/* CRM DB Browser */}
          <div className="panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div className="panel-header">
              <h2 className="panel-title">
                <Database size={16} className="text-secondary" />
                <span>CRM Live Database</span>
              </h2>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {dbResetFlash && (
                  <span className="font-mono text-success" style={{ fontSize: '11px' }}>Database Reset</span>
                )}
                <button
                  onClick={handleResetDatabase}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', color: 'var(--text-secondary)' }}
                  title="Reset Database to seed values"
                >
                  <RefreshCw size={13} />
                </button>
              </div>
            </div>

            {/* DB Tabs */}
            <div style={{ padding: '16px 20px 0 20px' }}>
              <div className="db-tabs">
                <div
                  className={`db-tab ${activeDbTab === "users" ? "active" : ""}`}
                  onClick={() => setActiveDbTab("users")}
                >
                  Users
                </div>
                <div
                  className={`db-tab ${activeDbTab === "orders" ? "active" : ""}`}
                  onClick={() => setActiveDbTab("orders")}
                >
                  Orders
                </div>
                <div
                  className={`db-tab ${activeDbTab === "emails" ? "active" : ""}`}
                  onClick={() => setActiveDbTab("emails")}
                >
                  Outbox
                </div>
                <div
                  className={`db-tab ${activeDbTab === "tickets" ? "active" : ""}`}
                  onClick={() => setActiveDbTab("tickets")}
                >
                  History
                </div>
              </div>
            </div>

            {/* DB Panel Body */}
            <div className="panel-body" style={{ paddingTop: '4px', overflowY: 'auto' }}>
              
              {/* Users Snapshot */}
              {activeDbTab === "users" && (
                <div className="db-table-container animate-fadeIn">
                  <table className="db-table">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Name</th>
                        <th>Status</th>
                        <th>Points</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dbSnapshot.users.map((u: User) => (
                        <tr key={u.user_id}>
                          <td className="font-mono text-primary">{u.user_id}</td>
                          <td>{u.name}</td>
                          <td>
                            <span className={`badge ${u.status === "ACTIVE" ? "badge-active" : "badge-locked"}`}>
                              {u.status}
                            </span>
                          </td>
                          <td className="font-mono font-semibold">{u.loyalty_points}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Orders Snapshot */}
              {activeDbTab === "orders" && (
                <div className="db-table-container animate-fadeIn">
                  <table className="db-table">
                    <thead>
                      <tr>
                        <th>Ord #</th>
                        <th>User ID</th>
                        <th>Item</th>
                        <th>Price</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dbSnapshot.orders.map((o: Order) => (
                        <tr key={o.order_id}>
                          <td className="font-mono">{o.order_id}</td>
                          <td className="font-mono text-secondary">{o.user_id}</td>
                          <td>{o.item_name}</td>
                          <td className="font-mono font-semibold">${o.price.toFixed(2)}</td>
                          <td>
                            <span className={`badge ${
                              o.status === "DELIVERED" ? "badge-active" : o.status === "REFUNDED" ? "badge-locked" : "badge-pending"
                            }`}>
                              {o.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Emails snapshot */}
              {activeDbTab === "emails" && (
                <div className="flex flex-col gap-2 animate-fadeIn">
                  {dbSnapshot.emails.length === 0 ? (
                    <div className="text-muted" style={{ fontStyle: 'italic', padding: '16px 0', textAlign: 'center' }}>No emails sent yet.</div>
                  ) : (
                    dbSnapshot.emails.map((e: Email) => (
                      <div key={e.email_id} className="email-log-item">
                        <div className="email-meta">
                          <span className="font-mono text-secondary" style={{ fontSize: '11px' }}>To: {e.recipient} ({e.user_id})</span>
                          <span>{new Date(e.sent_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                        </div>
                        <div className="email-subject">{e.subject}</div>
                        <div className="email-body">{e.body}</div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* Tickets history snapshots */}
              {activeDbTab === "tickets" && (
                <div className="db-table-container animate-fadeIn">
                  <table className="db-table">
                    <thead>
                      <tr>
                        <th>Ticket ID</th>
                        <th>Title</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dbSnapshot.tickets.map((t: Ticket) => (
                        <tr
                          key={t.ticket_id}
                          className="cursor-pointer"
                          style={{ cursor: 'pointer', background: activeTicketId === t.ticket_id ? 'rgba(10, 132, 255, 0.08)' : 'none' }}
                          onClick={() => setActiveTicketId(t.ticket_id)}
                        >
                          <td className="font-mono text-primary">{t.ticket_id}</td>
                          <td className="truncate" style={{ maxWidth: '140px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.title}</td>
                          <td>
                            <span className={`badge ${
                              t.status === "OPEN" ? "badge-open" : t.status === "RESOLVED" ? "badge-resolved" : "badge-rejected"
                            }`}>
                              {t.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

            </div>
          </div>
        </section>

      </main>
    </div>
  );
}
