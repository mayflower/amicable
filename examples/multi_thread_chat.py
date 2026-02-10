"""
Multi-thread chat example with per-thread sandbox isolation.

This example demonstrates how to use DeepAgents with ThreadedSandboxManager
to provide isolated sandboxes for each conversation thread, with persistent
filesystems that survive across requests.

Key features:
- Each thread_id gets its own isolated sandbox
- Filesystem persists across multiple invocations with the same thread_id
- Different threads have completely separate filesystems
- LangGraph checkpointer handles message history

Usage:
    # Start a conversation in thread A
    python multi_thread_chat.py --thread thread-A --query "Create hello.txt with 'Hello from A'"

    # Continue the conversation (file persists)
    python multi_thread_chat.py --thread thread-A --query "Read hello.txt"

    # Different thread has its own sandbox
    python multi_thread_chat.py --thread thread-B --query "Read hello.txt"
    # ^ Will fail because thread-B's sandbox doesn't have hello.txt

    # Interactive mode for a specific thread
    python multi_thread_chat.py --thread thread-A

    # Delete a thread's sandbox when done
    python multi_thread_chat.py --thread thread-A --delete
"""

import argparse
import os
import sys
from datetime import timedelta

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

from src.sandbox_backends.thread_manager import ThreadedSandboxManager
from src.sandbox_backends.threaded_factory import create_threaded_backend_factory


def get_model():
    """Get the chat model based on available API keys."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model="claude-sonnet-4-20250514")

    if os.environ.get("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model="gpt-4o")

    if os.environ.get("GOOGLE_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model="gemini-1.5-pro")

    print("Error: No API key found. Set one of:")
    print("  - ANTHROPIC_API_KEY")
    print("  - OPENAI_API_KEY")
    print("  - GOOGLE_API_KEY")
    sys.exit(1)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Multi-thread chat with per-thread sandbox isolation"
    )
    parser.add_argument(
        "--thread",
        "-t",
        type=str,
        required=True,
        help="Thread ID for this conversation (required)",
    )
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        help="Single query to run (omit for interactive mode)",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete the thread's sandbox and exit",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all active threads and exit",
    )
    parser.add_argument(
        "--template",
        type=str,
        default=os.environ.get("K8S_SANDBOX_TEMPLATE_NAME", "amicable-sandbox"),
        help="SandboxTemplate name (default: amicable-sandbox)",
    )
    parser.add_argument(
        "--root-dir",
        type=str,
        default=os.environ.get("SANDBOX_ROOT_DIR", "/app"),
        help="Virtual filesystem root in sandbox (default: /app)",
    )
    parser.add_argument(
        "--idle-ttl",
        type=int,
        default=None,
        help="Idle TTL in minutes for auto-cleanup (default: no auto-cleanup)",
    )
    parser.add_argument(
        "--skills",
        type=str,
        nargs="*",
        default=[".deepagents/skills"],
        help="Skill directories to load (default: .deepagents/skills)",
    )
    return parser.parse_args()


def run_interactive(agent, thread_id: str, config: dict):
    """Run the agent in interactive mode."""
    print(f"\nMulti-Thread Chat (thread: {thread_id})")
    print("=" * 50)
    print("Your sandbox filesystem persists across messages.")
    print("Type 'quit' or 'exit' to stop.\n")

    while True:
        try:
            query = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not query:
            continue

        if query.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        try:
            result = agent.invoke({"messages": [("user", query)]}, config=config)
            messages = result.get("messages", [])
            for msg in reversed(messages):
                if hasattr(msg, "content") and msg.type == "ai":
                    print(f"\nAgent: {msg.content}\n")
                    break
        except Exception as e:
            print(f"\nError: {e}\n")


def run_single_query(agent, query: str, config: dict):
    """Run a single query and print the result."""
    print(f"Query: {query}\n")

    result = agent.invoke({"messages": [("user", query)]}, config=config)

    messages = result.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "content") and msg.type == "ai":
            print(f"Agent: {msg.content}")
            break


def main():
    """Main entry point."""
    args = parse_args()

    manager_kwargs: dict = {}
    if args.template:
        manager_kwargs["template_name"] = args.template
    if args.root_dir:
        manager_kwargs["root_dir"] = args.root_dir
    if args.idle_ttl:
        manager_kwargs["idle_ttl"] = timedelta(minutes=args.idle_ttl)

    manager = ThreadedSandboxManager(**manager_kwargs)

    try:
        # Handle --list
        if args.list:
            threads = manager.list_threads()
            if threads:
                print("Active threads:")
                for t in threads:
                    print(f"  - {t}")
            else:
                print("No active threads")
            return

        # Handle --delete
        if args.delete:
            if manager.delete_thread(args.thread):
                print(f"Deleted sandbox for thread '{args.thread}'")
            else:
                print(f"No sandbox found for thread '{args.thread}'")
            return

        model = get_model()

        print(f"Connecting to sandbox for thread '{args.thread}'...")
        print(f"  Template: {args.template}")

        checkpointer = MemorySaver()

        agent = create_deep_agent(
            model=model,
            backend=create_threaded_backend_factory(manager=manager),
            checkpointer=checkpointer,
            skills=args.skills,
        )

        config = {"configurable": {"thread_id": args.thread}}

        print("Initializing sandbox...")

        if args.query:
            run_single_query(agent, args.query, config)
        else:
            run_interactive(agent, args.thread, config)

    finally:
        pass


if __name__ == "__main__":
    main()
