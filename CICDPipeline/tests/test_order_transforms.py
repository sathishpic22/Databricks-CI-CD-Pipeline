"""Tests for CICDPipeline.order_transforms.refine_orders."""

import datetime

import pytest
from pyspark.sql import Row, SparkSession
from pyspark.testing.utils import assertDataFrameEqual

from CICDPipeline.order_transforms import refine_orders


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _raw_row(
    amount="100",
    status="shipped",
    order_date="2024-06-15",
    updated_at="2024-06-15T10:30:00Z",
    discount_amount=5.0,
    shipping_amount=3.0,
):
    """Build a single raw-order dict with sensible defaults."""
    return {
        "amount": amount,
        "status": status,
        "order_date": order_date,
        "updated_at": updated_at,
        "discount_amount": discount_amount,
        "shipping_amount": shipping_amount,
    }


# ---------------------------------------------------------------------------
# amount cleaning
# ---------------------------------------------------------------------------

def test_amount_strips_commas_and_casts_to_double(spark: SparkSession):
    """Comma-formatted amounts like '1,234.56' should become 1234.56."""
    df = spark.createDataFrame([_raw_row(amount="1,234.56")])
    result = refine_orders(df).select("amount").first()
    assert result["amount"] == 1234.56


def test_amount_plain_number(spark: SparkSession):
    """A plain numeric string like '250' should cast to 250.0."""
    df = spark.createDataFrame([_raw_row(amount="250")])
    result = refine_orders(df).select("amount").first()
    assert result["amount"] == 250.0


def test_amount_null_stays_null(spark: SparkSession):
    """A null amount should remain null after transformation."""
    df = spark.createDataFrame([_raw_row(amount=None)])
    result = refine_orders(df).select("amount").first()
    assert result["amount"] is None


# ---------------------------------------------------------------------------
# status standardisation
# ---------------------------------------------------------------------------

def test_status_pend_becomes_pending(spark: SparkSession):
    """The abbreviation 'pend' (any case) should map to 'pending'."""
    df = spark.createDataFrame([_raw_row(status="pend")])
    result = refine_orders(df).select("status").first()
    assert result["status"] == "pending"


def test_status_pend_uppercase(spark: SparkSession):
    """'PEND' should also normalise to 'pending'."""
    df = spark.createDataFrame([_raw_row(status="PEND")])
    result = refine_orders(df).select("status").first()
    assert result["status"] == "pending"


def test_status_lowercased(spark: SparkSession):
    """Non-abbreviated statuses should be lowercased."""
    df = spark.createDataFrame([_raw_row(status="SHIPPED")])
    result = refine_orders(df).select("status").first()
    assert result["status"] == "shipped"


def test_status_already_lowercase(spark: SparkSession):
    """Already-lowercase statuses should pass through unchanged."""
    df = spark.createDataFrame([_raw_row(status="delivered")])
    result = refine_orders(df).select("status").first()
    assert result["status"] == "delivered"


# ---------------------------------------------------------------------------
# date / timestamp parsing
# ---------------------------------------------------------------------------

def test_order_date_parsed(spark: SparkSession):
    """A valid 'yyyy-MM-dd' string should parse to a date."""
    df = spark.createDataFrame([_raw_row(order_date="2024-01-31")])
    result = refine_orders(df).select("order_date").first()
    assert result["order_date"] == datetime.date(2024, 1, 31)


def test_order_date_invalid_returns_null(spark: SparkSession):
    """An invalid date like '2024-02-30' should yield null (try_to_timestamp)."""
    df = spark.createDataFrame([_raw_row(order_date="2024-02-30")])
    result = refine_orders(df).select("order_date").first()
    assert result["order_date"] is None


def test_updated_at_parsed(spark: SparkSession):
    """A valid ISO-8601 string should parse to a timestamp."""
    df = spark.createDataFrame([_raw_row(updated_at="2024-06-15T10:30:00Z")])
    result = refine_orders(df).select("updated_at").first()
    assert result["updated_at"] == datetime.datetime(2024, 6, 15, 10, 30, 0)


def test_updated_at_invalid_returns_null(spark: SparkSession):
    """A malformed timestamp should yield null."""
    df = spark.createDataFrame([_raw_row(updated_at="not-a-timestamp")])
    result = refine_orders(df).select("updated_at").first()
    assert result["updated_at"] is None


# ---------------------------------------------------------------------------
# net_amount computation
# ---------------------------------------------------------------------------

def test_net_amount_basic(spark: SparkSession):
    """net_amount = amount - discount_amount + shipping_amount."""
    df = spark.createDataFrame(
        [_raw_row(amount="100", discount_amount=10.0, shipping_amount=5.0)]
    )
    result = refine_orders(df).select("net_amount").first()
    assert result["net_amount"] == 95.0  # 100 - 10 + 5


def test_net_amount_rounds_to_two_decimals(spark: SparkSession):
    """The net_amount should be rounded to 2 decimal places."""
    df = spark.createDataFrame(
        [_raw_row(amount="33.333", discount_amount=1.111, shipping_amount=2.222)]
    )
    result = refine_orders(df).select("net_amount").first()
    # 33.333 - 1.111 + 2.222 = 34.444 -> rounded to 34.44
    assert result["net_amount"] == 34.44


def test_net_amount_null_when_amount_null(spark: SparkSession):
    """If amount is null, net_amount should also be null."""
    df = spark.createDataFrame([_raw_row(amount=None)])
    result = refine_orders(df).select("net_amount").first()
    assert result["net_amount"] is None


# ---------------------------------------------------------------------------
# full-row integration test
# ---------------------------------------------------------------------------

def test_refine_orders_full_row(spark: SparkSession):
    """End-to-end: verify all columns transform correctly together."""
    df = spark.createDataFrame(
        [
            _raw_row(
                amount="2,500.99",
                status="pend",
                order_date="2024-03-15",
                updated_at="2024-03-15T14:00:00Z",
                discount_amount=100.0,
                shipping_amount=25.50,
            )
        ]
    )
    row = refine_orders(df).first()

    assert row["amount"] == 2500.99
    assert row["status"] == "pending"
    assert row["order_date"] == datetime.date(2024, 3, 15)
    assert row["updated_at"] == datetime.datetime(2024, 3, 15, 14, 0, 0)
    # 2500.99 - 100.0 + 25.50 = 2426.49
    assert row["net_amount"] == 2426.49


def test_refine_orders_preserves_row_count(spark: SparkSession):
    """Transformation should not add or drop rows."""
    rows = [_raw_row(amount=str(i)) for i in range(10)]
    df = spark.createDataFrame(rows)
    assert refine_orders(df).count() == 10
