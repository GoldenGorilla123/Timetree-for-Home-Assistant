"""Calendar platform for TimeTree."""
from datetime import datetime, date
import logging
from zoneinfo import ZoneInfo

from homeassistant.components.calendar import (
    CalendarEntity, 
    CalendarEvent, 
    CalendarEntityFeature
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_CALENDAR_NAME,
    CONF_CALENDAR_USERS,
    CONF_CALENDAR_LABELS,
    CONF_SYNC_MODE,
    SYNC_MODE_INDIVIDUAL,
    UNASSIGNED_MEMBER_ID,
)
from .coordinator import TimeTreeCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the calendar entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    calendar_name = entry.data[CONF_CALENDAR_NAME]
    if entry.data.get(CONF_SYNC_MODE) != SYNC_MODE_INDIVIDUAL:
        async_add_entities([TimeTreeCalendarEntity(coordinator, calendar_name)])
        return

    users = entry.data.get(CONF_CALENDAR_USERS, [])
    entities = [
        TimeTreeCalendarEntity(coordinator, f"{calendar_name} ({user['name']})", user["id"])
        for user in users
        if user.get("id") is not None and user.get("name")
    ]
    entities.append(
        TimeTreeCalendarEntity(
            coordinator,
            f"{calendar_name} (Unassigned)",
            UNASSIGNED_MEMBER_ID,
        )
    )
    async_add_entities(entities)


class TimeTreeCalendarEntity(CalendarEntity):
    """Representation of a TimeTree Calendar."""

    _attr_has_entity_name = True
    _attr_supported_features = CalendarEntityFeature.CREATE_EVENT

    def __init__(self, coordinator: TimeTreeCoordinator, name: str, member_id=None):
        """Initialize the entity."""
        self.coordinator = coordinator
        self._attr_name = name
        self._member_id = member_id
        self._labels = {
            label["id"]: label
            for label in coordinator.entry.data.get(CONF_CALENDAR_LABELS, [])
            if label.get("id") is not None
        }
        self._attr_unique_id = f"{coordinator.calendar_id}_{member_id or 'all'}"

    @property
    def extra_state_attributes(self):
        """Return the labels available in the TimeTree calendar."""
        return {
            "member_id": self._member_id,
            "labels": [label for label in self._labels.values() if label.get("name")],
        }
    
    @property
    def event(self):
        """Return the next upcoming event."""
        now = dt_util.now()
        events = self._filtered_events()
        
        future_events = []
        for e in events:
            if e["all_day"]:
                end_val = e["end"]
                if isinstance(end_val, datetime):
                    end_val = end_val.date()
                if end_val >= now.date():
                    future_events.append(e)
            else:
                if e["end"] > now:
                    future_events.append(e)
        
        if not future_events:
            return None
            
        def sort_key(x):
            start = x["start"]
            if isinstance(start, datetime):
                return start
            return dt_util.start_of_local_day(
                datetime.combine(start, datetime.min.time())
            )

        next_event = min(future_events, key=sort_key)
        return self._build_calendar_event(next_event)

    async def async_get_events(self, hass, start_date, end_date):
        """Return calendar events within a range."""
        if self.coordinator.data is None:
            await self.coordinator.async_request_refresh()
            
        events = []
        for event_data in self._filtered_events():
            ev_start = event_data["start"]
            ev_end = event_data["end"]
            
            if event_data["all_day"]:
                query_start_date = start_date.date()
                query_end_date = end_date.date()
                if ev_start < query_end_date and ev_end > query_start_date:
                    events.append(self._build_calendar_event(event_data))
            else:
                if ev_start < end_date and ev_end > start_date:
                    events.append(self._build_calendar_event(event_data))
                
        return events

    async def async_create_event(self, **kwargs):
        """Add a new event to the calendar."""
        summary = kwargs.get("summary", "New Event")
        description = kwargs.get("description", "")
        location = kwargs.get("location", "")
        start_dt = kwargs.get("start_date_time")
        end_dt = kwargs.get("end_date_time")
        
        if not start_dt:
            start_date = kwargs.get("start_date")
            end_date = kwargs.get("end_date")
            all_day = True
            dt_start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            dt_end = datetime.combine(end_date, datetime.min.time()).replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        else:
            all_day = False
            dt_start = start_dt
            dt_end = end_dt

        start_ms = int(dt_start.timestamp() * 1000)
        end_ms = int(dt_end.timestamp() * 1000)
        
        event_payload = {
            "summary": summary,
            "description": description,
            "location": location,
            "all_day": all_day,
            "start_at": start_ms,
            "end_at": end_ms,
            "timezone": str(dt_util.DEFAULT_TIME_ZONE)
        }
        if self._member_id not in (None, UNASSIGNED_MEMBER_ID):
            event_payload["attendees"] = [self._member_id]

        try:
            await self.coordinator.api.async_create_event(self.coordinator.calendar_id, event_payload)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error creating event: %s", err)
            # This raises a visible error in the HA UI
            raise HomeAssistantError(f"TimeTree API Failed: {err}") from err

    def _build_calendar_event(self, event_data):
        label = self._labels.get(event_data.get("label_id"))
        description = event_data["description"] or ""
        if label and label.get("name"):
            description = f"Label: {label['name']}\n{description}".strip()

        return CalendarEvent(
            summary=event_data["summary"],
            start=event_data["start"],
            end=event_data["end"],
            location=event_data["location"],
            description=description or None,
            uid=event_data["uid"],
            rrule=event_data["recurrences"][0] if event_data["recurrences"] else None
        )

    def _filtered_events(self):
        """Return all events or only events assigned to this member."""
        events = self.coordinator.data or []
        if self._member_id is None:
            return events
        if self._member_id == UNASSIGNED_MEMBER_ID:
            return [event for event in events if not event.get("attendees", [])]
        return [event for event in events if self._member_id in event.get("attendees", [])]