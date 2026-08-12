"""
generate_sample_data.py
------------------------
Creates data/sample_sales_data.xlsx: 90 days of daily sales data across
2 regions x 2 categories x 2 products, with a few deliberately injected
anomalies (a revenue spike and a revenue/orders crash) so the app has
something interesting to detect out of the box.
"""

import numpy as np
import pandas as pd

np.random.seed(42)

start_date = pd.Timestamp("2026-05-01")
n_days = 90
dates = pd.date_range(start_date, periods=n_days, freq="D")

regions = ["North", "South"]
categories = ["Electronics", "Apparel"]
products = {"Electronics": ["Laptop", "Headphones"], "Apparel": ["Jacket", "Sneakers"]}
segments = ["Retail", "Wholesale"]

rows = []
for date in dates:
    for region in regions:
        for category in categories:
            for product in products[category]:
                base_orders = np.random.poisson(30)
                unit_price = 800 if category == "Electronics" else 90
                revenue = base_orders * unit_price * np.random.uniform(0.9, 1.1)
                profit = revenue * np.random.uniform(0.15, 0.25)
                customers = max(1, int(base_orders * np.random.uniform(0.7, 0.95)))
                returns = np.random.poisson(1.5)
                cancellations = np.random.poisson(1.0)
                segment = np.random.choice(segments)

                rows.append({
                    "date": date, "region": region, "category": category, "product": product,
                    "customer_segment": segment, "orders": base_orders, "revenue": round(revenue, 2),
                    "profit": round(profit, 2), "customers": customers,
                    "returns": returns, "cancellations": cancellations,
                })

df = pd.DataFrame(rows)

# --- Inject anomalies -------------------------------------------------------
# 1) Revenue SPIKE in North/Electronics/Laptop on day 45 (e.g. a promo)
spike_date = dates[45]
mask = (df["date"] == spike_date) & (df["region"] == "North") & (df["product"] == "Laptop")
df.loc[mask, "revenue"] *= 2.8
df.loc[mask, "orders"] = (df.loc[mask, "orders"] * 2.2).astype(int)

# 2) Revenue CRASH across North region on day 70 (e.g. an outage/stockout)
crash_date = dates[70]
mask2 = (df["date"] == crash_date) & (df["region"] == "North")
df.loc[mask2, "revenue"] *= 0.35
df.loc[mask2, "orders"] = (df.loc[mask2, "orders"] * 0.4).astype(int)
df.loc[mask2, "cancellations"] += 8

df = df.sort_values(["date", "region", "category", "product"]).reset_index(drop=True)
df.to_excel("data/sample_sales_data.xlsx", index=False, engine="openpyxl")
print(f"Wrote data/sample_sales_data.xlsx with {len(df)} rows.")
