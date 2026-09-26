from pathlib import Path

from livetranslate.app import parse_args


def test_parse_args():
    a = parse_args(["--self-test", "--wav", "x.wav"])
    assert a.self_test and a.wav == Path("x.wav") and not a.demo and not a.dev
    assert parse_args(["--demo"]).demo
