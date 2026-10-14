import os

from app import app

app.config["ACCOUNT_BATTLE_SCOPE_ENABLED"] = (
    os.environ.get(
        "ACCOUNT_BATTLE_SCOPE_ENABLED",
        "0",
    ).strip() == "1"
)
