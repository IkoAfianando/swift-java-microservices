-- Per-language databases so Swift Fluent and Java JPA each manage their own schema
-- (avoids column-name conflicts e.g. password vs password_hash)

CREATE DATABASE swift_user_db;
CREATE DATABASE swift_product_db;
CREATE DATABASE swift_order_db;

CREATE DATABASE java_user_db;
CREATE DATABASE java_product_db;
CREATE DATABASE java_order_db;

GRANT ALL PRIVILEGES ON DATABASE swift_user_db    TO research;
GRANT ALL PRIVILEGES ON DATABASE swift_product_db TO research;
GRANT ALL PRIVILEGES ON DATABASE swift_order_db   TO research;
GRANT ALL PRIVILEGES ON DATABASE java_user_db     TO research;
GRANT ALL PRIVILEGES ON DATABASE java_product_db  TO research;
GRANT ALL PRIVILEGES ON DATABASE java_order_db    TO research;
