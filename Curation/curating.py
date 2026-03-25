
import pyodbc
import pandas as pd
from sqlalchemy import create_engine
from urllib.parse import quote_plus

# --------------------------
# CONNECTION SETUP
# --------------------------
server = r'QUAN-CORNER\SQLEXPRESS'
database = "dwh"

# Read connection
conn = pyodbc.connect(
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={server};"
    f"DATABASE={database};"
    "Trusted_Connection=yes;"
)

cursor = conn.cursor()

connection_string = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={server};"
    f"DATABASE={database};"
    "Trusted_Connection=yes;"
)
engine = create_engine(
    f"mssql+pyodbc:///?odbc_connect={quote_plus(connection_string)}"
)

# -------------------------------------------------------------------------
# CUSTOMER DATAFRAME
customer_crm_df = pd.read_sql("SELECT * FROM transformation.cust_info", conn)
customer_erp_df = pd.read_sql("SELECT * FROM transformation.cust_az12", conn)
location_erp_df = pd.read_sql("SELECT * FROM transformation.loc_a101", conn)

print(customer_crm_df.columns)
print(customer_erp_df.columns)
print(location_erp_df.columns)

# Join CRM customers with ERP customers
df = pd.merge(
    left=customer_crm_df,
    right=customer_erp_df,
    how="left",
    left_on="cst_key",
    right_on="CID"
)

print(df.head())

# Join with location table
df = pd.merge(
    left=df,
    right=location_erp_df,
    how="left",
    left_on="CID",
    right_on="CID",
    suffixes=("", "_loc")
)

print(df.head())

# Build dim_customers
dim_customers = pd.DataFrame({
    "customer_id": df["cst_id"],
    "customer_number": df["cst_key"],
    "first_name": df["cst_firstname"],
    "last_name": df["cst_lastname"],
    "country": df["CNTRY"],
    "marital_status": df["cst_marital_status"],
    "gender": df["GEN"],
    "birthdate": df["BDATE"],
    "create_date": df["cst_create_date"]
})

print(dim_customers.head(10))

dim_customers = dim_customers.sort_values("customer_id").reset_index(drop=True)
dim_customers.insert(0, "customer_key", dim_customers.index + 1)

# -------------------------------------------------------------------------
# WRITE CUSTOMER TABLE

cursor.execute("""
IF NOT EXISTS (
    SELECT * FROM sys.schemas WHERE name = 'curated'
)
BEGIN
    EXEC('CREATE SCHEMA curated')
END
""")
conn.commit()

dim_customers.to_sql(
    name="dim_customers",
    con=engine,
    schema="curated",
    if_exists="replace",
    index=False
)

print("Cleaned data loaded into curated.dim_customers")

# -------------------------------------------------------------------------
# PRODUCT DATAFRAME

product_crm_df = pd.read_sql("SELECT * FROM transformation.prd_info", conn)
category_erp_df = pd.read_sql("SELECT * FROM transformation.px_cat_g1v2", conn)

print(product_crm_df.columns)
print(category_erp_df.columns)

# Join product info with categories
df = pd.merge(
    left=product_crm_df,
    right=category_erp_df,
    how="left",
    left_on="cat_id",
    right_on="ID"
)

print(df.head())

# Build dim_products
dim_products = pd.DataFrame({
    "product_number": df["prd_key"],
    "product_name": df["prd_nm"],
    "category_id": df["cat_id"],
    "category": df["CAT"],
    "subcategory": df["SUBCAT"],
    "maintenance": df["MAINTENANCE"],
    "cost": df["prd_cost"],
    "product_line": df["prd_line"],
    "start_date": df["prd_start_dt"],
    "end_date": df["prd_end_dt"]
})

print(dim_products.head(10))

dim_products = dim_products.sort_values("product_number").reset_index(drop=True)
dim_products.insert(0, "product_key", dim_products.index + 1)

# -------------------------------------------------------------------------
# WRITE PRODUCT TABLE

dim_products.to_sql(
    name="dim_products",
    con=engine,
    schema="curated",
    if_exists="replace",
    index=False
)

print("Cleaned data loaded into curated.dim_products")

# -------------------------------------------------------------------------
# SALES DATAFRAME

sales_details_df = pd.read_sql("SELECT * FROM transformation.sales_details", conn)
dim_products_df = pd.read_sql("SELECT * FROM curated.dim_products", conn)
dim_customers_df = pd.read_sql("SELECT * FROM curated.dim_customers", conn)

print(sales_details_df.columns)
print(dim_products_df.columns)
print(dim_customers_df.columns)

# Join sales with products
df = pd.merge(
    left=sales_details_df,
    right=dim_products_df[["product_key", "product_number"]],
    how="left",
    left_on="sls_prd_key",
    right_on="product_number"
)

# Join sales with customers
df = pd.merge(
    left=df,
    right=dim_customers_df[["customer_key", "customer_id"]],
    how="left",
    left_on="sls_cust_id",
    right_on="customer_id"
)

print(df.head())

# Build fact_sales
fact_sales = pd.DataFrame({
    "product_key": df["product_key"],
    "customer_key": df["customer_key"],
    "order_number": df["sls_ord_num"],
    "order_date": df["sls_order_dt"],
    "shipping_date": df["sls_ship_dt"],
    "due_date": df["sls_due_dt"],
    "sales": df["sls_sales"],
    "quantity": df["sls_quantity"],
    "price": df["sls_price"]
})

print(fact_sales.head(10))

fact_sales = fact_sales.reset_index(drop=True)
fact_sales.insert(0, "sales_key", fact_sales.index + 1)

# -------------------------------------------------------------------------
# WRITE FACT TABLE

fact_sales.to_sql(
    name="fact_sales",
    con=engine,
    schema="curated",
    if_exists="replace",
    index=False
)

print("Cleaned data loaded into curated.fact_sales")

# -------------------------------------------------------------------------
# CLOSE CONNECTIONS

cursor.close()
conn.close()
