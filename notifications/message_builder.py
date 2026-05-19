from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Mapping, TypedDict, Union, cast


Severity = Literal["critical", "high", "medium", "low"]
PatchImpact = Literal["BUFF", "NERF", "NEUTRAL"]


SEVERITY_COLORS: Mapping[Severity, int] = {
    "critical": 0xD7263D,
    "high": 0xFF7A00,
    "medium": 0xF2C14E,
    "low": 0x2E86AB,
}


class PriceOpportunityAlert(TypedDict, total=False):
    severity: Severity
    item_name: str
    price: Union[str, int, float]
    deviation_pct: Union[str, int, float]
    observed_at: Union[str, int, float, datetime]
    source: str
    notes: str


class PatchImpactResult(TypedDict, total=False):
    severity: Severity
    impact: PatchImpact
    patch_version: str
    observed_at: Union[str, int, float, datetime]
    source: str
    confidence: Union[str, int, float]
    buffed_items: list[str]
    nerfed_items: list[str]


class DiscordEmbedField(TypedDict):
    name: str
    value: str
    inline: bool


class DiscordEmbed(TypedDict, total=False):
    title: str
    description: str
    color: int
    fields: list[DiscordEmbedField]
    footer: dict[str, str]
    timestamp: str


def build_price_opportunity_embed(alert: PriceOpportunityAlert) -> DiscordEmbed:
    """
    Build a Discord embed for a price opportunity alert.

    Formatting-only responsibility:
    - Ensures a stable embed shape (title/description/fields/footer/timestamp).
    - Handles missing fields with safe placeholders.
    """
    severity: Severity = _coerce_severity(alert.get("severity"))

    item_name = _str_or_dash(alert.get("item_name"))
    price = _format_price(alert.get("price"))
    deviation = _format_deviation(alert.get("deviation_pct"))
    observed_at_dt = _parse_observed_at(alert.get("observed_at"))
    observed_at_field = _format_discord_timestamp(observed_at_dt)
    source = _str_or_dash(alert.get("source"))
    notes = _str_or_dash(alert.get("notes"))

    title = f"OKAZJA CENOWA • {item_name}" if item_name != "—" else "OKAZJA CENOWA"
    description = f"Cena {price} ({deviation} vs mediana)\nŹródło: {source}"

    return DiscordEmbed(
        title=title,
        color=SEVERITY_COLORS[severity],
        description=description,
        fields=[
            {"name": "Item", "value": item_name, "inline": True},
            {"name": "Price", "value": price, "inline": True},
            {"name": "Deviation", "value": deviation, "inline": True},
            {"name": "Observed at", "value": observed_at_field, "inline": True},
            {"name": "Source", "value": source, "inline": True},
            {"name": "Notes", "value": notes, "inline": False},
        ],
        footer={"text": "Stalcraft Market Analyzer"},
        timestamp=_format_iso_timestamp(observed_at_dt),
    )


def build_patch_impact_embed(result: PatchImpactResult) -> DiscordEmbed:
    """
    Build a Discord embed for patch impact (buff/nerf/neutral).

    Formatting-only responsibility:
    - Ensures a stable embed shape (title/description/fields/footer/timestamp).
    - Handles missing fields with safe placeholders.
    """
    severity: Severity = _coerce_severity(result.get("severity"))
    impact: PatchImpact = _coerce_impact(result.get("impact"))
    patch_version = _str_or_dash(result.get("patch_version"))
    source = _str_or_dash(result.get("source"))

    confidence = _format_confidence(result.get("confidence"))
    observed_at_dt = _parse_observed_at(result.get("observed_at"))
    observed_at_field = _format_discord_timestamp(observed_at_dt)

    buffed_items = _format_bulleted_list(result.get("buffed_items"))
    nerfed_items = _format_bulleted_list(result.get("nerfed_items"))

    title = (
        f"PATCH IMPACT • {patch_version} • {impact}"
        if patch_version != "—"
        else f"PATCH IMPACT • {impact}"
    )
    description = (
        f"Ocena wpływu patcha na rynek (confidence: {confidence})\nŹródło: {source}"
    )

    return DiscordEmbed(
        title=title,
        color=SEVERITY_COLORS[severity],
        description=description,
        fields=[
            {"name": "Patch", "value": patch_version, "inline": True},
            {"name": "Confidence", "value": confidence, "inline": True},
            {"name": "Observed at", "value": observed_at_field, "inline": True},
            {"name": "Buffed items", "value": buffed_items, "inline": False},
            {"name": "Nerfed items", "value": nerfed_items, "inline": False},
            {"name": "Source", "value": source, "inline": True},
        ],
        footer={"text": "Stalcraft Market Analyzer"},
        timestamp=_format_iso_timestamp(observed_at_dt),
    )


def _coerce_severity(value: Any) -> Severity:
    if value in SEVERITY_COLORS:
        return cast(Severity, value)
    return "low"


def _coerce_impact(value: Any) -> PatchImpact:
    if value in ("BUFF", "NERF", "NEUTRAL"):
        return cast(PatchImpact, value)
    return "NEUTRAL"


def _str_or_dash(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else "—"
    return str(value)


def _format_price(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not value.is_integer():
            return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " ₽"
        return f"{int(value):,}".replace(",", " ") + " ₽"
    s = _str_or_dash(value)
    return s if s == "—" else s


def _format_deviation(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        sign = "+" if value > 0 else ""
        return f"{sign}{value:.1f}%"
    s = _str_or_dash(value)
    return s if s == "—" else s


def _format_confidence(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    s = _str_or_dash(value)
    return s if s == "—" else s


def _parse_observed_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Allow ISO-8601 (with or without 'Z').
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _format_discord_timestamp(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    unix = int(dt.timestamp())
    return f"<t:{unix}:F>"


def _format_iso_timestamp(dt: datetime | None) -> str:
    if dt is None:
        # Discord embed.timestamp is optional; stable shape expects a string.
        # Use epoch as a safe, deterministic placeholder.
        return datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()
    return dt.astimezone(timezone.utc).isoformat()


def _format_bulleted_list(items: Any, *, limit: int = 5) -> str:
    if not items:
        return "—"
    if not isinstance(items, list):
        return _str_or_dash(items)

    cleaned: list[str] = []
    for item in items:
        s = _str_or_dash(item)
        if s != "—":
            cleaned.append(s)

    if not cleaned:
        return "—"

    shown = cleaned[:limit]
    lines = [f"• {x}" for x in shown]
    if len(cleaned) > limit:
        lines.append(f"+{len(cleaned) - limit} more")
    return "\n".join(lines)

