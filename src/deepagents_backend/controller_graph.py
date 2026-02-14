from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Callable
from typing import Any, Literal, TypedDict

from src.deepagents_backend.qa import (
    PackageJsonReadResult,
    QaCommandResult,
    aspnetcore_project_present,
    classify_qa_failure,
    effective_qa_commands_for_backend,
    flutter_project_present,
    phoenix_project_present,
    python_project_present,
    python_qa_commands,
    qa_run_tests_enabled,
    qa_timeout_s,
    quarkus_project_present,
    read_package_json,
    run_qa,
    self_heal_max_rounds,
)

logger = logging.getLogger(__name__)


class ControllerState(TypedDict, total=False):
    # DeepAgents-compatible message list (tuples are accepted by LangChain/LangGraph).
    messages: list[Any]

    attempt: int
    qa_passed: bool
    qa_results: list[dict[str, Any]]
    qa_failure_kind: Literal["none", "code", "environment"]
    final_status: Literal["success", "failed_qa"]

    git_pushed: bool
    git_last_commit: str | None
    git_error: str | None
    git_warnings: list[str]
    delegate_target: Literal["qa_fixer", "db_migrator"]


GetBackendFn = Callable[[str], Any]


def _run_coro_sync(coro):
    """Run a coroutine from sync contexts.

    If we're already inside an event loop, run in a separate thread to avoid
    'asyncio.run() cannot be called from a running event loop'.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    fut: concurrent.futures.Future[Any] = concurrent.futures.Future()

    def _worker():
        try:
            fut.set_result(asyncio.run(coro))
        except Exception as e:  # pragma: no cover
            fut.set_exception(e)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return fut.result()


def _thread_id_from_config(config: Any) -> str:
    if not isinstance(config, dict):
        return "default-thread"
    configurable = config.get("configurable") or {}
    if not isinstance(configurable, dict):
        return "default-thread"
    tid = configurable.get("thread_id")
    return tid if isinstance(tid, str) and tid else "default-thread"


def _qa_results_to_dicts(results: list[QaCommandResult]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in results:
        out.append(
            {
                "command": r.command,
                "exit_code": r.exit_code,
                "output": r.output,
                "truncated": r.truncated,
            }
        )
    return out


def _format_last_failure(qa_results: list[dict[str, Any]]) -> str:
    if not qa_results:
        return "QA failed, but no command output was captured."
    last = qa_results[-1]
    cmd = last.get("command", "<unknown>")
    code = last.get("exit_code", "<unknown>")
    out = last.get("output", "")
    if not isinstance(out, str):
        out = str(out)
    # Keep this bounded; this will be fed back into the model.
    if len(out) > 8000:
        out = out[:8000]
    return f"QA failed on `{cmd}` (exit {code}). Output:\n\n{out}"


def _delegate_target_from_qa_results(
    qa_results: list[dict[str, Any]],
) -> Literal["qa_fixer", "db_migrator"]:
    if not qa_results:
        return "qa_fixer"
    last = qa_results[-1]
    output = str(last.get("output") or "").lower()
    command = str(last.get("command") or "").lower()
    db_markers = (
        "graphql",
        "hasura",
        "relation",
        "table",
        "column",
        "sql",
        "migration",
        "db_",
        "database",
    )
    if any(marker in output for marker in db_markers):
        return "db_migrator"
    if any(marker in command for marker in ("db", "hasura", "graphql", "sql")):
        return "db_migrator"
    return "qa_fixer"


def build_controller_graph(
    *,
    deep_agent_runnable: Any,
    get_backend: GetBackendFn,
    qa_enabled: bool,
    checkpointer: Any | None = None,
    store: Any | None = None,
) -> Any:
    # Imports are kept inside to avoid requiring langgraph/langchain in minimal dev environments.
    from langchain_core.messages import AIMessage, HumanMessage  # type: ignore
    from langchain_core.runnables import (  # type: ignore
        RunnableLambda,
        RunnablePassthrough,
    )
    from langgraph.graph import END, START, StateGraph  # type: ignore

    # Ensure the inner deep agent uses its own checkpoint namespace when a persistent
    # PostgresSaver is shared with the controller graph.
    deep_agent_for_node = deep_agent_runnable
    try:
        deep_agent_for_node = deep_agent_runnable.with_config(
            configurable={"checkpoint_ns": "deep_agent"}
        )
    except Exception as exc:
        logger.warning("Could not set checkpoint_ns on deep agent: %s", exc)
        deep_agent_for_node = deep_agent_runnable

    # Update only the `messages` key, preserving other controller state keys.
    agent_node = RunnablePassthrough.assign(
        messages=(
            RunnableLambda(lambda st: {"messages": st.get("messages", [])})
            | deep_agent_for_node
            | RunnableLambda(lambda out: out.get("messages", []))
        )
    )

    def _delegate_node(extra_instruction: str):
        return RunnablePassthrough.assign(
            messages=(
                RunnableLambda(
                    lambda st: {
                        "messages": [
                            *(st.get("messages", []) or []),
                            HumanMessage(content=extra_instruction),
                        ]
                    }
                )
                | deep_agent_for_node
                | RunnableLambda(lambda out: out.get("messages", []))
            )
        )

    qa_fixer_node = _delegate_node(
        "You are acting as QA-fixer subagent. Focus on lint/typecheck/build failures. "
        "Prefer minimal code edits and avoid changing DB schema unless clearly required."
    )
    db_migrator_node = _delegate_node(
        "You are acting as DB-migrator subagent. Focus on schema/data-layer issues "
        "(Hasura, GraphQL, SQL, migrations). Keep app/UI changes minimal."
    )

    async def qa_validate(_state: ControllerState, config: Any) -> dict[str, Any]:
        if not qa_enabled:
            return {"qa_passed": True, "qa_results": [], "final_status": "success"}

        thread_id = _thread_id_from_config(config)
        backend = get_backend(thread_id)

        pkg: PackageJsonReadResult = await asyncio.to_thread(read_package_json, backend)
        if pkg.exists and pkg.error:
            return {
                "qa_passed": False,
                "qa_results": [
                    {
                        "command": "<parse package.json>",
                        "exit_code": 2,
                        "output": pkg.error,
                        "truncated": False,
                    }
                ],
            }

        commands = effective_qa_commands_for_backend(backend, pkg)
        if not commands and not pkg.exists and python_project_present(backend):
            commands = python_qa_commands(run_tests=qa_run_tests_enabled())
        if not commands:
            # No scripts defined; treat as pass but record a note.
            return {
                "qa_passed": True,
                "qa_results": [
                    {
                        "command": "<none>",
                        "exit_code": 0,
                        "output": "No QA commands detected (no scripts, no fallbacks).",
                        "truncated": False,
                    }
                ],
                "final_status": "success",
            }

        # The backend already has an exec timeout; we still keep a higher-level timeout.
        try:
            passed, results = await asyncio.wait_for(
                asyncio.to_thread(run_qa, backend, commands),
                timeout=float(qa_timeout_s()),
            )
        except TimeoutError:
            passed = False
            results = [
                QaCommandResult(
                    command="; ".join(commands),
                    exit_code=124,
                    output="QA timeout exceeded",
                    truncated=False,
                )
            ]

        failure_kind = classify_qa_failure(results)
        return {
            "qa_passed": bool(passed),
            "qa_results": _qa_results_to_dicts(results),
            "qa_failure_kind": failure_kind if not passed else "none",
        }

    async def self_heal_message(state: ControllerState, config: Any) -> dict[str, Any]:
        attempt = int(state.get("attempt") or 0) + 1
        qa_results = state.get("qa_results") or []
        msg = _format_last_failure(qa_results)
        hint = (
            "\n\nPlease fix the cause, then make QA pass. "
            "If dependencies are missing, run `npm install`. "
            "After edits, ensure `npm run -s build` succeeds."
        )
        try:
            thread_id = _thread_id_from_config(config)
            backend = get_backend(thread_id)
            pkg: PackageJsonReadResult = await asyncio.to_thread(read_package_json, backend)
            if not pkg.exists and python_project_present(backend):
                hint = (
                    "\n\nPlease fix the cause, then make QA pass. "
                    "If dependencies are missing, run `pip install -r requirements.txt`. "
                    "After edits, ensure `ruff check .` succeeds."
                )
            elif not pkg.exists and aspnetcore_project_present(backend):
                hint = (
                    "\n\nPlease fix the cause, then make QA pass. "
                    "If dependencies are missing, run `dotnet restore`. "
                    "After edits, ensure `dotnet build` succeeds."
                )
            elif not pkg.exists and quarkus_project_present(backend):
                hint = (
                    "\n\nPlease fix the cause, then make QA pass. "
                    "If dependencies are missing, run `./mvnw -q dependency:resolve`. "
                    "After edits, ensure `./mvnw -q -DskipTests compile` succeeds."
                )
            elif not pkg.exists and phoenix_project_present(backend):
                hint = (
                    "\n\nPlease fix the cause, then make QA pass. "
                    "If dependencies are missing, run `mix deps.get`. "
                    "After edits, ensure `mix compile` succeeds."
                )
            elif not pkg.exists and flutter_project_present(backend):
                hint = (
                    "\n\nPlease fix the cause, then make QA pass. "
                    "If dependencies are missing, run `flutter pub get`. "
                    "After edits, ensure `flutter analyze` succeeds."
                )
        except Exception as exc:
            logger.debug("Could not detect project type for self-heal hint: %s", exc)
        msg += hint

        messages = list(state.get("messages") or [])
        messages.append(HumanMessage(content=msg))
        return {
            "attempt": attempt,
            "messages": messages,
            "delegate_target": _delegate_target_from_qa_results(qa_results),
        }

    async def qa_fail_summary(state: ControllerState, config: Any) -> dict[str, Any]:
        # `config` must be named exactly this way for LangChain/LangGraph introspection.
        # Keep it in the signature and mark as used to satisfy linting.
        _ = config

        qa_results = state.get("qa_results") or []
        failure_kind = str(state.get("qa_failure_kind") or "code")
        attempt = int(state.get("attempt") or 0)
        max_rounds = self_heal_max_rounds()

        if failure_kind == "environment":
            summary = (
                "QA failed due to a sandbox environment/setup issue, so I skipped self-heal retries "
                "(code edits cannot fix missing runtime tooling).\n\n"
                f"{_format_last_failure(qa_results)}\n\n"
                "Please fix the sandbox/runtime environment (for example tool PATH/image setup), "
                "then rerun."
            )
        else:
            summary = (
                f"I couldn't get the project into a passing state after {attempt} self-heal round(s) "
                f"(max {max_rounds}).\n\n"
                f"{_format_last_failure(qa_results)}\n\n"
                "Tell me if you want me to keep trying (increase self-heal rounds) or if we should change the approach."
            )

        messages = list(state.get("messages") or [])
        messages.append(AIMessage(content=summary))
        return {"final_status": "failed_qa", "messages": messages}

    async def git_sync(_state: ControllerState, config: Any) -> dict[str, Any]:
        """Sync sandbox tree + commit + push to GitLab.

        In production, GitLab sync is required (AMICABLE_GIT_SYNC_REQUIRED=1).
        """

        try:
            from src.deepagents_backend.tool_journal import drain as drain_tool_journal
            from src.deepagents_backend.tool_journal import (
                summarize as summarize_tool_journal,
            )
            from src.gitlab.commit_message import (
                append_commit_warnings,
                evaluate_agent_readme_policy,
                generate_agent_commit_message_llm,
            )
            from src.gitlab.config import (
                ensure_git_sync_configured,
                git_agent_readme_policy_enabled,
                git_sync_enabled,
                git_sync_required,
            )
            from src.gitlab.sync import sync_sandbox_tree_to_repo

            ensure_git_sync_configured()
            required = git_sync_required()
            if not git_sync_enabled():
                return {
                    "git_pushed": False,
                    "git_last_commit": None,
                    "git_error": None,
                    "git_warnings": [],
                }

            thread_id = _thread_id_from_config(config)
            cfg = (config or {}).get("configurable") if isinstance(config, dict) else {}
            if not isinstance(cfg, dict):
                cfg = {}

            repo_http_url = cfg.get("git_repo_http_url")
            project_slug = cfg.get("project_slug") or thread_id

            if not isinstance(repo_http_url, str) or not repo_http_url:
                if required:
                    raise RuntimeError("git repo url missing")
                return {
                    "git_pushed": False,
                    "git_last_commit": None,
                    "git_error": "git repo url missing",
                    "git_warnings": [],
                }

            backend = get_backend(thread_id)

            # Gather "why" context for the commit message.
            events = drain_tool_journal(thread_id)
            journal_summary = summarize_tool_journal(events)

            messages = list(_state.get("messages") or [])
            user_request = ""
            for m in reversed(messages):
                # LangChain messages expose .type/.content, but we keep this defensive.
                mtype = getattr(m, "type", None)
                content = getattr(m, "content", None)
                if mtype == "human" and isinstance(content, str) and content.strip():
                    user_request = content.strip()
                    break
            # Fallback (older message objects): if we couldn't detect a human message,
            # take the earliest non-empty string content.
            if not user_request:
                for m in messages:
                    content = getattr(m, "content", None)
                    if isinstance(content, str) and content.strip():
                        user_request = content.strip()
                        break

            agent_summary = ""
            for m in reversed(messages):
                mtype = getattr(m, "type", None)
                content = getattr(m, "content", None)
                if (
                    mtype in ("ai", "assistant")
                    and isinstance(content, str)
                    and content.strip()
                ):
                    agent_summary = content.strip()
                    break

            qa_passed = _state.get("qa_passed")
            qa_results = _state.get("qa_results") or []
            qa_last_output = ""
            if isinstance(qa_results, list) and qa_results:
                last = qa_results[-1]
                if isinstance(last, dict):
                    out = last.get("output")
                    if isinstance(out, str):
                        qa_last_output = out

            policy_warnings: list[str] = []

            def _commit_message(diff_stat: str, name_status: str) -> str:
                msg = generate_agent_commit_message_llm(
                    user_request=user_request,
                    agent_summary=agent_summary,
                    project_slug=str(project_slug),
                    qa_passed=bool(qa_passed) if qa_passed is not None else None,
                    qa_last_output=qa_last_output,
                    diff_stat=diff_stat,
                    name_status=name_status,
                    tool_journal_summary=journal_summary,
                )
                if git_agent_readme_policy_enabled():
                    warnings = evaluate_agent_readme_policy(name_status)
                    policy_warnings[:] = warnings
                    return append_commit_warnings(msg, warnings)
                return msg

            pushed, sha, _diff_stat, _name_status = await asyncio.to_thread(
                sync_sandbox_tree_to_repo,
                backend,
                repo_http_url=repo_http_url,
                project_slug=str(project_slug),
                commit_message_fn=_commit_message,
            )
            return {
                "git_pushed": bool(pushed),
                "git_last_commit": sha,
                "git_error": None,
                "git_warnings": list(policy_warnings),
            }
        except Exception as e:
            logger.exception("git_sync failed")
            # In required mode, bubble up so the user sees a hard error.
            try:
                from src.gitlab.config import git_sync_required

                if git_sync_required():
                    raise
            except Exception:
                raise
            return {
                "git_pushed": False,
                "git_last_commit": None,
                "git_error": str(e),
                "git_warnings": [],
            }

    def route_after_qa(state: ControllerState) -> Literal["pass", "heal", "fail"]:
        passed = bool(state.get("qa_passed"))
        if passed:
            return "pass"
        if str(state.get("qa_failure_kind") or "") == "environment":
            return "fail"

        attempt = int(state.get("attempt") or 0)
        if attempt < self_heal_max_rounds():
            return "heal"
        return "fail"

    def route_delegate(state: ControllerState) -> Literal["qa_fixer", "db_migrator"]:
        target = state.get("delegate_target")
        return "db_migrator" if target == "db_migrator" else "qa_fixer"

    g: Any = StateGraph(ControllerState)
    g.add_node("deepagents_edit", agent_node)
    g.add_node("qa_fixer_edit", qa_fixer_node)
    g.add_node("db_migrator_edit", db_migrator_node)
    g.add_node(
        "qa_validate",
        RunnableLambda(
            func=lambda st, cfg=None: _run_coro_sync(qa_validate(st, cfg)),
            afunc=qa_validate,
        ),
    )
    g.add_node(
        "self_heal_message",
        RunnableLambda(
            func=lambda st, cfg=None: _run_coro_sync(self_heal_message(st, cfg)),
            afunc=self_heal_message,
        ),
    )
    g.add_node(
        "qa_fail_summary",
        RunnableLambda(
            func=lambda st, cfg=None: _run_coro_sync(qa_fail_summary(st, cfg)),
            afunc=qa_fail_summary,
        ),
    )
    g.add_node(
        "git_sync",
        RunnableLambda(
            func=lambda st, cfg=None: _run_coro_sync(git_sync(st, cfg)), afunc=git_sync
        ),
    )

    g.add_edge(START, "deepagents_edit")
    g.add_edge("deepagents_edit", "qa_validate")
    g.add_conditional_edges(
        "qa_validate",
        route_after_qa,
        {
            "pass": "git_sync",
            "heal": "self_heal_message",
            "fail": "qa_fail_summary",
        },
    )
    g.add_conditional_edges(
        "self_heal_message",
        route_delegate,
        {
            "qa_fixer": "qa_fixer_edit",
            "db_migrator": "db_migrator_edit",
        },
    )
    g.add_edge("qa_fixer_edit", "qa_validate")
    g.add_edge("db_migrator_edit", "qa_validate")
    g.add_edge("qa_fail_summary", "git_sync")
    g.add_edge("git_sync", END)

    # A checkpointer is required for HITL interrupts/resume (Command(resume=...)).
    # The store must be propagated so the inner agent's StoreBackend can access it.
    return g.compile(checkpointer=checkpointer, store=store)
