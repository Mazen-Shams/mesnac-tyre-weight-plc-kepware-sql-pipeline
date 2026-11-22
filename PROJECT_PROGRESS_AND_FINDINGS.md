# Session Log: Progress, Discoveries & Technical Findings

> **Date**: November 17, 2026  
> **Workspace**: `c:\Users\st1ahmedma\OneDrive - Prometeon\Mesnac Tyre Weight (sql - kepware - plc) pipeline`  
> **Target Machinery**: Mesnac Building Machine 1 (`MESNAC26`) & Mesnac Building Machine 2 (`MESNAC27`)  
> **Database Table**: `CollectionDB.dbo.MESNAC_TYRE_WEIGHT` on `sql-server.plant.local`  

---

## 1. Executive Summary of Achievements

During this session, we accomplished the following milestones:
1. **Pipeline Reverse Engineering**: Traced the complete hardware, PLC, Kepware DataLogger, and SQL Server data flow for MESNAC 1 and identified matching PLC tags for MESNAC 2.
2. **Database Schema Modernization**: Non-destructively upgraded `CollectionDB.dbo.MESNAC_TYRE_WEIGHT` by adding 5 standard columns (`Timestamp`, `Barcode`, `MCH_CODE`, `ActualWeight_Online`, `Trigger`).
3. **Historical Data Preservation**: Backfilled all **232,593 existing production records** into the clean columns with zero data loss.
4. **Multi-Machine Configuration Generated**: Created [`kepware_clean_tyre_weight.json`](file:///c:/Users/st1ahmedma/OneDrive%20-%20Prometeon/Mesnac%20Tyre%20Weight%20(sql%20-%20kepware%20-%20plc)%20pipeline/kepware_clean_tyre_weight.json) containing clean mappings for MESNAC 1 and a new cloned group for MESNAC 2 with safe startup flags.
5. **Negative Weights Diagnosis**: Conducted a statistical and chronological investigation revealing why tyres were logging negative weights (`-214` / `-6`), uncovering a physical timing mismatch between `C_MESRecord` and the scale platform.
6. **Trigger Fine-Tuning**: Configured an interim trigger profile (`Log on Data Change: Yes`, `Log all items on condition start: No`) to restore positive weight values immediately without corrupting Grafana.

---

## 2. Technical Discoveries & Root Cause Analyses

### A. The "VTQ Bloat" Problem
* **Observation**: In the original [kepware 16-11-2026.json](file:///c:/Users/st1ahmedma/OneDrive%20-%20Prometeon/Mesnac%20Tyre%20Weight%20(sql%20-%20kepware%20-%20plc)%20pipeline/kepware%2016-11-2026.json), the table had 17 auto-generated columns:
  `MESNAC26_MESNAC_1_Global_Aux_ActualWeight_Online_NUMERICID`, `_VALUE`, `_TIMESTAMP`, `_QUALITY`, etc.
* **Cause**: In Kepware DataLogger, `LOG_GROUP_REGENERATE_ALIAS_TABLE_ON_DSN_CHANGE` was set to `true`. When the database connection was updated, Kepware wiped custom column mappings and auto-generated bloated names for every tag.
* **Resolution**: Rebuilt `column_mappings` in Python to map directly to single clean column names (`Barcode`, `MCH_CODE`, `ActualWeight_Online`, `Trigger`, `Timestamp`) and set `LOG_GROUP_REGENERATE_ALIAS_TABLE...` to `false`.

---

### B. Why `Trigger = 0` Rows Were Appearing
* **Observation**: The database contained 19,072 rows where `Trigger = 0`.
* **Root Cause**:
  1. `MESNAC26.MESNAC 1.Global.C_MESRecord` was added as a monitored Log Item in the group.
  2. `Log on Data Change` was set to `Yes`.
  3. When the machine finished building a tyre, the PLC pulsed `C_MESRecord` from `1` back to `0`.
  4. Kepware evaluated this transition as a **data change event**, logging an extra row with `Trigger = 0` before closing the condition window.

---

### C. Why Recent Tyres Logged Negative Weights (`-214` on MES1, `-6` on MES2)
* **Statistical Investigation**:
  Querying the database today showed:
  * Positive weights count: 217,894 (average = 3,974.45 / 39.74 kg).
  * Negative weights count: 14,750 (concentrated at `-200` to `-236` on MES1, and `-6` on MES2).
* **Load Cell Physics**:
  In tyre manufacturing, weights are represented in 0.01 kg units:
  * `-214` = `-2.14 kg`
  * `-6` = `-0.06 kg`
  These negative numbers are the **empty-scale tare zero offset** of the load cell when **NO tyre is sitting on the scale**.
* **The Chronological Trace**:
  Inspecting historical multi-row barcodes (e.g. `8114468405`):
  1. `10:44:16.437` ➔ Weight = `-206` (Trigger = 1) ➔ *Condition fires, scale is still empty.*
  2. `10:44:16.317` ➔ Weight = `1080` ➔ `2074` ➔ `3980` ➔ *Tyre lands on scale, logged because Data Change was Yes.*
  3. `10:44:16.317` ➔ Weight = `426` ➔ `196` ➔ `-212` ➔ *Tyre removed from scale.*
  4. `10:44:19.643` ➔ Weight = `-194` (Trigger = 0) ➔ *PLC resets trigger bit.*
* **Why Turning Off "Log on Data Change" Exposed This**:
  With `Log on Data Change = No` and `Log all items on condition start = Yes`, Kepware logged **strictly at the exact millisecond `C_MESRecord` turned 1**. Because `C_MESRecord` fires 1–2 seconds *before* the mechanical arm places the tyre onto the scale, Kepware captured only the empty-scale tare reading!

---

## 3. Current Working Solution (Interim Tuning)

In [`kepware_clean_tyre_weight.json`](file:///c:/Users/st1ahmedma/OneDrive%20-%20Prometeon/Mesnac%20Tyre%20Weight%20(sql%20-%20kepware%20-%20plc)%20pipeline/kepware_clean_tyre_weight.json):
* **`Log on Data Change`** ➔ **`Yes` (`true`)**: Allows Kepware to log when the tyre lands on the scale.
* **`Log all items on condition start`** ➔ **`No` (`false`)**: Suppresses the initial empty-scale snapshot.
* **`Log all items on condition stop`** ➔ **`No` (`false`)**: Suppresses the closing `Trigger = 0` snapshot.

### Grafana Compatibility
Grafana panel queries in `mesnac-live.json` already contain:
```sql
WHERE Trigger_TIMESTAMP IS NOT NULL 
  AND CAST(ActualWeight_Online AS DOUBLE) > 0
```
and deduplicate using `ROW_NUMBER() ... rn = 1`. This interim configuration immediately restores positive, valid weights to Grafana dashboards.

---

## 4. Legacy VTQ Columns Retirement (November 18, 2026)

With maintenance clearance, the 16 legacy VTQ columns were safely dropped:
1. **Schema Cleanup**: Executed `ALTER TABLE dbo.MESNAC_TYRE_WEIGHT DROP COLUMN ...` across all 16 legacy columns.
2. **Outcome**: The production table is now streamlined to exactly 6 clean columns (`id`, `Timestamp`, `Barcode`, `MCH_CODE`, `ActualWeight_Online`, `Trigger`), matching the modernized Kepware DataLogger configuration.

---

## 5. High-Speed OPC UA Field Trace & Tag Discoveries (November 19, 2026)

To resolve the discrepancy between theoretical tag specifications and physical machine behavior, we deployed a dedicated 100ms Python OPC UA monitor (`mesnac_opcua_weight_monitor.py`) directly against the Kepware server (`192.168.10.50:49320`).

### A. Proof that Latched Registers are Unused in PLC Ladder Logic
Field testing and video tracing (`mesnac tyre weight tag trace.mp4`, `mesnac_weighing_events.csv`) yielded definitive proof:
* **`Aux_EndActualWeight_Online`**: Held `0.00 kg` (Raw `0`) across 100% of tyre cycles.
* **`Aux_TireActualWeight1`**: Held `0.00 kg` (Raw `0.00`) across 100% of tyre cycles.
* **`MES_TireWeight` (MES 2)**: Held `-0.06 kg` static.
* **`F_WeightOnline_PC`**: Remained `False` throughout all weighing events.

> **Key Takeaway**: Although these tags exist in the ControlLogix tag database, **the PLC ladder logic does not write to them**. Therefore, **`Aux_ActualWeight_Online` is 100% confirmed as the ONLY live, physical weight signal on the machine.**

### B. Physical Scale Dynamics Observed on MESNAC 1
* **True Green Tyre Weight**: Tyres produced on MES1 weigh **~19.0 to 21.8 kg** (e.g. `21.82 kg`, `20.04 kg`, `19.30 kg`).
* **Settling Window**: When the tyre is lowered onto the load cells, `F_WeightStableOnline` switches to `True` within **1.0 to 1.5 seconds**, confirming mechanical vibration has ceased.
* **Handshake Pulse**: `C_MESRecord` stays high (`1`) for approximately **3.4 seconds**.

### C. Physical Status of MESNAC 2
* `Aux_ActualWeight_Online` on MESNAC 2 flatlined at `-0.06 kg` (`-6`) continuously with zero response during machine cycles.
* **Conclusion**: MESNAC 2 online scale is currently disconnected, bypassed, or undergoing mechanical calibration.

---

## 6. Single-Shot Architecture via Kepware Advanced Derived Tag

To prevent the historical problem of flooding the database with 15–20 fluctuating rows per tyre and logging trailing `Trigger = 0` exit rows, we designed a compound trigger:

### A. Advanced Derived Tag Definition
Created in `kepware_mesnac_tyre_weight_config.json` under `_AdvancedTags.MESNAC_Tyre_weight`:
* **Tag Name**: `MESNAC1_Weighing_Valid`
* **Boolean Formula**:
  ```text
  (TAG(MESNAC26.MESNAC 1.Global.C_MESRecord) == 1) AND (TAG(MESNAC26.MESNAC 1.Global.F_WeightStableOnline) == 1)
  ```

### B. Kepware DataLogger Group Configuration (`MESNAC_TYRE_WEIGHT`)
* **Trigger Type**: Condition Trigger (Type 2)
* **Start Condition**: `_AdvancedTags.MESNAC_Tyre_weight.MESNAC1_Weighing_Valid == 1`
* **Stop Condition**: `_AdvancedTags.MESNAC_Tyre_weight.MESNAC1_Weighing_Valid == 0`
* **Log all items on condition start**: `True` (Captures instant single snapshot of settled tyre)
* **Log on Data Change**: `False` (Suppresses all mid-cycle bouncing)
* **Log all items on condition stop**: `False` (Suppresses exit tare snapshot)

### C. Live Production Verification in SQL Server (`CollectionDB`)
Immediately after enabling the log group in Kepware, continuous production monitoring revealed clear operational characteristics:
* **Genuine Green Tyres**: Every production tyre weighing between **12.68 kg and 23.32 kg** logged **EXACTLY 1 ROW PER TYRE** (e.g. Barcodes `8114469153` to `8114469168`).
* **`Trigger = 0` Rows**: **ZERO** across all cycles.
* **Empty Unloader Cycles & Tare Flutter**:
  * Unloader cycles with no tyre or partial test loads read at **~4.3 to 5.4 kg** or **0.00 kg** (e.g. barcodes `8114469167`, `8114469169`, `8114469170`).
  * At this near-empty weight, mechanical arm vibration caused `F_WeightStableOnline` to flutter (`1 -> 0 -> 1` in ~500ms), triggering 2–3 rows.
  * This provides direct empirical justification for our recommendation to add a `Weight > 10.0 kg` interlock.

---

## 7. Action Items & Agenda for Electrical / Automation Team

When meeting with the plant electrical and automation engineers:

1. **Ladder Logic Latching (Long-Term Best Practice)**:
   * Ask the PLC programmer to add a simple 1-rung logic instruction to copy `AUX_ACTUALWEIGHT_ONLINE` into `AUX_ENDACTUALWEIGHT_ONLINE` (or `AUX_TIREACTUALWEIGHT1`) when `F_WeightStableOnline` is True.
   * This provides a hardware-frozen register that persists even after the unloader picks up the tyre.

2. **Empty Scale Stability Bit Filter**:
   * When no tyre is on the scale, `F_WeightStableOnline` can report `True` because an empty scale is also mechanically static.
   * Recommend adding a minimum weight interlock in PLC or Derived Tag: `ActualWeight > 500` (i.e. > 5.0 kg) so empty tares cannot trigger logging if `C_MESRecord` fires prematurely.

3. **MESNAC 2 Scale Hardware Status**:
   * Request electrical inspection of load cell amplifier and communication module for MESNAC 2 (`Channel MESNAC27`), which currently outputs a static `-0.06 kg`.
   * Keep MESNAC 2 DataLogger group disabled until scale hardware is verified.

