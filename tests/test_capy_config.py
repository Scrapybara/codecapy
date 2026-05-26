import pytest
from pydantic import ValidationError

from src.capy_config import CapyConfig


def test_accepts_valid_capy_steps():
    config = CapyConfig.model_validate(
        {
            "steps": [
                {"type": "bash", "command": "npm install"},
                {"type": "create-env"},
                {"type": "instruction", "text": "Open http://localhost:3000"},
                {"type": "wait", "seconds": 5},
                {"type": "wait"},
            ]
        }
    )

    assert len(config.steps) == 5


@pytest.mark.parametrize(
    ("step", "message"),
    [
        ({"type": "bash"}, "bash steps require a non-empty command"),
        ({"type": "bash", "command": "   "}, "bash steps require a non-empty command"),
        ({"type": "instruction"}, "instruction steps require non-empty text"),
        (
            {"type": "instruction", "text": ""},
            "instruction steps require non-empty text",
        ),
        (
            {"type": "wait", "seconds": 0},
            "wait steps require seconds to be greater than 0",
        ),
        (
            {"type": "wait", "seconds": -1},
            "wait steps require seconds to be greater than 0",
        ),
    ],
)
def test_rejects_invalid_capy_steps(step, message):
    with pytest.raises(ValidationError, match=message):
        CapyConfig.model_validate({"steps": [step]})
