import os

os.environ.setdefault(
    "DATABASE_URL",
    "mysql+pymysql://root:root123@127.0.0.1:3307/test_platform_test?charset=utf8mb4",
)
