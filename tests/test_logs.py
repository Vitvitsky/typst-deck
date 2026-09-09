import json
import logging

from typst_deck.logs import JsonFormatter, TextFormatter, log_event, setup_logging


def record(name="typst_deck.test", level=logging.INFO, event="llm.done", **fields):
    log = logging.getLogger(name)
    captured = []
    handler = logging.Handler()
    handler.emit = captured.append
    log.addHandler(handler)
    log.setLevel(level)
    try:
        log_event(log, event, **fields)
    finally:
        log.removeHandler(handler)
    return captured[0]


def test_log_event_puts_fields_on_record():
    r = record(deck="d1", tokens_in=1240)
    assert r.msg == "llm.done"
    assert r.fields == {"deck": "d1", "tokens_in": 1240}


def test_log_event_without_fields():
    assert record(event="job.start").fields == {}


def test_text_formatter_renders_event_then_fields():
    out = TextFormatter().format(record(deck="d1", ms=341))
    assert "llm.done" in out
    assert "deck=d1" in out
    assert "ms=341" in out
    assert out.index("llm.done") < out.index("deck=d1")


def test_text_formatter_keeps_fields_in_call_order():
    out = TextFormatter().format(record(zeta=1, alpha=2))
    assert out.index("zeta=1") < out.index("alpha=2")


def test_text_formatter_quotes_values_with_spaces():
    assert 'err="boom boom"' in TextFormatter().format(record(err="boom boom"))


def test_json_formatter_emits_one_valid_object():
    d = json.loads(JsonFormatter().format(record(deck="d1", ms=341)))
    assert d["ev"] == "llm.done"
    assert d["deck"] == "d1"
    assert d["ms"] == 341
    assert d["lvl"] == "INFO"
    assert "ts" in d


def test_json_formatter_survives_unserializable_field():
    d = json.loads(JsonFormatter().format(record(obj=object())))
    assert isinstance(d["obj"], str)


def test_formatters_handle_plain_logging_calls():
    log = logging.getLogger("typst_deck.plain")
    captured = []
    handler = logging.Handler()
    handler.emit = captured.append
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        log.info("просто сообщение")
    finally:
        log.removeHandler(handler)
    assert "просто сообщение" in TextFormatter().format(captured[0])
    assert json.loads(JsonFormatter().format(captured[0]))["ev"] == "просто сообщение"


def test_setup_logging_text_installs_single_handler(capsys):
    setup_logging("INFO", "text")
    setup_logging("INFO", "text")  # повторный вызов не должен множить обработчики
    log = logging.getLogger("typst_deck.setup")
    log_event(log, "job.done", deck="d1")
    err = capsys.readouterr().err
    assert err.count("job.done") == 1
    assert "deck=d1" in err


def test_setup_logging_json_writes_parsable_lines(capsys):
    setup_logging("INFO", "json")
    log_event(logging.getLogger("typst_deck.setup"), "job.done", deck="d1")
    assert json.loads(capsys.readouterr().err.strip())["deck"] == "d1"


def test_setup_logging_respects_level(capsys):
    setup_logging("WARNING", "text")
    log_event(logging.getLogger("typst_deck.setup"), "job.done", deck="d1")
    assert capsys.readouterr().err == ""


def test_setup_logging_silences_duplicate_third_party_logs(capsys):
    setup_logging("INFO", "text")
    # httpx дублирует llm.done, uvicorn.access — наше событие http, но без таймингов
    logging.getLogger("httpx").info('HTTP Request: POST https://api.deepseek.com "200 OK"')
    logging.getLogger("uvicorn.access").info('127.0.0.1 - "GET /api/decks HTTP/1.1" 200')
    assert capsys.readouterr().err == ""


def test_setup_logging_keeps_third_party_warnings(capsys):
    setup_logging("INFO", "text")
    logging.getLogger("httpx").warning("что-то пошло не так")
    assert "что-то пошло не так" in capsys.readouterr().err


def test_setup_logging_keeps_our_own_info(capsys):
    setup_logging("INFO", "text")
    log_event(logging.getLogger("typst_deck.service"), "job.done", deck="d1")
    assert "job.done" in capsys.readouterr().err
