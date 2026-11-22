# Python Automation Guide: Kepware JSON & SQL Server Manipulation

> **Purpose**: Standalone, reusable technical reference guide with copy-pasteable Python scripts for automating Kepware KEPServerEX project configurations (`.json`) and SQL Server database schema/data operations (`pyodbc`).  
> **Reusability**: Use this guide across other Prometeon IIoT and Smart Manufacturing projects (Pneumatic panels, TBM, Extrusion, Calenders, Curing).

---

## Part 1: Manipulating Kepware KEPServerEX Project JSON Files

Kepware V6 supports full export/import of project configurations as JSON files (`File -> Export -> JSON`).

### Key Lessons & Best Practices
1. **UTF-8 with BOM (`utf-8-sig`)**:  
   Kepware project exports usually begin with a UTF-8 Byte Order Mark (BOM). Always open files in Python with `encoding='utf-8-sig'` to prevent `JSONDecodeError`.
2. **Preventing Kepware GUI Freeze on Project Open**:  
   When Kepware opens a project where a DataLogger group points to an unreachable DSN with `LOG_GROUP_ENABLED: true`, the runtime makes a blocking ODBC call that freezes the Kepware GUI for 30–60 seconds. Always set `datalogger.LOG_GROUP_ENABLED: false` when generating new groups so users can open the project smoothly.
3. **Preventing Column Mapping Overwrites**:  
   Kepware will wipe custom column mappings whenever someone changes the DSN in the GUI if `LOG_GROUP_REGENERATE_ALIAS_TABLE_ON_DSN_CHANGE` is `true`. Always lock this setting to `false` in code.
4. **Eliminating VTQ Bloat**:  
   By default, Kepware generates 4 database columns for every single tag (`_VALUE`, `_TIMESTAMP`, `_QUALITY`, `_NUMERICID`). Customizing the `column_mappings` list allows you to map only the single clean value column and a single shared timestamp column.

---

### Reusable Script 1: Clean Column Mapping & Clone Log Group

```python
"""
=============================================================================
Kepware DataLogger JSON Generator / Cloner
=============================================================================
Usage:
1. Loads an exported Kepware JSON file.
2. Updates an existing log group with clean, single-column mappings.
3. Clones the log group for a second machine with safe startup flags.
4. Saves to an updated JSON file.
"""

import json
import copy

INPUT_PROJECT  = "kepware_baseline.json"
OUTPUT_PROJECT = "kepware_revamped.json"

# Define the clean column mapping schema for Machine 1
CLEAN_MAPPINGS_M1 = {
    # Full Tag Path in Kepware                           : {"val": "Target SQL Column", "time": "Timestamp Column or Empty"}
    "MESNAC26.MESNAC 1.Global.Aux_ActualWeight_Online"  : {"val": "ActualWeight_Online", "time": ""},
    "MESNAC26.MESNAC 1.Global.C_MESRecord"             : {"val": "Trigger",             "time": "Timestamp"},
    "MESNAC26.MESNAC 1.Global.Data_GTLMOut.DATA"        : {"val": "Barcode",             "time": ""},
    "MESNAC26.MESNAC 1.Global.MCH_CODE.DATA"           : {"val": "MCH_CODE",            "time": ""}
}

# Define the clean column mapping schema for Machine 2
CLEAN_MAPPINGS_M2 = {
    "MESNAC27.MESNAC 2.Global.Aux_ActualWeight_Online"  : {"val": "ActualWeight_Online", "time": ""},
    "MESNAC27.MESNAC 2.Global.C_MESRecord"             : {"val": "Trigger",             "time": "Timestamp"},
    "MESNAC27.MESNAC 2.Global.Data_GTLMOut.DATA"        : {"val": "Barcode",             "time": ""},
    "MESNAC27.MESNAC 2.Global.MCH_CODE.DATA"           : {"val": "MCH_CODE",            "time": ""}
}

def build_kepware_column_mappings(mapping_dict):
    """Generates the Kepware DataLogger column_mappings JSON structure without VTQ bloat."""
    mappings = []
    idx = 1
    for item_id, cols in mapping_dict.items():
        mappings.append({
            "common.ALLTYPES_NAME": f"ColumnMapping{idx}",
            "datalogger.TABLE_ALIAS_LOG_ITEM_ID": item_id,
            "datalogger.TABLE_ALIAS_DATABASE_FIELD_NAME_NAME": "",
            "datalogger.TABLE_ALIAS_SQL_DATA_TYPE_NAME": 0,
            "datalogger.TABLE_ALIAS_SQL_LENGTH_NAME": 0,
            "datalogger.TABLE_ALIAS_DATABASE_FIELD_NAME_NUMERIC": "",
            "datalogger.TABLE_ALIAS_SQL_DATA_TYPE_NUMERIC": 0,
            "datalogger.TABLE_ALIAS_SQL_LENGTH_NUMERIC": 0,
            "datalogger.TABLE_ALIAS_DATABASE_FIELD_NAME_QUALITY": "",
            "datalogger.TABLE_ALIAS_SQL_DATA_TYPE_QUALITY": 0,
            "datalogger.TABLE_ALIAS_SQL_LENGTH_QUALITY": 0,
            "datalogger.TABLE_ALIAS_DATABASE_FIELD_NAME_TIMESTAMP": cols["time"],
            "datalogger.TABLE_ALIAS_SQL_DATA_TYPE_TIMESTAMP": 11 if cols["time"] else 0,
            "datalogger.TABLE_ALIAS_SQL_LENGTH_TIMESTAMP": 16 if cols["time"] else 0,
            "datalogger.TABLE_ALIAS_DATABASE_FIELD_NAME_VALUE": cols["val"],
            "datalogger.TABLE_ALIAS_SQL_DATA_TYPE_VALUE": 1,
            "datalogger.TABLE_ALIAS_SQL_LENGTH_VALUE": 64,
            "datalogger.TABLE_ALIAS_DATABASE_FIELD_NAME_BATCHID": "",
            "datalogger.TABLE_ALIAS_SQL_DATA_TYPE_BATCHID": 0,
            "datalogger.TABLE_ALIAS_SQL_LENGTH_BATCHID": 0
        })
        idx += 1
        
    # Internal Kepware placeholder mapping
    mappings.append({
        "common.ALLTYPES_NAME": "DefaultMapping",
        "datalogger.TABLE_ALIAS_LOG_ITEM_ID": "__internal",
        "datalogger.TABLE_ALIAS_DATABASE_FIELD_NAME_NAME": "",
        "datalogger.TABLE_ALIAS_SQL_DATA_TYPE_NAME": 0,
        "datalogger.TABLE_ALIAS_SQL_LENGTH_NAME": 0,
        "datalogger.TABLE_ALIAS_DATABASE_FIELD_NAME_NUMERIC": "",
        "datalogger.TABLE_ALIAS_SQL_DATA_TYPE_NUMERIC": 0,
        "datalogger.TABLE_ALIAS_SQL_LENGTH_NUMERIC": 0,
        "datalogger.TABLE_ALIAS_DATABASE_FIELD_NAME_QUALITY": "",
        "datalogger.TABLE_ALIAS_SQL_DATA_TYPE_QUALITY": 0,
        "datalogger.TABLE_ALIAS_SQL_LENGTH_QUALITY": 0,
        "datalogger.TABLE_ALIAS_DATABASE_FIELD_NAME_TIMESTAMP": "",
        "datalogger.TABLE_ALIAS_SQL_DATA_TYPE_TIMESTAMP": 0,
        "datalogger.TABLE_ALIAS_SQL_LENGTH_TIMESTAMP": 0,
        "datalogger.TABLE_ALIAS_DATABASE_FIELD_NAME_VALUE": "",
        "datalogger.TABLE_ALIAS_SQL_DATA_TYPE_VALUE": 0,
        "datalogger.TABLE_ALIAS_SQL_LENGTH_VALUE": 0,
        "datalogger.TABLE_ALIAS_DATABASE_FIELD_NAME_BATCHID": "",
        "datalogger.TABLE_ALIAS_SQL_DATA_TYPE_BATCHID": 0,
        "datalogger.TABLE_ALIAS_SQL_LENGTH_BATCHID": 0
    })
    return mappings

def update_kepware_project():
    print(f"Loading {INPUT_PROJECT}...")
    with open(INPUT_PROJECT, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    for dl in data["project"].get("_datalogger", []):
        log_groups = dl.get("log_groups", [])

        # 1. Update MESNAC 1 Log Group
        m1_group = None
        for lg in log_groups:
            if lg.get("common.ALLTYPES_NAME") == "MESNAC_TYRE_WEIGHT":
                m1_group = lg
                # Lock alias regeneration
                lg["datalogger.LOG_GROUP_REGENERATE_ALIAS_TABLE_ON_DSN_CHANGE"] = False
                lg["datalogger.LOG_GROUP_REGENERATE_ALIAS_TABLE_ON_BATCH_ID_CHANGE"] = False
                lg["datalogger.LOG_GROUP_REGENERATE_ALIAS_TABLE_ON_TABLE_NAME_CHANGE"] = False
                lg["datalogger.LOG_GROUP_REGENERATE_ALIAS_TABLE_ON_TABLE_SELECTION_CHANGE"] = False

                # Inject clean column mapping
                lg["column_mapping_groups"] = [{
                    "common.ALLTYPES_NAME": "Column Mappings",
                    "column_mappings": build_kepware_column_mappings(CLEAN_MAPPINGS_M1)
                }]
                print("  [OK] Updated MESNAC_TYRE_WEIGHT column mapping.")
                break

        # 2. Clone for MESNAC 2
        if m1_group:
            # Remove old MESNAC 2 group if re-running
            log_groups[:] = [lg for lg in log_groups if lg.get("common.ALLTYPES_NAME") != "MESNAC2_TYRE_WEIGHT"]

            m2_group = copy.deepcopy(m1_group)
            m2_group["common.ALLTYPES_NAME"] = "MESNAC2_TYRE_WEIGHT"
            m2_group["datalogger.LOG_GROUP_ENABLED"] = False  # Safe startup flag

            # Swap channel/device names in tag references
            for item in m2_group["log_item_groups"][0]["log_items"]:
                item["datalogger.LOG_ITEM_ID"] = item["datalogger.LOG_ITEM_ID"].replace("MESNAC26.MESNAC 1", "MESNAC27.MESNAC 2")

            # Update trigger tags
            trig = m2_group["trigger_groups"][0]["triggers"][0]
            trig["datalogger.TRIGGER_CONDITION_START_ITEM_ID"] = "MESNAC27.MESNAC 2.Global.C_MESRecord"
            trig["datalogger.TRIGGER_CONDITION_STOP_ITEM_ID"] = "MESNAC27.MESNAC 2.Global.C_MESRecord"

            # Inject MESNAC 2 column mappings
            m2_group["column_mapping_groups"] = [{
                "common.ALLTYPES_NAME": "Column Mappings",
                "column_mappings": build_kepware_column_mappings(CLEAN_MAPPINGS_M2)
            }]

            log_groups.append(m2_group)
            print("  [OK] Cloned and configured MESNAC2_TYRE_WEIGHT.")

    print(f"Saving to {OUTPUT_PROJECT}...")
    with open(OUTPUT_PROJECT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("  [SUCCESS] Project JSON saved cleanly!")

if __name__ == "__main__":
    update_kepware_project()
```

---

## Part 2: Automating SQL Server with Python (`pyodbc`)

### Key Lessons & Best Practices
1. **Non-Destructive Schema Evolution (`ALTER TABLE ADD`)**:  
   Never drop or recreate active production tables. Always inspect existing columns via `INFORMATION_SCHEMA.COLUMNS` first, and use `ALTER TABLE ... ADD ...` to add new columns.
2. **Identity Columns**:  
   Columns defined with `IDENTITY(1,1)` (like `id`) must not be inserted into directly by Kepware or application scripts. SQL Server assigns them automatically.
3. **Safe Historical Backfilling**:  
   After adding clean columns, populate them from existing legacy columns using a single `UPDATE` query with `WHERE [NewColumn] IS NULL`.

---

### Reusable Script 2: Safe Schema Migration & Data Backfill

```python
"""
=============================================================================
SQL Server Schema Synchronizer & Data Backfiller
=============================================================================
Usage:
1. Connects to SQL Server using pyodbc.
2. Checks if desired columns exist in the target table.
3. Adds any missing columns safely without interrupting active logging.
4. Backfills historical rows from legacy columns into new clean columns.
"""

import pyodbc

# Connection Settings
DB_SERVER   = "sql-server.plant.local"
DB_DATABASE = "CollectionDB"
DB_USER     = "Kepware"
DB_PASS     = "Kepware"
TABLE_NAME  = "MESNAC_TYRE_WEIGHT"

CONN_STR = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_DATABASE};"
    f"UID={DB_USER};"
    f"PWD={DB_PASS};"
    f"TrustServerCertificate=yes;"
)

# Target Clean Columns to Ensure Exist
TARGET_COLUMNS = [
    ("Timestamp",           "DATETIME NULL"),
    ("Barcode",             "VARCHAR(64) NULL"),
    ("MCH_CODE",            "VARCHAR(64) NULL"),
    ("ActualWeight_Online", "VARCHAR(64) NULL"),
    ("Trigger",             "VARCHAR(64) NULL")
]

def sync_table_schema_and_backfill():
    print(f"Connecting to {DB_SERVER} -> [{DB_DATABASE}]...")
    conn = pyodbc.connect(CONN_STR, autocommit=True, timeout=10)
    cursor = conn.cursor()

    # 1. Query existing columns
    cursor.execute("""
        SELECT COLUMN_NAME 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME = ? AND TABLE_SCHEMA = 'dbo'
    """, TABLE_NAME)
    existing_cols = {row[0].lower() for row in cursor.fetchall()}
    print(f"Found {len(existing_cols)} existing columns in dbo.{TABLE_NAME}.")

    # 2. Add missing columns safely
    for col_name, col_def in TARGET_COLUMNS:
        if col_name.lower() not in existing_cols:
            print(f"  Adding missing column [{col_name}]...")
            cursor.execute(f"ALTER TABLE dbo.{TABLE_NAME} ADD [{col_name}] {col_def}")
            print(f"  [SUCCESS] Column [{col_name}] added.")
        else:
            print(f"  Column [{col_name}] already exists.")

    # 3. Check for unpopulated historical rows
    cursor.execute(f"SELECT COUNT(*) FROM dbo.{TABLE_NAME} WHERE ActualWeight_Online IS NULL")
    unpopulated_count = cursor.fetchone()[0]
    print(f"\nUnpopulated historical records: {unpopulated_count:,}")

    # 4. Backfill from legacy columns if available
    if unpopulated_count > 0:
        print("Backfilling historical records from legacy columns...")
        sql_backfill = f"""
        UPDATE dbo.{TABLE_NAME}
        SET 
            ActualWeight_Online = MESNAC26_MESNAC_1_Global_Aux_ActualWeight_Online_VALUE,
            [Trigger]           = MESNAC26_MESNAC_1_Global_C_MESRecord_VALUE,
            [Timestamp]         = MESNAC26_MESNAC_1_Global_C_MESRecord_TIMESTAMP,
            Barcode             = RTRIM(MESNAC26_MESNAC_1_Global_Data_GTLMOut_DATA_VALUE),
            MCH_CODE            = RTRIM(MESNAC26_MESNAC_1_Global_MCH_CODE_DATA_VALUE)
        WHERE ActualWeight_Online IS NULL;
        """
        cursor.execute(sql_backfill)
        print("  [SUCCESS] Historical records backfilled!")

    # 5. Verify sample recent rows
    print("\nVerifying latest 3 rows:")
    cursor.execute(f"""
        SELECT TOP 3 id, [Timestamp], Barcode, MCH_CODE, ActualWeight_Online, [Trigger] 
        FROM dbo.{TABLE_NAME} 
        ORDER BY id DESC
    """)
    for r in cursor.fetchall():
        print(f"  id={r[0]} | Timestamp={r[1]} | Barcode={r[2]} | MCH={r[3]} | Weight={r[4]} | Trigger={r[5]}")

    cursor.close()
    conn.close()
    print("\n[DONE] Schema sync and backfill complete.")

if __name__ == "__main__":
    sync_table_schema_and_backfill()
```

