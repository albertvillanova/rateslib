import pytest
from datetime import datetime as dt
from pandas.testing import assert_frame_equal
from pandas import DataFrame, Series
import numpy as np

import context
from rateslib.periods import (
    Cashflow, FixedPeriod, FloatPeriod,
)
from rateslib.fx import FXRates
from rateslib.defaults import Defaults
from rateslib.curves import Curve, LineCurve


@pytest.fixture()
def curve():
    nodes = {
        dt(2022, 1, 1): 1.00,
        dt(2022, 4, 1): 0.99,
        dt(2022, 7, 1): 0.98,
        dt(2022, 10, 1): 0.97
    }
    return Curve(nodes=nodes, interpolation="log_linear")


@pytest.fixture()
def fxr():
    return FXRates({"usdnok": 10.0})


@pytest.fixture()
def rfr_curve():
    v1 = 1 / (1 + 0.01 / 365)
    v2 = v1 / (1 + 0.02 / 365)
    v3 = v2 / (1 + 0.03 / 365)
    v4 = v3 / (1 + 0.04 / 365)

    nodes = {
        dt(2022, 1, 1): 1.00,
        dt(2022, 1, 2): v1,
        dt(2022, 1, 3): v2,
        dt(2022, 1, 4): v3,
        dt(2022, 1, 5): v4,
    }
    return Curve(nodes=nodes, interpolation="log_linear", convention="act365f")


@pytest.fixture()
def line_curve():
    nodes = {
        dt(2021, 12, 31): -99,
        dt(2022, 1, 1): 1.00,
        dt(2022, 1, 2): 2.00,
        dt(2022, 1, 3): 3.00,
        dt(2022, 1, 4): 4.00,
        dt(2022, 1, 5): 5.00,
    }
    return LineCurve(nodes=nodes, interpolation="linear", convention="act365f")


class TestFloatPeriod:

    @pytest.mark.parametrize("spread_method, float_spread, expected", [
        ("none_simple", 100.0, 24744.478172244584),
        ("isda_compounding", 0.0, 24744.478172244584),
        ("isda_compounding", 100.0, 25053.484941157145),
        ("isda_flat_compounding", 100.0, 24747.211149828523),
    ])
    def test_float_period_analytic_delta(self, curve, spread_method, float_spread, expected):
        float_period = FloatPeriod(
            start=dt(2022, 1, 1),
            end=dt(2022, 4, 1),
            payment=dt(2022, 4, 3),
            notional=1e9,
            convention="Act360",
            termination=dt(2022, 4, 1),
            frequency="Q",
            float_spread=float_spread,
            spread_compound_method=spread_method,
        )
        result = float_period.analytic_delta(curve)
        assert abs(result - expected) < 1e-7

    @pytest.mark.parametrize("spread, crv, fx", [
        (4.00, True, 2.0),
        (None, False, 2.0),
        (4.00, True, 10.0),
        (None, False, 10.0),
    ])
    def test_float_period_cashflows(self, curve, fxr, spread, crv, fx):
        float_period = FloatPeriod(
            start=dt(2022, 1, 1),
            end=dt(2022, 4, 1),
            payment=dt(2022, 4, 3),
            notional=1e9,
            convention="Act360",
            termination=dt(2022, 4, 1),
            frequency="Q",
            float_spread=spread,
        )
        curve = curve if crv else None
        rate = None if curve is None else float(float_period.rate(curve))
        cashflow = None if rate is None else rate * -1e9 * float_period.dcf / 100
        expected = {
            Defaults.headers["type"]: "FloatPeriod",
            Defaults.headers["stub_type"]: "Regular",
            Defaults.headers["a_acc_start"]: dt(2022, 1, 1),
            Defaults.headers["a_acc_end"]: dt(2022, 4, 1),
            Defaults.headers["payment"]: dt(2022, 4, 3),
            Defaults.headers["notional"]: 1e9,
            Defaults.headers["currency"]: "USD",
            Defaults.headers["convention"]: "Act360",
            Defaults.headers["dcf"]: float_period.dcf,
            Defaults.headers["df"]: 0.9897791268897856 if crv else None,
            Defaults.headers["rate"]: rate,
            Defaults.headers["spread"]: 0 if spread is None else spread,
            Defaults.headers["npv"]: -10096746.871171726 if crv else None,
            Defaults.headers["cashflow"]: cashflow,
            Defaults.headers["fx"]: fx,
            Defaults.headers["npv_fx"]: -10096746.871171726 * fx if crv else None,
        }
        result = float_period.cashflows(
            curve if crv else None,
            fx=(2 if fx == 2 else fxr),
            base="_" if fx == 2 else "nok",
        )
        assert result == expected

    def test_spread_compound_raises(self):
        with pytest.raises(ValueError, match="`spread_compound_method`"):
            FloatPeriod(
                start=dt(2022, 1, 1),
                end=dt(2022, 4, 1),
                payment=dt(2022, 4, 3),
                frequency="Q",
                spread_compound_method="bad_vibes"
            )

    def test_spread_compound_calc_raises(self):
        period = FloatPeriod(
            start=dt(2022, 1, 1),
            end=dt(2022, 4, 1),
            payment=dt(2022, 4, 3),
            frequency="Q",
            spread_compound_method="none_simple",
            float_spread=1
        )
        period.spread_compound_method = "bad_vibes"
        with pytest.raises(ValueError, match="`spread_compound_method` must be in"):
            period._isda_compounded_rate_with_spread(Series([1, 2]), Series([1, 1]))

    def test_rfr_lockout_too_few_dates(self, curve):
        period = FloatPeriod(
            start=dt(2022, 1, 10),
            end=dt(2022, 1, 15),
            payment=dt(2022, 1, 15),
            frequency="M",
            fixing_method="rfr_lockout",
            method_param=6
        )
        with pytest.raises(ValueError, match="period has too few dates"):
            period.rate(curve)

    def test_fixing_method_raises(self):
        with pytest.raises(ValueError, match="`fixing_method`"):
            FloatPeriod(
                start=dt(2022, 1, 1),
                end=dt(2022, 4, 1),
                payment=dt(2022, 4, 3),
                frequency="Q",
                fixing_method="bad_vibes"
            )

    def test_float_period_npv(self, curve):
        float_period = FloatPeriod(
            start=dt(2022, 1, 1),
            end=dt(2022, 4, 1),
            payment=dt(2022, 4, 3),
            notional=1e9,
            convention="Act360",
            termination=dt(2022, 4, 1),
            frequency="Q",
        )
        result = float_period.npv(curve)
        assert abs(result + 9997768.95848275) < 1e-7

    @pytest.mark.parametrize("curve_type", ["curve", "line_curve"])
    def test_rfr_payment_delay_method(self, curve_type, rfr_curve, line_curve):
        curve = rfr_curve if curve_type == "curve" else line_curve
        period = FloatPeriod(dt(2022, 1, 1), dt(2022, 1, 4), dt(2022, 1, 4), "Q",
                             fixing_method="rfr_payment_delay")
        result = period.rate(curve)
        expected = ((1 + 0.01 / 365) * (1 + 0.02 / 365) * (
                    1 + 0.03 / 365) - 1) * 36500 / 3
        assert abs(result - expected) < 1e-12

    @pytest.mark.parametrize("curve_type", ["curve", "line_curve"])
    def test_rfr_payment_delay_method_with_fixings(self, curve_type, rfr_curve, line_curve):
        curve = rfr_curve if curve_type == "curve" else line_curve
        period = FloatPeriod(dt(2022, 1, 1), dt(2022, 1, 4), dt(2022, 1, 4), "Q",
                             fixing_method="rfr_payment_delay", fixings=[10, 8])
        result = period.rate(curve)
        expected = ((1 + 0.10 / 365) * (1 + 0.08 / 365) * (
                    1 + 0.03 / 365) - 1) * 36500 / 3
        assert abs(result - expected) < 1e-12

    @pytest.mark.parametrize("curve_type", ["curve", "line_curve"])
    def test_rfr_lockout_method(self, curve_type, rfr_curve, line_curve):
        curve = rfr_curve if curve_type == "curve" else line_curve
        period = FloatPeriod(dt(2022, 1, 1), dt(2022, 1, 4), dt(2022, 1, 4), "Q",
                             fixing_method="rfr_lockout", method_param=2)
        assert period._is_complex == True  # lockout requires all fixings.
        result = period.rate(curve)
        expected = ((1 + 0.01 / 365) * (1 + 0.01 / 365) * (
                    1 + 0.01 / 365) - 1) * 36500 / 3
        assert abs(result - expected) < 1e-12

        period = FloatPeriod(dt(2022, 1, 2), dt(2022, 1, 5), dt(2022, 1, 5), "Q",
                             fixing_method="rfr_lockout", method_param=1)
        result = period.rate(rfr_curve)
        expected = ((1 + 0.02 / 365) * (1 + 0.03 / 365) * (
                    1 + 0.03 / 365) - 1) * 36500 / 3
        assert abs(result - expected) < 1e-12

    @pytest.mark.parametrize("curve_type", ["curve", "line_curve"])
    def test_rfr_lockout_method_with_fixings(self, curve_type, rfr_curve, line_curve):
        curve = rfr_curve if curve_type == "curve" else line_curve
        period = FloatPeriod(dt(2022, 1, 1), dt(2022, 1, 4), dt(2022, 1, 4), "Q",
                             fixing_method="rfr_lockout", method_param=2,
                             fixings=[10, 8])
        result = period.rate(curve)
        expected = ((1 + 0.10 / 365) * (1 + 0.10 / 365) * (
                    1 + 0.10 / 365) - 1) * 36500 / 3
        assert abs(result - expected) < 1e-12

        period = FloatPeriod(dt(2022, 1, 2), dt(2022, 1, 5), dt(2022, 1, 5), "Q",
                             fixing_method="rfr_lockout", method_param=1,
                             fixings=[10, 8])
        result = period.rate(rfr_curve)
        expected = ((1 + 0.10 / 365) * (1 + 0.08 / 365) * (
                    1 + 0.08 / 365) - 1) * 36500 / 3
        assert abs(result - expected) < 1e-12

    @pytest.mark.parametrize("curve_type", ["curve", "line_curve"])
    def test_rfr_observation_shift_method(self, curve_type, rfr_curve, line_curve):
        curve = rfr_curve if curve_type == "curve" else line_curve
        period = FloatPeriod(dt(2022, 1, 2), dt(2022, 1, 5), dt(2022, 1, 5), "Q",
                             fixing_method="rfr_observation_shift", method_param=1)
        result = period.rate(curve)
        expected = ((1 + 0.01 / 365) * (1 + 0.02 / 365) * (
                    1 + 0.03 / 365) - 1) * 36500 / 3
        assert abs(result - expected) < 1e-12

        period = FloatPeriod(dt(2022, 1, 3), dt(2022, 1, 5), dt(2022, 1, 5), "Q",
                             fixing_method="rfr_observation_shift", method_param=2)
        result = period.rate(curve)
        expected = ((1 + 0.01 / 365) * (1 + 0.02 / 365) - 1) * 36500 / 2
        assert abs(result - expected) < 1e-12

    @pytest.mark.parametrize("curve_type", ["curve", "line_curve"])
    def test_rfr_observation_shift_method_with_fixings(
        self, curve_type, rfr_curve, line_curve
    ):
        curve = rfr_curve if curve_type == "curve" else line_curve
        period = FloatPeriod(dt(2022, 1, 2), dt(2022, 1, 5), dt(2022, 1, 5), "Q",
                             fixing_method="rfr_observation_shift", method_param=1,
                             fixings=[10, 8])
        result = period.rate(curve)
        expected = ((1 + 0.10 / 365) * (1 + 0.08 / 365) * (
                    1 + 0.03 / 365) - 1) * 36500 / 3
        assert abs(result - expected) < 1e-12

        period = FloatPeriod(dt(2022, 1, 3), dt(2022, 1, 5), dt(2022, 1, 5), "Q",
                             fixing_method="rfr_observation_shift", method_param=2,
                             fixings=[10, 8])
        result = period.rate(curve)
        expected = ((1 + 0.10 / 365) * (1 + 0.08 / 365) - 1) * 36500 / 2
        assert abs(result - expected) < 1e-12

    @pytest.mark.parametrize("curve_type", ["curve", "linecurve"])
    @pytest.mark.parametrize("method, expected, expected_date", [
        ("rfr_payment_delay", [1000616, 1000589, 1000328, 1000561], dt(2022, 1, 6)),
        ("rfr_observation_shift", [1500369, 1500328, 1500287, 1500246], dt(2022, 1, 4)),
        ("rfr_lockout", [1000548, 5001945, 0, 0], dt(2022, 1, 6)),
        ("rfr_lookback", [1000411, 1000383, 3000575, 1000328], dt(2022, 1, 4)),
    ])
    def test_rfr_fixings_array(self, curve_type, method, expected, expected_date):
        # tests the fixings array and the compounding for different types of curve
        # at different rates in the period.

        v1 = 1 / (1 + 0.01 / 365)
        v2 = v1 / (1 + 0.02 / 365)
        v3 = v2 / (1 + 0.03 / 365)
        v4 = v3 / (1 + 0.04 / 365)
        v5 = v4 / (1 + 0.045 * 3 / 365)
        v6 = v5 / (1 + 0.05 / 365)
        v7 = v6 / (1 + 0.055 / 365)

        nodes = {
            dt(2022, 1, 3): 1.00,
            dt(2022, 1, 4): v1,
            dt(2022, 1, 5): v2,
            dt(2022, 1, 6): v3,
            dt(2022, 1, 7): v4,
            dt(2022, 1, 10): v5,
            dt(2022, 1, 11): v6,
            dt(2022, 1, 12): v7,
        }
        curve = Curve(
            nodes=nodes,
            interpolation="log_linear",
            convention="act365f",
            calendar="bus",
        )

        line_curve = LineCurve(
            nodes={
                dt(2022, 1, 2): -99,
                dt(2022, 1, 3): 1.0,
                dt(2022, 1, 4): 2.0,
                dt(2022, 1, 5): 3.0,
                dt(2022, 1, 6): 4.0,
                dt(2022, 1, 7): 4.5,
                dt(2022, 1, 10): 5.0,
                dt(2022, 1, 11): 5.5,
            },
            interpolation="linear",
            convention="act365f",
            calendar="bus",
        )
        rfr_curve = curve if curve_type == "curve" else line_curve

        period = FloatPeriod(dt(2022, 1, 5), dt(2022, 1, 11), dt(2022, 1, 11), "Q",
                             fixing_method=method, method_param=2, convention="act365f",
                             notional=-1000000)
        rate, table = period._rfr_fixings_array(
            curve=rfr_curve, fixing_exposure=True
        )

        assert table["obs_dates"][1] == expected_date
        for i, val in table["notional"].iloc[:-1].items():
            assert abs(expected[i] - val) < 1

    def test_rfr_fixings_array_raises(self, rfr_curve):
        period = FloatPeriod(dt(2022, 1, 5), dt(2022, 1, 11), dt(2022, 1, 11), "Q",
                             fixing_method="rfr_payment_delay", method_param=2,
                             notional=-1000000)
        period.fixing_method = "bad_vibes"
        with pytest.raises(NotImplementedError, match="`fixing_method`"):
            period._rfr_fixings_array(rfr_curve)

    @pytest.mark.parametrize("method, expected", [
        ("rfr_payment_delay", 1000000),
        ("rfr_observation_shift", 1000000 / 3),
        ("rfr_lookback", 1000000 / 3)
    ])
    def test_rfr_fixings_array_single_period(self, method, expected):
        rfr_curve = Curve(
            nodes={dt(2022, 1, 3): 1.0, dt(2022, 1, 15): 0.9995},
            interpolation="log_linear",
            convention="act365f",
            calendar="bus",
        )
        period = FloatPeriod(dt(2022, 1, 10), dt(2022, 1, 11), dt(2022, 1, 11), "Q",
                             fixing_method=method, method_param=1,
                             notional=-1000000, convention="act365f")
        result = period.fixings_table(rfr_curve)
        assert abs(result["notional"][0] - expected) < 1

    @pytest.mark.parametrize("method, expected", [
        ("none_simple", ((1 + 0.01 / 365) * (1 + 0.02 / 365) * (
                1 + 0.03 / 365) - 1) * 36500 / 3 + 100 / 100),
        ("isda_compounding",
         ((1 + 0.02 / 365) * (1 + 0.03 / 365) * (1 + 0.04 / 365) - 1) * 36500 / 3),
        ("isda_flat_compounding", 3.000118724464),
    ])
    def test_rfr_compounding_float_spreads(self, method, expected, rfr_curve):
        period = FloatPeriod(
            start=dt(2022, 1, 1),
            end=dt(2022, 1, 4),
            payment=dt(2022, 1, 4),
            frequency="M",
            float_spread=100,
            spread_compound_method=method,
            convention="act365f",
        )
        result = period.rate(rfr_curve)
        assert abs(result - expected) < 1e-8

    def test_ibor_rate_line_curve(self, line_curve):
        period = FloatPeriod(
            start=dt(2022, 1, 5),
            end=dt(2022, 4, 5),
            payment=dt(2022, 4, 5),
            frequency="Q",
            fixing_method="ibor",
            method_param=2,
        )
        assert period._is_complex == False
        assert period.rate(line_curve) == 3.0

    def test_ibor_fixing_table(self, line_curve):
        float_period = FloatPeriod(
            start=dt(2022, 1, 4),
            end=dt(2022, 4, 4),
            payment=dt(2022, 4, 4),
            frequency="Q",
            fixing_method="ibor",
            method_param=2,
        )
        result = float_period.fixings_table(line_curve)
        expected = DataFrame({
            "obs_dates": [dt(2022, 1, 2)],
            "notional": [-1e6],
            "dcf": [None],
            "rates": [2.0]
        }).set_index("obs_dates")
        assert_frame_equal(expected, result)

    def test_ibor_fixings(self):
        curve = Curve({dt(2022, 1, 1): 1.0, dt(2025, 1, 1): 0.90}, calendar="bus")
        fixings = Series([1.00, 2.801, 1.00, 1.00], index=[
            dt(2023, 3, 1), dt(2023, 3, 2), dt(2023, 3, 3), dt(2023, 3, 6)
        ])
        float_period = FloatPeriod(
            start=dt(2023, 3, 6),
            end=dt(2023, 6, 6),
            payment=dt(2023, 6, 6),
            frequency="Q",
            fixing_method="ibor",
            method_param=2,
            fixings=fixings
        )
        result = float_period.rate(curve)
        assert result == 2.801

    def test_ibor_fixing_unavailable(self):
        curve = Curve({dt(2022, 1, 1): 1.0, dt(2025, 1, 1): 0.90}, calendar="bus")
        lcurve = LineCurve({dt(2022, 1, 1): 2.0, dt(2025, 1, 1): 4.0}, calendar="bus")
        fixings = Series([2.801], index=[dt(2023, 3, 1)])
        float_period = FloatPeriod(
            start=dt(2023, 3, 20),
            end=dt(2023, 6, 20),
            payment=dt(2023, 6, 20),
            frequency="Q",
            fixing_method="ibor",
            method_param=2,
            fixings=fixings
        )
        result = float_period.rate(curve)  # fixing occurs 18th Mar, not in `fixings`
        assert abs(result - 3.476095729528156) < 1e-5
        result = float_period.rate(lcurve)  # fixing occurs 18th Mar, not in `fixings`
        assert abs(result - 2.801094890510949) < 1e-5

    @pytest.mark.parametrize("float_spread", [0, 100])
    def test_ibor_rate_df_curve(self, float_spread, curve):
        period = FloatPeriod(
            start=dt(2022, 4, 1),
            end=dt(2022, 7, 1),
            payment=dt(2022, 7, 1),
            frequency="Q",
            fixing_method="ibor",
            method_param=2,
            float_spread=float_spread,
        )
        expected = (0.99 / 0.98 - 1) * 36000 / 91 + float_spread / 100
        assert period.rate(curve) == expected

    @pytest.mark.parametrize("float_spread", [0, 100])
    def test_ibor_rate_stub_df_curve(self, float_spread, curve):
        period = FloatPeriod(
            start=dt(2022, 4, 1),
            end=dt(2022, 5, 1),
            payment=dt(2022, 5, 1),
            frequency="Q",
            fixing_method="ibor",
            method_param=2,
            stub=True,
            float_spread=float_spread,
        )
        expected = (0.99 / curve[dt(2022, 5, 1)] - 1) * 36000 / 30 + float_spread / 100
        assert period.rate(curve) == expected

    def test_single_fixing_override(self, curve):
        period = FloatPeriod(
            start=dt(2022, 4, 1),
            end=dt(2022, 5, 1),
            payment=dt(2022, 5, 1),
            frequency="Q",
            fixing_method="ibor",
            method_param=2,
            stub=True,
            float_spread=100,
            fixings=7.5
        )
        expected = 7.5 + 1
        assert period.rate(curve) == expected

    @pytest.mark.parametrize("curve_type", ["curve", "linecurve"])
    def test_period_historic_fixings(self, curve_type, line_curve, rfr_curve):
        curve = rfr_curve if curve_type == "curve" else line_curve
        period = FloatPeriod(
            start=dt(2021, 12, 30),
            end=dt(2022, 1, 3),
            payment=dt(2022, 1, 3),
            frequency="Q",
            fixing_method="rfr_payment_delay",
            float_spread=100,
            fixings=[1.5, 2.5],
            convention="act365F",
        )
        expected = ((1 + 0.015 / 365) * (1 + 0.025 / 365) * (1 + 0.01 / 365) * (
                    1 + 0.02 / 365) - 1) * 36500 / 4 + 1
        assert period.rate(curve) == expected

    @pytest.mark.parametrize("curve_type", ["curve", "linecurve"])
    def test_period_historic_fixings_series(self, curve_type, line_curve, rfr_curve):
        curve = rfr_curve if curve_type == "curve" else line_curve
        fixings = Series(
            [99, 99, 1.5, 2.5],
            index=[dt(1995, 1, 1), dt(2021, 12, 29), dt(2021, 12, 30), dt(2021, 12, 31)]
        )
        period = FloatPeriod(
            start=dt(2021, 12, 30),
            end=dt(2022, 1, 3),
            payment=dt(2022, 1, 3),
            frequency="Q",
            fixing_method="rfr_payment_delay",
            float_spread=100,
            fixings=fixings,
            convention="act365F",
        )
        expected = ((1 + 0.015 / 365) * (1 + 0.025 / 365) * (1 + 0.01 / 365) * (
                    1 + 0.02 / 365) - 1) * 36500 / 4 + 1
        result = period.rate(curve)
        assert result == expected

    @pytest.mark.parametrize("curve_type", ["curve", "linecurve"])
    def test_period_historic_fixings_series_missing_warns(
            self, curve_type, line_curve, rfr_curve
    ):
        curve = rfr_curve if curve_type == "curve" else line_curve
        fixings = Series(
            [99, 99, 2.5],
            index=[dt(1995, 12, 1), dt(2021, 12, 30), dt(2022, 1, 1)]
        )
        period = FloatPeriod(
            start=dt(2021, 12, 30),
            end=dt(2022, 1, 3),
            payment=dt(2022, 1, 3),
            frequency="Q",
            fixing_method="rfr_payment_delay",
            float_spread=100,
            fixings=fixings,
            convention="act365F",
        )
        # expected = ((1 + 0.015 / 365) * (1 + 0.025 / 365) * (1 + 0.01 / 365) * (
        #             1 + 0.02 / 365) - 1) * 36500 / 4 + 1
        with pytest.warns(UserWarning):
            result = period.rate(curve)
        # assert result == expected

    def test_fixing_with_float_spread_warning(self, curve):
        float_period = FloatPeriod(
            start=dt(2022, 1, 4),
            end=dt(2022, 4, 4),
            payment=dt(2022, 4, 4),
            frequency="Q",
            fixing_method="rfr_payment_delay",
            spread_compound_method="isda_compounding",
            float_spread=100,
            fixings=1.0
        )
        with pytest.warns(UserWarning):
            result = float_period.rate(curve)
        assert result == 2.0

    def test_float_period_rate_raises(self):
        float_period = FloatPeriod(
            start=dt(2022, 1, 4),
            end=dt(2022, 4, 4),
            payment=dt(2022, 4, 4),
            frequency="Q",
        )
        with pytest.raises(TypeError, match="`curve` must be of type"):
            float_period.rate("bad_curve")

    def test_float_period_fixings_list_raises_on_ibor(self):
        with pytest.raises(ValueError, match="`fixings` can only be a single"):
            float_period = FloatPeriod(
                start=dt(2022, 1, 4),
                end=dt(2022, 4, 4),
                payment=dt(2022, 4, 4),
                frequency="Q",
                fixing_method="ibor",
                method_param=2,
                fixings=[1.00]
            )

    def test_rfr_fixings_table(self, curve):
        float_period = FloatPeriod(
            start=dt(2022, 12, 28),
            end=dt(2023, 1, 2),
            payment=dt(2023, 1, 2),
            frequency="M",
            fixings=[1.19, 1.19, -8.81],
        )
        result = float_period.fixings_table(curve)
        expected = DataFrame({
            "obs_dates": [
                dt(2022, 12, 28),
                dt(2022, 12, 29),
                dt(2022, 12, 30),
                dt(2022, 12, 31),
                dt(2023, 1, 1),
            ],
            "notional": [
                -1000011.27030,
                -1000011.27030,
                -1000289.11920,
                -999932.84380,
                -999932.84380,
            ],
            "dcf": [0.0027777777777777778] * 5,
            "rates": [1.19, 1.19, -8.81, 4.01364, 4.01364]
        }).set_index("obs_dates")
        assert_frame_equal(result, expected)

        curve._set_ad_order(order=1)
        # assert values are unchanged even if curve can calculate derivatives
        result = float_period.fixings_table(curve)
        assert_frame_equal(result, expected)

    def test_rfr_rate_fixings_series_monotonic_error(self):
        nodes = {
            dt(2022, 1, 1): 1.00,
            dt(2022, 4, 1): 0.99,
            dt(2022, 7, 1): 0.98,
            dt(2022, 10, 1): 0.97
        }
        curve = Curve(nodes=nodes, interpolation="log_linear")
        fixings = Series(
            [99, 2.25, 2.375, 2.5],
            index=[dt(1995, 12, 1), dt(2021, 12, 30), dt(2022, 12, 31), dt(2022, 1, 1)]
        )
        period = FloatPeriod(
            start=dt(2021, 12, 30),
            end=dt(2022, 1, 3),
            payment=dt(2022, 1, 3),
            frequency="Q",
            fixing_method="rfr_payment_delay",
            float_spread=100,
            fixings=fixings,
            convention="act365F",
        )
        with pytest.raises(ValueError, match="`fixings` as a Series"):
            period.rate(curve)

    @pytest.mark.parametrize("scm, exp", [
        ("none_simple", True),
        ("isda_compounding", False),
    ])
    def test_float_spread_affects_fixing_exposure(self, scm, exp):
        nodes = {
            dt(2022, 1, 1): 1.00,
            dt(2022, 4, 1): 0.99,
            dt(2022, 7, 1): 0.98,
            dt(2022, 10, 1): 0.97
        }
        curve = Curve(nodes=nodes, interpolation="log_linear")
        period = FloatPeriod(
            start=dt(2022, 1, 1),
            end=dt(2022, 7, 1),
            payment=dt(2022, 7, 1),
            frequency="S",
            fixing_method="rfr_payment_delay",
            float_spread=0,
            convention="act365F",
            spread_compound_method=scm,
        )
        table = period.fixings_table(curve)
        period.float_spread = 200
        table2 = period.fixings_table(curve)
        assert (table["notional"][0] == table2["notional"][0]) == exp

    def test_custom_interp_rate_nan(self):
        float_period = FloatPeriod(
            start=dt(2022, 12, 28),
            end=dt(2023, 1, 2),
            payment=dt(2023, 1, 2),
            frequency="M",
            fixings=[1.19, 1.19],
        )
        def interp(date, nodes):
            if date < dt(2023, 1 ,1):
                return None
            return 2.0
        curve = LineCurve({dt(2023, 1, 1): 3.0, dt(2023, 2, 1): 2.0},
                          interpolation=interp)
        with pytest.raises(ValueError, match="RFRs could not be calculated"):
            result = float_period.fixings_table(curve)

    def test_method_param_raises(self):
        with pytest.raises(ValueError, match='`method_param` must be >0 for "rfr_lock'):
            float_period = FloatPeriod(
                start=dt(2022, 1, 4),
                end=dt(2022, 4, 4),
                payment=dt(2022, 4, 4),
                frequency="Q",
                fixing_method="rfr_lockout",
                method_param=0,
                fixings=[1.00]
            )


class TestFixedPeriod:

    def test_fixed_period_analytic_delta(self, curve, fxr):
        fixed_period = FixedPeriod(
            start=dt(2022, 1, 1),
            end=dt(2022, 4, 1),
            payment=dt(2022, 4, 3),
            notional=1e9,
            convention="Act360",
            termination=dt(2022, 4, 1),
            frequency="Q",
            currency="usd"
        )
        result = fixed_period.analytic_delta(curve)
        assert abs(result - 24744.478172244584) < 1e-7

        result = fixed_period.analytic_delta(curve, curve, fxr, "nok")
        assert abs(result - 247444.78172244584) < 1e-7


    def test_fixed_period_analytic_delta_fxr_base(self, curve, fxr):
        fixed_period = FixedPeriod(
            start=dt(2022, 1, 1),
            end=dt(2022, 4, 1),
            payment=dt(2022, 4, 3),
            notional=1e9,
            convention="Act360",
            termination=dt(2022, 4, 1),
            frequency="Q",
            currency="usd"
        )
        fxr = FXRates({"usdnok": 10.0}, base="NOK")
        result = fixed_period.analytic_delta(curve, curve, fxr)
        assert abs(result - 247444.78172244584) < 1e-7

    @pytest.mark.parametrize("rate, crv, fx", [
        (4.00, True, 2.0),
        (None, False, 2.0),
        (4.00, True, 10),
        (None, False, 10),
    ])
    def test_fixed_period_cashflows(self, curve, fxr, rate, crv, fx):
        # also test the inputs to fx as float and as FXRates (10 is for
        fixed_period = FixedPeriod(
            start=dt(2022, 1, 1),
            end=dt(2022, 4, 1),
            payment=dt(2022, 4, 3),
            notional=1e9,
            convention="Act360",
            termination=dt(2022, 4, 1),
            frequency="Q",
            fixed_rate=rate,
        )

        cashflow = None if rate is None else rate * -1e9 * fixed_period.dcf / 100
        expected = {
            Defaults.headers["type"]: "FixedPeriod",
            Defaults.headers["stub_type"]: "Regular",
            Defaults.headers["a_acc_start"]: dt(2022, 1, 1),
            Defaults.headers["a_acc_end"]: dt(2022, 4, 1),
            Defaults.headers["payment"]: dt(2022, 4, 3),
            Defaults.headers["notional"]: 1e9,
            Defaults.headers["currency"]: "USD",
            Defaults.headers["convention"]: "Act360",
            Defaults.headers["dcf"]: fixed_period.dcf,
            Defaults.headers["df"]: 0.9897791268897856 if crv else None,
            Defaults.headers["rate"]: rate,
            Defaults.headers["spread"]: None,
            Defaults.headers["npv"]: -9897791.268897858 if crv else None,
            Defaults.headers["cashflow"]: cashflow,
            Defaults.headers["fx"]: fx,
            Defaults.headers["npv_fx"]: -9897791.268897858 * fx if crv else None,
        }
        result = fixed_period.cashflows(
            curve if crv else None,
            fx=(2 if fx == 2 else fxr),
            base="_" if fx == 2 else "nok",
        )
        assert result == expected

    def test_fixed_period_npv(self, curve, fxr):
        fixed_period = FixedPeriod(
            start=dt(2022, 1, 1),
            end=dt(2022, 4, 1),
            payment=dt(2022, 4, 3),
            notional=1e9,
            convention="Act360",
            termination=dt(2022, 4, 1),
            frequency="Q",
            fixed_rate=4.00,
            currency="usd",
        )
        result = fixed_period.npv(curve)
        assert abs(result + 9897791.268897833) < 1e-7

        result = fixed_period.npv(curve, curve, fxr, "nok")
        assert abs(result + 98977912.68897833) < 1e-6


class TestCashflow:

    def test_cashflow_analytic_delta(self, curve):
        cashflow = Cashflow(notional=1e6, payment=dt(2022, 1, 1))
        assert cashflow.analytic_delta(curve) == 0


    @pytest.mark.parametrize("crv, fx", [
        (True, 2.0),
        (False, 2.0),
        (True, 10.0),
        (False, 10.0),
    ])
    def test_cashflow_cashflows(self, curve, fxr, crv, fx):
        cashflow = Cashflow(notional=1e9, payment=dt(2022, 4, 3))
        curve = curve if crv else None
        expected = {
            Defaults.headers["type"]: "Cashflow",
            Defaults.headers["stub_type"]: None,
            Defaults.headers["a_acc_start"]: None,
            Defaults.headers["a_acc_end"]: None,
            Defaults.headers["payment"]: dt(2022, 4, 3),
            Defaults.headers["currency"]: "USD",
            Defaults.headers["notional"]: 1e9,
            Defaults.headers["convention"]: None,
            Defaults.headers["dcf"]: None,
            Defaults.headers["df"]: 0.9897791268897856 if crv else None,
            Defaults.headers["rate"]: None,
            Defaults.headers["spread"]: None,
            Defaults.headers["npv"]: -989779126.8897856 if crv else None,
            Defaults.headers["cashflow"]: -1e9,
            Defaults.headers["fx"]: fx,
            Defaults.headers["npv_fx"]: -989779126.8897856 * fx if crv else None,
        }
        result = cashflow.cashflows(
            curve if crv else None,
            fx=(2 if fx == 2 else fxr),
            base="_" if fx == 2 else "nok",
        )
        assert result == expected



def test_base_period_dates_raise():
    with pytest.raises(ValueError):
        _ = FixedPeriod(dt(2023, 1, 1), dt(2022, 1, 1), dt(2024, 1, 1), "Q")
