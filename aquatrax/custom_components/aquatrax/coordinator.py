"""Coordinator for the AquaTrax integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AquaTraxAuthError, AquaTraxClient, AquaTraxConnectionError
from .const import DEFAULT_UPDATE_INTERVAL_HOURS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class AquaTraxCoordinator(DataUpdateCoordinator[dict]):
    """Polls the AquaTrax portal and keeps a running water total."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: AquaTraxClient,
        utility_id: str,
        utility_name: str,
        email: str,
        password: str,
        update_interval_hours: int = DEFAULT_UPDATE_INTERVAL_HOURS,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=update_interval_hours),
        )
        self.client = client
        self.utility_id = utility_id
        self.utility_name = utility_name
        self.email = email
        self.password = password
        self._accumulated_total_gal = 0.0
        self._last_period_gal: float | None = None

    @property
    def total_gal(self) -> float:
        """Cumulative water use in gallons (meter read, or accumulated)."""
        if self.data:
            meter = self.data.get("meter_read_gal")
            if isinstance(meter, (int, float)):
                return float(meter)
        return self._accumulated_total_gal

    def seed_total(self, value: float) -> None:
        """Restore the accumulated total from the sensor's previous state."""
        if value > self._accumulated_total_gal:
            self._accumulated_total_gal = value

    async def _async_update_data(self) -> dict:
        if not self.client.logged_in:
            try:
                await self.client.login(self.utility_id, self.email, self.password)
            except AquaTraxAuthError as err:
                raise UpdateFailed(f"AquaTrax sign-in failed: {err}") from err
            except AquaTraxConnectionError as err:
                raise UpdateFailed(f"Could not reach AquaTrax: {err}") from err
        try:
            usage = await self.client.fetch_usage()
        except AquaTraxAuthError:
            # Session may have expired; try once more with a fresh sign-in.
            self.client._logged_in = False
            try:
                await self.client.login(self.utility_id, self.email, self.password)
                usage = await self.client.fetch_usage()
            except AquaTraxAuthError as err:
                raise UpdateFailed(f"AquaTrax sign-in failed: {err}") from err
            except AquaTraxConnectionError as err:
                raise UpdateFailed(f"Could not reach AquaTrax: {err}") from err
        except AquaTraxConnectionError as err:
            raise UpdateFailed(f"Could not reach AquaTrax: {err}") from err

        self._accumulate(usage)
        usage["total_gal"] = self.total_gal
        return usage

    def _accumulate(self, usage: dict) -> None:
        """Maintain the running total when the portal shows no meter read."""
        if isinstance(usage.get("meter_read_gal"), (int, float)):
            return
        period = usage.get("period_gal")
        if not isinstance(period, (int, float)):
            period = usage.get("month_gal")
        if not isinstance(period, (int, float)):
            return
        if self._last_period_gal is None:
            self._accumulated_total_gal += float(period)
        elif period >= self._last_period_gal:
            self._accumulated_total_gal += float(period) - self._last_period_gal
        else:
            # Billing period reset: the new period's figure so far counts.
            self._accumulated_total_gal += float(period)
        self._last_period_gal = float(period)
