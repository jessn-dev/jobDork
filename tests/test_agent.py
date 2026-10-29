"""
Tests for a coding agent as the writer (web/agent.py, web/mcp.py): the brief
is what a model would have been given, a saved answer goes through every
check a model's does, the agent never checks itself, and the MCP server and
the CLI speak the same tools. A temporary database and documents folder;
no model is called and nothing goes online.

Keep the `__main__` block at the END of this file.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobdork import cli
from jobdork.ai import guard, llm, writer
from jobdork.core.config import Config, ConfigError, Llm, Reader, _validate
from jobdork.db.store import Role, Store
from jobdork.web import agent, api, mcp

RESUME = """Jane Doe
Platform engineer. Seven years of Python and Go.
- Ran the Kubernetes platform for 40 services at Acme.
- Built CI pipelines in GitHub Actions.
"""

ADVERT = ("We are hiring a platform engineer to run Kubernetes for our "
          "product teams. You will own CI, on-call and the path to production. "
          "Python or Go required. Remote in the EU. " * 3)

LETTER = {"paragraphs": ["I ran the Kubernetes platform for 40 services at Acme, the work "
                         "your advert describes.", "I built CI pipelines in GitHub Actions."]}


@contextlib.contextmanager
def _setup():
    """A config, a resume and one job post, with documents kept in the
    temporary folder: never the real ~/Documents."""
    with tempfile.TemporaryDirectory() as tmp:
        resume = Path(tmp) / "resume.md"
        resume.write_text(RESUME, encoding="utf-8")
        cfg = Config(titles_include=["x"], db_path=str(Path(tmp) / "t.db"),
                     resume_path=str(resume))
        role = Role(platform="greenhouse", company="Initech", title="Platform Engineer",
                    url="https://boards.greenhouse.io/initech/jobs/1",
                    location_raw="Remote", description=ADVERT)
        with Store(cfg.db_path) as store:
            store.upsert(role)
        was = os.environ.get("JOBDORK_DOCS_DIR")
        os.environ["JOBDORK_DOCS_DIR"] = tmp
        try:
            yield cfg, role.uid, Path(tmp)
        finally:
            if was is None:
                os.environ.pop("JOBDORK_DOCS_DIR", None)
            else:
                os.environ["JOBDORK_DOCS_DIR"] = was


def test_the_brief_is_what_a_model_would_have_been_given():
    with _setup() as (cfg, uid, _):
        brief = agent.call(cfg, "get_brief", {"uid": uid, "kind": "cover_letter"})
        with Store(cfg.db_path) as store:
            assert not store.artifacts(uid), "a brief writes nothing"
    assert brief["system"] == writer.LETTER_SYSTEM
    assert brief["schema"] == writer.LETTER_SCHEMA
    assert "Kubernetes" in brief["user"] and "Jane Doe" in brief["user"]
    assert "save_document" in brief["then"]


def test_a_saved_answer_goes_through_every_check_and_is_recorded():
    with _setup() as (cfg, uid, tmp):
        done = agent.call(cfg, "save_document", {"uid": uid, "kind": "cover_letter",
                                                 "answer": LETTER, "_client": "claude-code"})
        with Store(cfg.db_path) as store:
            (letter,) = store.artifacts(uid, "cover_letter")
            output = store.conn.execute("SELECT model FROM ai_outputs").fetchone()
            status = store.get(uid)["status"]
        assert Path(done["files"][0]).is_relative_to(tmp), "kept in the documents folder"
    checks = {c["check"]: c for c in done["checks"]}
    assert checks["AI tells"]["passed"] and "unsupported figures" in checks
    # No checker set: the hallucination check is not run, and says so.
    assert not checks[writer.GUARD_GATE]["passed"]
    assert "no checker model" in checks[writer.GUARD_GATE]["detail"]
    assert writer.GUARD_GATE in done["to_read"]
    assert letter["path"] == done["files"][0]
    assert output["model"] == "Coding agent · claude-code"
    assert status == "interested"


def test_an_answer_that_is_not_the_schema_is_refused():
    with _setup() as (cfg, uid, _):
        for answer, said in (({"nope": []}, "no paragraphs"),
                             ({"paragraphs": "one string"}, "must be a array")):
            try:
                agent.call(cfg, "save_document", {"uid": uid, "kind": "cover_letter",
                                                  "answer": answer})
            except agent.ToolError as exc:
                assert said in str(exc), exc
            else:
                raise AssertionError(f"accepted {answer}")
        with Store(cfg.db_path) as store:
            assert not store.artifacts(uid)


def test_the_agent_never_falls_through_to_another_model():
    settings = llm.Settings(provider=llm.AGENT,
                            fallbacks=[llm.Settings(provider="ollama", model="m")])
    llm.agent_answers([])
    try:
        llm.complete_json(settings, "sys", "user", {"type": "object"}, purpose="judge")
    except llm.AgentBrief:
        pass
    else:
        raise AssertionError("an agent with nothing to give must stop the run")
    assert llm.last_brief()["system"] == "sys"


def test_the_agent_never_checks_its_own_writing():
    ollama = llm.Settings(provider="ollama", model="checker")
    wrote = llm.Settings(provider=llm.AGENT, checkers=[ollama])
    use, _ = guard.checking(wrote)
    assert (use.provider, use.model, use.fallbacks) == ("ollama", "checker", [])
    alone = guard.check(llm.Settings(provider=llm.AGENT), "I ran Kubernetes.", {"resume": ""})
    assert not alone.checked and alone.error == guard.NO_CHECKER


def test_as_agent_keeps_the_other_readers_as_checkers():
    cfg = Config(llm=Llm(provider="ollama", model="m", readers=[Reader("ollama", "m")]))
    mine = agent.as_agent(cfg)
    assert [r.provider for r in mine.llm.readers] == [llm.AGENT]
    assert [(r.provider, r.model) for r in mine.llm.checkers] == [("ollama", "m")]
    assert cfg.llm.readers[0].provider == "ollama", "the config itself is unchanged"


def test_a_coding_agent_writes_alone():
    _validate(Config(titles_include=["x"], llm=Llm(provider=llm.AGENT, readers=[Reader(llm.AGENT)])))
    for bad in (Llm(provider=llm.AGENT, readers=[Reader(llm.AGENT), Reader("ollama", "m")]),
                Llm(provider="ollama", model="m", readers=[Reader("ollama", "m")],
                    checkers=[Reader(llm.AGENT)])):
        try:
            _validate(Config(titles_include=["x"], llm=bad))
        except ConfigError as exc:
            assert "coding agent" in str(exc)
        else:
            raise AssertionError(f"accepted {bad}")


def test_agent_mode_refuses_the_dashboards_model_jobs_with_what_to_ask():
    with _setup() as (cfg, uid, _):
        cfg.llm = Llm(provider=llm.AGENT, readers=[Reader(llm.AGENT)])
        for job in (api.letter_job, api.tailor_job, api.judge_job):
            try:
                job(cfg, uid=uid) if job is api.judge_job else job(cfg, uid)
            except api.ApiError as exc:
                assert exc.status == 409 and "Ask your agent" in str(exc) and uid in str(exc)
            else:
                raise AssertionError(f"{job.__name__} ran in agent mode")
        lines = []
        with Store(cfg.db_path) as store:
            assert api._judge_after_scan(cfg, store, lines.append) == "AI judging skipped"


def test_a_verdict_is_saved_as_the_ai_score():
    with _setup() as (cfg, uid, _):
        done = agent.call(cfg, "save_verdict", {"uid": uid, "answer": {
            "score": 81, "verdict": "strong", "summary": "Kubernetes and CI match.",
            "reasons": ["Ran Kubernetes for 40 services"], "concerns": [],
            "enough_evidence": True}})
        assert done["score"] == 81 and done["verdict"] == "strong"
        with Store(cfg.db_path) as store:
            assert api.ai_fields(store.get(uid))["ai"]["score"] == 81


def test_update_application_changes_only_what_is_given():
    with _setup() as (cfg, uid, _):
        agent.call(cfg, "update_application", {"uid": uid, "status": "applied",
                                               "next_step": "Call", "next_date": "2026-11-02"})
        agent.call(cfg, "update_application", {"uid": uid, "contact_name": "Dana",
                                               "note": "They called"})
        with Store(cfg.db_path) as store:
            app = store.application(uid)
            notes = store.application_notes(uid)
        assert (app["next_step"], app["next_date"], app["contact_name"]) == \
            ("Call", "2026-11-02", "Dana")
        assert [n["note"] for n in notes] == ["They called"]
        try:
            agent.call(cfg, "update_application", {"uid": uid})
        except agent.ToolError as exc:
            assert "nothing to change" in str(exc)
        else:
            raise AssertionError("an empty update was accepted")


def test_tools_refuse_what_they_do_not_take():
    with _setup() as (cfg, uid, _):
        for name, args, said in (("nope", {}, "no tool"), ("get_job_post", {}, "needs uid"),
                                 ("get_job_post", {"uid": uid, "x": 1}, "takes no x"),
                                 ("get_brief", {"uid": "../etc", "kind": "cover_letter"}, "uid")):
            try:
                agent.call(cfg, name, args)
            except agent.ToolError as exc:
                assert said in str(exc), (name, exc)
            else:
                raise AssertionError(f"{name} {args} accepted")


def test_the_mcp_server_speaks_json_rpc_on_stdio():
    with _setup() as (cfg, uid, _):
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2024-11-05", "clientInfo": {"name": "codex"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "save_document", "arguments": {"uid": uid, "kind": "cover_letter",
                                                       "answer": LETTER}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
                "name": "get_job_post", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 5, "method": "nope"},
        ]
        out = io.StringIO()
        mcp.serve(cfg, io.StringIO("\n".join(json.dumps(m) for m in lines) + "\nnot json\n"), out)
        with Store(cfg.db_path) as store:
            model = store.conn.execute("SELECT model FROM ai_outputs").fetchone()["model"]
    answers = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [a["id"] for a in answers] == [1, 2, 3, 4, 5, None], "no answer to a notification"
    hello = answers[0]["result"]
    assert hello["protocolVersion"] == "2024-11-05" and hello["serverInfo"]["name"] == "jobdork"
    assert "get_brief" in hello["instructions"]
    assert {t["name"] for t in answers[1]["result"]["tools"]} == set(agent.BY_NAME)
    assert not answers[2]["result"]["isError"]
    assert json.loads(answers[2]["result"]["content"][0]["text"])["saved"]
    assert model == "Coding agent · codex", "named for the client that connected"
    assert answers[3]["result"]["isError"]
    assert answers[4]["error"]["code"] == -32601 and answers[5]["error"]["code"] == -32700


def test_the_cli_runs_the_same_tools():
    with _setup() as (cfg, uid, tmp):
        config = tmp / "config.yaml"
        config.write_text(f"titles: {{include: [x]}}\ndb: {cfg.db_path}\n"
                          f"resume: {{path: {cfg.resume_path}}}\n", encoding="utf-8")
        here = os.getcwd()
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cli.main(["--config", str(config), "agent", "list_job_posts",
                                 '{"query": "platform"}'])
            listed = json.loads(out.getvalue())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                bad = cli.main(["--config", str(config), "agent", "get_job_post", "{not json"])
        finally:
            os.chdir(here)
    assert code == 0 and listed["job_posts"][0]["uid"] == uid
    assert bad == 2 and "not JSON" in json.loads(out.getvalue())["error"]


def test_the_setup_commands_start_jobdork_on_this_computer():
    cfg = Config(path="/tmp/jobdork/config.yaml")
    s = api.agent_setup(cfg)
    assert s["args"][:3] == ["-m", "jobdork.cli", "--config"] and s["args"][-1] == "mcp"
    assert s["args"][3].endswith("config.yaml")
    assert s["claude_code"].startswith("claude mcp add jobdork -- ")
    assert json.loads(s["claude_desktop"])["mcpServers"]["jobdork"]["command"] == sys.executable
    frozen, was = getattr(sys, "frozen", None), sys.executable
    sys.frozen = True
    try:
        assert api.agent_setup(cfg)["args"] == ["--mcp"]
    finally:
        if frozen is None:
            del sys.frozen
        sys.executable = was


# ── keep this block LAST ───────────────────────────────────────────────────────

if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except BaseException as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"{len(tests) - failures}/{len(tests)} passed")
    raise SystemExit(1 if failures else 0)
