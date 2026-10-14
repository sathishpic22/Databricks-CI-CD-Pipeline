"""Order data transformation logic – silver-layer refinements."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def refine_orders(df: DataFrame) -> DataFrame:
    """Apply silver-layer refinements to raw order data.

    Transformations applied:
      - amount: strip commas and cast to double
      - status: lowercase; map abbreviation 'pend' → 'pending'
      - order_date: parse 'yyyy-MM-dd' string to date
      - updated_at: parse ISO-8601 string to timestamp
      - net_amount: amount − discount_amount + shipping_amount (rounded to 2 dp)
    """
    return (
        df
        # Cast amount: remove commas then convert to double
        .withColumn("amount", F.regexp_replace(F.col("amount"), ",", "").cast("double"))
        # Standardise status: lowercase + fix known abbreviations
        .withColumn(
            "status",
            F.when(F.lower(F.col("status")).isin("pend"), F.lit("pending"))
            .otherwise(F.lower(F.col("status"))),
        )
        # Parse date / timestamp strings
        .withColumn(
            "order_date",
            F.try_to_timestamp(F.col("order_date"), F.lit("yyyy-MM-dd")).cast("date"),
        )
        .withColumn(
            "updated_at",
            F.try_to_timestamp(F.col("updated_at"), F.lit("yyyy-MM-dd'T'HH:mm:ss'Z'")),
        )
        # Compute net amount after discount and shipping
        .withColumn(
            "net_amount",
            F.round(F.col("amount") - F.col("discount_amount") + F.col("shipping_amount"), 2),
        )
    )
