"""Tests for bae/agent.py -- extract_executable helper."""

from __future__ import annotations

from bae.agent import extract_executable


# --- extract_executable ---


def test_extract_executable_single_block():
    text = "Here is code:\n<run>\nprint('hello')\n</run>\nDone."
    code, extra = extract_executable(text)
    assert code == "print('hello')"
    assert extra == 0


def test_extract_executable_multiple_blocks():
    text = (
        "<run>\nfirst()\n</run>\n"
        "some text\n"
        "<run>\nsecond()\n</run>\n"
        "<run>\nthird()\n</run>"
    )
    code, extra = extract_executable(text)
    assert code == "first()"
    assert extra == 2


def test_extract_executable_no_blocks():
    text = "Just plain text, no code blocks here."
    code, extra = extract_executable(text)
    assert code is None
    assert extra == 0
