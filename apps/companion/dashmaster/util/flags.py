"""Feature flag helpers for runtime behaviour toggles."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class FeatureFlags:
    """Container for companion feature flags."""

    ntp_gate: bool = False
    enforce_pin: bool = False

    @classmethod
    def from_env(cls) -> "FeatureFlags":
        return cls(
            ntp_gate=_env_flag("DASHMASTER_NTP_GATE", default=False),
            enforce_pin=_env_flag("DASHMASTER_ENFORCE_PIN", default=False),
        )

    def ensure_ntp_ready(self) -> None:
        """Raise if NTP gate should prevent actions.

        Phase 1 stubs always pass but logs can hook here in Phase 2.
        """

        if not self.ntp_gate:
            return
        # Placeholder for future integration with companion status tracking.

    def ensure_pin_provided(self, pin: str | None) -> None:
        """Validate that a PIN is present when enforcement is enabled."""

        if not self.enforce_pin:
            return
        if not pin:
            raise PermissionError("Admin PIN required for this action")


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}
