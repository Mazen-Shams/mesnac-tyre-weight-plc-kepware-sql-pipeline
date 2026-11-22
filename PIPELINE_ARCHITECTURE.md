# Mesnac Tyre Weight Data Pipeline: Master Architecture Guide

> **Author**: Smart Manufacturing / Automation Team  
> **Target Plant Lines**: Building Machines MESNAC 1 (MESNAC26) & MESNAC 2 (MESNAC27)  
> **Database Host**: `sql-server.plant.local` (Database: `CollectionDB`)  
> **ODBC DSN**: `Kepware_SQL_DSN`  
> **Production Table**: `CollectionDB.dbo.MESNAC_TYRE_WEIGHT`  
> **Last Updated**: November 17, 2026  

---

## 1. System Vision & Objective

During green tyre building, tyre weight is a critical quality parameter monitored by quality control, process engineering, and smart manufacturing dashboards.

The objective of this pipeline is to provide **automated, real-time tyre weight traceability**:
* Whenever a building machine (MESNAC 1 or MESNAC 2) completes and weighs a green tyre, the telemetry is captured by Kepware KEPServerEX.
* The record binds the **Tyre Barcode**, **Machine Code**, **Measured Weight**, and **Timestamp** into a single row in SQL Server (`CollectionDB.dbo.MESNAC_TYRE_WEIGHT`).
* Downstream enterprise analytics engines (Dremio and Grafana dashboards) query this data for real-time monitoring and reporting.

---

## 2. End-to-End Architecture Overview

```mermaid
flowchart TD
    subgraph P1["⚡ Layer 1: Physical Machinery & PLCs"]
        direction TB
        M1["MESNAC 1 (IP: 192.168.1.168)<br/>Allen-Bradley ControlLogix<br/>Channel: MESNAC26 | Device: MESNAC 1"]
        M2["MESNAC 2 (IP: 192.168.1.127)<br/>Allen-Bradley ControlLogix<br/>Channel: MESNAC27 | Device: MESNAC 2"]
    end

    subgraph P2["⚙️ Layer 2: Industrial Middleware (KEPServerEX V6)"]
        direction TB
        DL1["DataLogger Group: MESNAC_TYRE_WEIGHT<br/>Monitors MESNAC 1 Tags<br/>Trigger: C_MESRecord (1 -> 0)"]
        DL2["DataLogger Group: MESNAC2_TYRE_WEIGHT<br/>Monitors MESNAC 2 Tags<br/>Trigger: C_MESRecord (1 -> 0)"]
    end

    subgraph P3["🗄️ Layer 3: Database & Analytics"]
        direction TB
        SQL[("SQL Server: sql-server<br/>Database: CollectionDB<br/>Table: dbo.MESNAC_TYRE_WEIGHT")]
        Dremio["Dremio Enterprise Lakehouse<br/>PTG_EG_ATCO_IND_DCollection01"]
        Grafana["Grafana Production Dashboards<br/>mesnac-live.json (Panels 110, 111, 112)"]
    end

    M1 -->|Ethernet/IP (100ms scan)| DL1
    M2 -->|Ethernet/IP (100ms scan)| DL2
    DL1 -->|ODBC INSERT (DSN: Kepware_SQL_DSN)| SQL
    DL2 -->|ODBC INSERT (DSN: Kepware_SQL_DSN)| SQL
    SQL --> Dremio --> Grafana
```

---

## 3. PLC Tag Specifications

Both MESNAC 1 and MESNAC 2 utilize Allen-Bradley ControlLogix PLCs with matching tag structures under the `Global` tag group:

| Signal Role | MESNAC 1 Kepware Tag Path | MESNAC 2 Kepware Tag Path | PLC Address / Data Type |
| :--- | :--- | :--- | :--- |
| **Tyre Barcode** | `MESNAC26.MESNAC 1.Global.Data_GTLMOut.DATA` | `MESNAC27.MESNAC 2.Global.Data_GTLMOut.DATA` | `DATA_GTLMOUT.DATA/82` (String) |
| **Machine Identifier** | `MESNAC26.MESNAC 1.Global.MCH_CODE.DATA` | `MESNAC27.MESNAC 2.Global.MCH_CODE.DATA` | `MCH_CODE.DATA/82` (String) |
| **Instantaneous Weight** | `MESNAC26.MESNAC 1.Global.Aux_ActualWeight_Online` | `MESNAC27.MESNAC 2.Global.Aux_ActualWeight_Online` | `AUX_ACTUALWEIGHT_ONLINE` (DINT, /100 kg) |
| **Latched Weight (End)** | `MESNAC26.MESNAC 1.Global.Aux_EndActualWeight_Online` | `MESNAC27.MESNAC 2.Global.Aux_EndActualWeight_Online` | `AUX_ENDACTUALWEIGHT_ONLINE` (DINT, /100 kg) |
| **Latched Weight (Real)** | `MESNAC26.MESNAC 1.Global.Aux_TireActualWeight1` | `MESNAC27.MESNAC 2.Global.MES_TireWeight` | `AUX_TIREACTUALWEIGHT1` / `MES_TIREWEIGHT` (REAL) |
| **Handshake Trigger** | `MESNAC26.MESNAC 1.Global.C_MESRecord` | `MESNAC27.MESNAC 2.Global.C_MESRecord` | `C_MESRECORD` (Boolean) |
| **Weight Stable Flag** | `MESNAC26.MESNAC 1.Global.F_WeightStableOnline` | `MESNAC27.MESNAC 2.Global.F_WeightStableOnline` | `F_WEIGHTSTABLEONLINE` (Boolean) |
| **Weighing Complete** | `MESNAC26.MESNAC 1.Global.F_WeightOnline_PC` | `MESNAC27.MESNAC 2.Global.F_WeightOnline_PC` | `F_WEIGHTONLINE_PC` (Boolean) |

---

## 4. Production Database Schema: `dbo.MESNAC_TYRE_WEIGHT`

The target table in `CollectionDB` contains 6 active production columns:

| Column Name | SQL Data Type | Nullable | Managed By | Description |
| :--- | :--- | :---: | :--- | :--- |
| **`id`** | `INT IDENTITY(1,1)` | NO | SQL Server | Primary key, auto-incrementing record ID. |
| **`Timestamp`** | `DATETIME` | YES | Kepware DataLogger | Exact event timestamp mapped from `C_MESRecord`. |
| **`Barcode`** | `VARCHAR(64)` | YES | Kepware DataLogger | Tyre barcode scanned by Green Tyre Laser Machine. |
| **`MCH_CODE`** | `VARCHAR(64)` | YES | Kepware DataLogger | Machine code (`'MES1'` or `'MES2'`). |
| **`ActualWeight_Online`** | `VARCHAR(64)` | YES | Kepware DataLogger | Measured tyre weight in 0.01 kg units (e.g. `4178` = 41.78 kg). |
| **`Trigger`** | `VARCHAR(64)` | YES | Kepware DataLogger | Handshake trigger bit value (`'1'`). |

*(Note: The 16 legacy VTQ columns prefixed with `MESNAC26_...` were formally retired and dropped on November 18, 2026).*

---

## 5. Kepware DataLogger Trigger Mechanics

### Current Modern Architecture (November 19, 2026)
In `kepware_mesnac_tyre_weight_config.json`, Kepware utilizes an **Advanced Derived Tag**:
* **Tag Path**: `_AdvancedTags.MESNAC_Tyre_weight.MESNAC1_Weighing_Valid`
* **Formula**: `(TAG(MESNAC26.MESNAC 1.Global.C_MESRecord) == 1) AND (TAG(MESNAC26.MESNAC 1.Global.F_WeightStableOnline) == 1)`
* **Condition Start**: `== 1` (Opens only when tyre is fully settled on scale platform)
* **Condition Stop**: `== 0` (Closes immediately when tyre is lifted or pulse ends)
* **Log all items on condition start**: `True` (Single-shot snapshot of true green tyre weight)
* **Log on Data Change**: `False`
* **Log all items on condition stop**: `False`

### Handshake Sequence
1. The operator / machine completes the tyre building process on the main drum.
2. The Green Tyre Removal System (GTRS) unloader arm engages the tyre.
3. The barcode reader reads `DATA_GTLMOUT.DATA`.
4. The tyre is placed onto the online weighing scale.
5. Once settled, the weight is measured.
6. The PLC pulses `C_MESRECORD = 1` for approximately 3 to 4 seconds, then resets `C_MESRECORD = 0`.

### Kepware DataLogger Production Trigger Settings (`MESNAC_TYRE_WEIGHT`)
* **Trigger Type**: Condition Trigger (Type 2)
* **Start Condition**: `_AdvancedTags.MESNAC_Tyre_weight.MESNAC1_Weighing_Valid == 1`
* **Stop Condition**: `_AdvancedTags.MESNAC_Tyre_weight.MESNAC1_Weighing_Valid == 0`
* **Log on Condition Start**: `Yes` *(Captures single snapshot at settled weight)*
* **Log on Data Change**: `No` *(Prevents multi-row flooding & trailing Trigger=0)*
* **Log on Condition Stop**: `No` *(Suppresses empty-scale tare snapshot)*
* **Status**: 🟢 Active in Production (MESNAC 1). MESNAC 2 kept disabled pending electrical scale hardware inspection.


