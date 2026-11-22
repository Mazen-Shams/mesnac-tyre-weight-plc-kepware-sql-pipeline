# Mesnac Tyre Weight Data Pipeline (PLC ➔ Kepware ➔ SQL Server)

This repository manages the end-to-end telemetry pipeline for capturing and logging green tyre weights from **MESNAC 1** and **MESNAC 2** tyre building machines into Prometeon's enterprise SQL Server database (`CollectionDB`).

---

## 📚 Documentation Index

| Document | Description |
| :--- | :--- |
| **[`PIPELINE_ARCHITECTURE.md`](./PIPELINE_ARCHITECTURE.md)** | Complete end-to-end system architecture, hardware/PLC layers, middleware configuration, tag dictionaries, and database schemas. |
| **[`PYTHON_AUTOMATION_GUIDE.md`](./PYTHON_AUTOMATION_GUIDE.md)** | Standalone, copy-pasteable Python automation scripts for manipulating Kepware JSON exports and executing non-destructive SQL Server migrations. |
| **[`PROJECT_PROGRESS_AND_FINDINGS.md`](./PROJECT_PROGRESS_AND_FINDINGS.md)** | Chronological log of session milestones, the root cause analysis of negative weights / empty-scale tare readings, and trigger tuning details. |

---

## 🗂️ Configuration & Diagnostic Tools

* **[`kepware_mesnac_tyre_weight_config.json`](./kepware_mesnac_tyre_weight_config.json)**: ⭐ **Current Production Project**. Configured with the Advanced Derived Tag (`MESNAC1_Weighing_Valid`), single-shot trigger on condition start, and clean 6-column schema.
* **[`mesnac_opcua_weight_monitor.py`](./mesnac_opcua_weight_monitor.py)**: High-speed 100ms OPC UA live diagnostic tool and peak tyre logger.
* **[`run_mesnac_monitor.bat`](./run_mesnac_monitor.bat)**: Double-click launcher for the OPC UA monitor.
* **[`kepware_clean_tyre_weight.json`](./kepware_clean_tyre_weight.json)**: Interim backup configuration.

---

## ⚡ Quick Reference: Active Database Schema

**Target**: `sql-server.plant.local` ➔ `[CollectionDB].[dbo].[MESNAC_TYRE_WEIGHT]`

| Column Name | Type | Description |
| :--- | :--- | :--- |
| `id` | `INT IDENTITY(1,1)` | Auto-increment primary key (SQL Server managed) |
| `Timestamp` | `DATETIME` | Time of weighing event |
| `Barcode` | `VARCHAR(64)` | Tyre barcode (from Green Tyre Laser Machine) |
| `MCH_CODE` | `VARCHAR(64)` | Machine code (`'MES1'` or `'MES2'`) |
| `ActualWeight_Online` | `VARCHAR(64)` | Measured weight in 0.01 kg units (e.g. `4178` = 41.78 kg) |
| `Trigger` | `VARCHAR(64)` | Handshake bit value (`'1'`) |

