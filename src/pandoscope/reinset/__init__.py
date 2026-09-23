"""
Session-time reinset composition (pandoscope/skills#179, skills#195).

The composer runs once per session from a SessionStart hook, never from
a model turn. It detects facts from the environment. It reads the
waybill order that the Routine fired from. It writes the session
answers file. It renders the role profile.
"""
