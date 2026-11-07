"""Sensors for the AquaTrax integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_entity import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AquaTraxCoordinator

DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="total_gal",
        name="Water Total",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.GALLONS,
    ),
    SensorEntityDescription(
        key="today_gal",
        name="Water Today",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.GALLONS,
    ),
    SensorEntityDescription(
        key="week_gal",
        name="Water This Week",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.GALLONS,
    ),
    SensorEntityDescription(
        key="month_gal",
        name="Water This Month",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.GALLONS,
    ),
    SensorEntityDescription(
        key="period_gal",
        name="Water Billing Period",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.GALLONS,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AquaTrax sensors from a config entry."""
    coordinator: AquaTraxCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AquaTraxSensor(coordinator, description) for description in DESCRIPTIONS
    )


class AquaTraxSensor(CoordinatorEntity[AquaTraxCoordinator], SensorEntity, RestoreEntity):
    """A water usage sensor fed by the AquaTrax portal."""

    def __init__(
        self, coordinator: AquaTraxCoordinator, description: SensorEntityDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.email}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.email)},
            "name": f"AquaTrax ({coordinator.utility_name})",
            "manufacturer": "AquaTrax",
            "model": "Customer Portal",
        }

    async def async_added_to_hass(self) -> None:
        """Restore the running total after a restart."""
        await super().async_added_to_hass()
        if self.entity_description.key == "total_gal":
            if (state := await self.async_get_last_state()) is not None:
                try:
                    self.coordinator.seed_total(float(state.state))
                except (TypeError, ValueError):
                    pass

    @property
    def native_value(self) -> float | None:
        """Return the sensor value in gallons."""
        if self.entity_description.key == "total_gal":
            return round(self.coordinator.total_gal, 2)
        value = (self.coordinator.data or {}).get(self.entity_description.key)
        if isinstance(value, (int, float)):
            return round(float(value), 2)
        return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return portal details as attributes."""
        data = self.coordinator.data or {}
        return {
            "utility": self.coordinator.utility_name,
            "portal_unit": data.get("unit"),
            "dashboard_url": data.get("dashboard_url"),
        }
