# ResolveAI

ResolveAI is an autonomous IT and Customer Support Agent designed to streamline issue resolution using AI-driven agents.

## Project Structure

The project is structured into two main parts:

- **`backend/`**: A Python FastAPI backend that powers the autonomous agents using LangGraph. It includes tools, an SQLite database for persistence, and human-in-the-loop approvals.
- **`frontend/`**: A Next.js based web application providing a user interface to interact with the agents.

## Getting Started

### Backend Setup

1. Navigate to the `backend` directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment (recommended).
3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set up your environment variables (create a `.env` file and add necessary API keys).
5. Start the FastAPI server:
   ```bash
   uvicorn app:app --reload
   ```

### Frontend Setup

1. Navigate to the `frontend` directory:
   ```bash
   cd frontend
   ```
2. Install the dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```

## Architecture Overview

ResolveAI utilizes a ReAct loop with guardrails to ensure safe and deterministic agent interactions, maintaining full traces of agent execution for auditability.
