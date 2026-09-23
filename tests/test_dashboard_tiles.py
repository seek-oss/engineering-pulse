"""Focused dashboard tiles evaluate query-value formulas and colour bands."""

from scripts.dashboard_tiles import WidgetSpec, build_tiles, eval_formula, titles_match
from scripts.dashboards_plugin import ColorRule


def _row(title: str, subquery: str, latest: float) -> dict:
    return {
        "widget_title": title,
        "subquery": subquery,
        "series": [{"latest": latest}],
    }


SYSTEMS = WidgetSpec(
    title="Systems Assessed",
    formula="clamp_max((query2 / (query2 + query1)) * 100, 100)",
    unit="percent",
    precision=0,
)
FITNESS = WidgetSpec(
    title="Tech Fitness Score",
    formula="query2 / query1 * 100",
    unit="percent",
    precision=0,
)
RULES = (
    ColorRule("Tech Fitness Score", "< 50%", "50–75%", "> 75%"),
    ColorRule("System assessed", "< 50%", "50–80%", "> 80%"),
)


class TestFormula:
    def test_systems_assessed_is_the_percentage(self):
        value = eval_formula(
            SYSTEMS.formula or "",
            {"query2": 3.0, "query1": 1.0},
        )
        assert value == 75.0

    def test_divide_by_zero_is_blank(self):
        assert eval_formula("query2 / query1 * 100", {"query2": 1.0, "query1": 0.0}) is None


class TestFocusTiles:
    def test_percentage_and_colour_and_skips_other_widgets(self):
        results = [
            _row("Engineers", "query1", 21),
            _row("Tech Fitness Score", "query2", 45),
            _row("Tech Fitness Score", "query1", 94.5),
            _row("Systems Assessed", "query2", 3),
            _row("Systems Assessed", "query1", 1),
            _row("Tech Fitness Score", "query2", 135),
        ]
        tiles = build_tiles(
            results,
            focus=("Tech Fitness", "System assessed", "Incidents per deployment"),
            color_rules=RULES,
            specs={
                "Tech Fitness Score": FITNESS,
                "Systems Assessed": SYSTEMS,
                "Incidents Per Deployment": WidgetSpec(
                    "Incidents Per Deployment", "query1 / incidents", None, 2
                ),
            },
        )
        assert [tile.title for tile in tiles] == [
            "Tech Fitness Score",
            "Systems Assessed",
            "Incidents Per Deployment",
        ]
        assert tiles[0].display == "48%"
        assert tiles[0].css_class == "tile-red"
        assert tiles[1].display == "75%"
        assert tiles[1].css_class == "tile-yellow"
        assert tiles[2].display == "—"
        assert tiles[2].css_class == "tile-grey"

    def test_without_focus_keeps_the_first_raw_value(self):
        tiles = build_tiles(
            [
                _row("CPU", "query1", 80),
                _row("CPU", "query2", 100),
            ]
        )
        assert len(tiles) == 1
        assert tiles[0].display == "80.0"
        assert tiles[0].css_class == "tile-green"

    def test_catalogue_spelling_matches_catalog(self):
        assert titles_match("Catalogue", "Catalog Quality")
        assert titles_match("System assessed", "Systems Assessed")
