"""Tests for bae/agent.py -- extract_executable helper."""

from __future__ import annotations

from bae.agent import extract_executable


# --- extract_executable ---


def test_extract_executable_single_block():
    text = "Here is code:\n<run>\nprint('hello')\n</run>\nDone."
    blocks = extract_executable(text)
    assert blocks == ["print('hello')"]


def test_extract_executable_multiple_blocks():
    text = (
        "<run>\nfirst()\n</run>\n"
        "some text\n"
        "<run>\nsecond()\n</run>\n"
        "<run>\nthird()\n</run>"
    )
    blocks = extract_executable(text)
    assert blocks == ["first()", "second()", "third()"]


def test_extract_executable_no_blocks():
    text = "Just plain text, no code blocks here."
    blocks = extract_executable(text)
    assert blocks == []
