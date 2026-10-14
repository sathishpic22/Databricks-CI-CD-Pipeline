from pyspark import pipelines as dp
from pyspark.sql import functions as F


@dp.materialized_view(
    comment="Silver-layer refined order details with cleaned types and computed net_amount",
)
def order_details_silver():
    return (
        spark.read.table("`databrucks-ci-cd-pipelines`.sathish_skyuv.order_details")
        # Cast amount: remove commas then convert to double
        .withColumn("amount", F.regexp_replace(F.col("amount"), ",", "").cast("double"))
        # Standardise status: lowercase and fix known abbreviations
        .withColumn(
            "status",
            F.when(F.lower(F.col("status")).isin("pend"), F.lit("pending"))
            .otherwise(F.lower(F.col("status"))),
        )
        # Parse date and timestamp strings (try variants handle invalid dates like Feb 30)
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
