"""Physical reference data and player-attribute schema.

The SkillCorner values below are position-group references from the A-League
2024/25 open-data aggregate. They are useful for synthetic generation and
sanity checks; they are NOT measurements of Premier League players.
"""

from __future__ import annotations

PHYSICAL_REFERENCE_SOURCE = "SkillCorner A-League 2024/25 positional reference"

# Full-match position-group means from SkillCorner Open Data.
PHYSICAL_REFERENCE_BY_ROLE: dict[str, dict[str, float]] = {
    "CB": {
        "meters_per_minute": 105.73,
        "hsr_distance_90": 394.73,
        "hsr_count_90": 36.61,
        "sprint_distance_90": 107.96,
        "sprint_count_90": 6.23,
        "high_accel_90": 4.63,
        "high_decel_90": 10.52,
        "psv99_kmh": 28.14,
    },
    "FB": {
        "meters_per_minute": 112.71,
        "hsr_distance_90": 597.08,
        "hsr_count_90": 55.59,
        "sprint_distance_90": 197.65,
        "sprint_count_90": 11.02,
        "high_accel_90": 6.62,
        "high_decel_90": 17.63,
        "psv99_kmh": 28.98,
    },
    "CM": {
        "meters_per_minute": 122.88,
        "hsr_distance_90": 544.25,
        "hsr_count_90": 46.59,
        "sprint_distance_90": 112.85,
        "sprint_count_90": 6.41,
        "high_accel_90": 3.75,
        "high_decel_90": 11.52,
        "psv99_kmh": 27.10,
    },
    "AM_W": {
        "meters_per_minute": 119.04,
        "hsr_distance_90": 599.75,
        "hsr_count_90": 56.47,
        "sprint_distance_90": 189.28,
        "sprint_count_90": 10.52,
        "high_accel_90": 6.35,
        "high_decel_90": 16.69,
        "psv99_kmh": 28.76,
    },
    "ST": {
        "meters_per_minute": 118.37,
        "hsr_distance_90": 561.70,
        "hsr_count_90": 52.65,
        "sprint_distance_90": 157.72,
        "sprint_count_90": 9.27,
        "high_accel_90": 6.38,
        "high_decel_90": 13.92,
        "psv99_kmh": 28.28,
    },
}

PLAYER_ATTRIBUTE_COLUMNS = (
    "height_cm",
    "preferred_foot",
    "max_speed_kmh",
    "meters_per_minute",
    "hsr_distance_90",
    "hsr_count_90",
    "sprint_distance_90",
    "sprint_count_90",
    "high_accel_90",
    "high_decel_90",
    "physical_source",
    "physical_is_observed",
)
