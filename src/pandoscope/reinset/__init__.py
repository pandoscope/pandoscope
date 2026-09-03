"""
Session-time reinset composition (pandoscope/skills#179).

The composer runs once per session from a SessionStart hook, never from
a model turn. It detects facts from the environment, receives the intent
reference the spawner attached, resolves the intent file, compares the two
sides, writes the session answers file and renders the role profile.
"""
