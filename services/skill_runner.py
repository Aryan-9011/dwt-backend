"""
Skill Runner — bridges Claude skills/agents to the Agent Hub via Gemini.

Reads a .claude/skills/<name>/SKILL.md or .claude/agents/<name>.md file, parses
the YAML frontmatter + body, auto-loads any reference files the skill says it
needs ("Read: reference/brand-reference.md" etc.), then sends the whole package
to Gemini Pro as a system prompt.

This is NOT a perfect 1:1 replica of Claude Code's behavior — skills that depend
on multi-step tool orchestration (file writes, web search, subagent spawning)
won't fully work. But ~85% of DWT skills are prompt-driven (copywriting,
analysis, planning) and translate cleanly to Gemini.

Public API:
  list_skills()                          → catalog of available skills + agents
  run_skill(name, args, expect_json)     → execute one skill, return string or dict
"""
import re
from pathlib import Path

from services.llm_chat import chat as llm_chat, chat_json as llm_chat_json

# Workspace root = two levels up from this file (backend/services/ → backend → root)
WORKSPACE_ROOT = Path(__file__).parent.parent.parent
SKILLS_DIR = WORKSPACE_ROOT / ".claude" / "skills"
AGENTS_DIR = WORKSPACE_ROOT / ".claude" / "agents"
REFERENCE_DIR = WORKSPACE_ROOT / "reference"

# Cap on how much referenced-file content we shove into context (rough char budget)
MAX_REF_CONTEXT_CHARS = 60_000


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Strip YAML frontmatter (---\\n...\\n---). Return (meta_dict, body)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta_block, body = parts[1], parts[2].lstrip("\n")
    meta: dict = {}
    for line in meta_block.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


def _extract_referenced_files(body: str) -> list[str]:
    """
    Find file paths the skill says to read.
    Matches markdown backticks: `reference/brand-reference.md`
    Also matches inline mentions like 'reference/foo.md'.
    """
    # Backticked file paths
    backticked = re.findall(r"`([\w/.\-]+\.md)`", body)
    # Bare paths that start with reference/ or context/
    bare = re.findall(r"(?:^|\s)((?:reference|context)/[\w/.\-]+\.md)", body)
    seen: set = set()
    out: list = []
    for p in backticked + bare:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _safe_read(rel_path: str) -> str | None:
    """Read a workspace-relative file if it exists, capping size."""
    p = WORKSPACE_ROOT / rel_path
    try:
        if not p.exists() or not p.is_file():
            return None
        if not str(p.resolve()).startswith(str(WORKSPACE_ROOT.resolve())):
            return None  # path-escape guard
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def list_skills() -> dict:
    """Catalog every skill + agent the hub can run."""
    skills: list = []
    agents: list = []

    if SKILLS_DIR.exists():
        for skill_dir in sorted(SKILLS_DIR.iterdir()):
            md = skill_dir / "SKILL.md"
            if not md.exists():
                continue
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            meta, _ = _parse_frontmatter(text)
            skills.append({
                "id": skill_dir.name,
                "name": meta.get("name", skill_dir.name),
                "description": meta.get("description", "")[:300],
                "type": "skill",
            })

    if AGENTS_DIR.exists():
        for agent_file in sorted(AGENTS_DIR.glob("*.md")):
            try:
                text = agent_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            meta, _ = _parse_frontmatter(text)
            agents.append({
                "id": agent_file.stem,
                "name": meta.get("name", agent_file.stem),
                "description": meta.get("description", "")[:300],
                "type": "agent",
            })

    return {"skills": skills, "agents": agents, "skill_count": len(skills), "agent_count": len(agents)}


def _load_skill_or_agent(name: str) -> tuple[dict, str, list[tuple[str, str]]]:
    """
    Find and load a skill or agent by name.
    Returns (metadata, body, [(ref_path, ref_content)]).
    """
    # Try skill first
    skill_md = SKILLS_DIR / name / "SKILL.md"
    agent_md = AGENTS_DIR / f"{name}.md"

    if skill_md.exists():
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    elif agent_md.exists():
        text = agent_md.read_text(encoding="utf-8", errors="replace")
    else:
        raise ValueError(f"No skill or agent found with name '{name}'")

    meta, body = _parse_frontmatter(text)

    # Auto-load referenced files (best-effort; skip silently if missing)
    refs: list = []
    total_chars = 0
    for rel in _extract_referenced_files(body):
        content = _safe_read(rel)
        if content is None:
            continue
        # Skip if budget exceeded
        if total_chars + len(content) > MAX_REF_CONTEXT_CHARS:
            content = content[: MAX_REF_CONTEXT_CHARS - total_chars] + "\n\n[truncated]"
        refs.append((rel, content))
        total_chars += len(content)
        if total_chars >= MAX_REF_CONTEXT_CHARS:
            break

    return meta, body, refs


def run_skill(
    name: str,
    args: str = "",
    expect_json: bool = False,
    max_tokens: int = 6000,
    smart: bool = True,
) -> dict:
    """
    Execute a skill or agent.

    Args:
        name: skill id (e.g. 'carousel-copy') or agent id (e.g. 'marketing-post-ideator')
        args: free-text input from the user (e.g. "Vietnam family May 2026")
        expect_json: if True, requests JSON output and parses it
        max_tokens: Gemini output budget (default 6K — enough for most copy outputs)
        smart: True uses Gemini 2.5 Pro (default — better reasoning), False uses Flash

    Returns:
        {
          "skill": name,
          "type": "skill" | "agent",
          "metadata": {...},
          "referenced_files": [list of files auto-loaded],
          "output": str (or dict if expect_json),
          "model_used": "gemini-2.5-pro" | ...
        }
    """
    meta, body, refs = _load_skill_or_agent(name)
    is_agent = (AGENTS_DIR / f"{name}.md").exists() and not (SKILLS_DIR / name / "SKILL.md").exists()

    # Build system prompt: skill body + auto-loaded reference file contents
    ref_block = ""
    if refs:
        ref_block = "\n\n## Auto-loaded reference files\n\n"
        for path, content in refs:
            ref_block += f"\n--- BEGIN: {path} ---\n{content}\n--- END: {path} ---\n"

    system_prompt = (
        f"{body.strip()}\n{ref_block}\n\n"
        "IMPORTANT: You are running inside Dream World Tours' Agent Hub. "
        "You cannot write files — return your output directly in your response. "
        "If the skill says 'Save to outputs/...', include the filename suggestion in your response "
        "but produce the full content inline."
    )

    user_msg = args.strip() or f"Run the {name} skill with default behavior. Use sensible DWT-appropriate inputs."

    import os as _os
    provider = _os.environ.get("LLM_PROVIDER", "gemini").lower().strip()

    if expect_json:
        output = llm_chat_json(
            system=system_prompt,
            user=user_msg,
            max_tokens=max_tokens,
            smart=smart,
        )
    else:
        output = llm_chat(
            system=system_prompt,
            user=user_msg,
            max_tokens=max_tokens,
            temperature=0.7,
            smart=smart,
        )

    # Report which model actually served the request
    if provider == "claude":
        model_used = "claude-sonnet-4-6" if smart else "claude-haiku-4-5"
    else:
        model_used = "gemini-2.5-pro" if smart else "gemini-2.5-flash"

    return {
        "skill": name,
        "type": "agent" if is_agent else "skill",
        "metadata": meta,
        "referenced_files": [r[0] for r in refs],
        "output": output,
        "model_used": model_used,
        "provider": provider,
        "expected_json": expect_json,
    }
