"""
=============================================================================
Prometeon Tyre Group - MESNAC Tyre Weight Live OPC UA Monitor & Peak Logger
=============================================================================
Target: MESNAC 1 (MESNAC26) & MESNAC 2 (MESNAC27) Green Tyre Weighing
Middleware: Kepware KEPServerEX V6 (opc.tcp://192.168.10.50:49320)

Updated (Nov 19, 2026):
  - Removed unused/dead PLC registers (Aux_EndActualWeight_Online, Aux_TireActualWeight1, 
    MES_TireWeight, F_WeightOnline_PC).
  - Added Kepware Advanced Tag:
      _AdvancedTags.MESNAC_Tyre_weight.MESNAC1_Weighing_Valid
    Formula: (C_MESRecord == 1) AND (F_WeightStableOnline == 1)
  - 100ms high-speed scan rate to capture transient load cell dynamics.
  - Live split-view dashboard (Real-time Tag Values + Rolling Event Log).
  - Logs completed valid tyre weighings to CSV (mesnac_weighing_events.csv).

Usage:
  python mesnac_opcua_weight_monitor.py                     # MESNAC 1 (Default)
  python mesnac_opcua_weight_monitor.py --machine 2         # MESNAC 2
  python mesnac_opcua_weight_monitor.py --machine both      # Both Machines
  python mesnac_opcua_weight_monitor.py --rate 100          # 100 ms scan rate
  python mesnac_opcua_weight_monitor.py --log-only          # Scrolling stream mode (no cls)
=============================================================================
"""

import sys
import os
import time
import csv
import argparse
from datetime import datetime

# =============================================================================
# DEFAULT CONFIGURATION
# =============================================================================
DEFAULT_KEPWARE_URL = os.getenv("KEPWARE_OPCUA_URL", "opc.tcp://127.0.0.1:49320")   # Primary trusted plant endpoint
OPC_NAMESPACE       = 2                                  # Kepware default namespace
DEFAULT_SCAN_MS     = 100                                # 100ms scan interval
CSV_FILENAME        = "mesnac_weighing_events.csv"

# =============================================================================
# CLEANED TAG DEFINITIONS
# =============================================================================
TAG_DEFINITIONS = {
    "MES1": {
        "channel_device": "MESNAC26.MESNAC 1",
        "mch_code": "MES1",
        "plc_ip": "192.168.1.168",
        "tags": {
            "actual_weight":   "Global.Aux_ActualWeight_Online",  # Live scale (DINT /100 kg)
            "trigger":         "Global.C_MESRecord",              # PLC handshake pulse (Boolean)
            "stable_flag":     "Global.F_WeightStableOnline",     # Scale settled flag (Boolean)
            "barcode":         "Global.Data_GTLMOut.DATA",        # Tyre barcode (String)
            "machine_tag":     "Global.MCH_CODE.DATA",            # Machine Code (String)
        },
        "advanced_tag": "_AdvancedTags.MESNAC_Tyre_weight.MESNAC1_Weighing_Valid"
    },
    "MES2": {
        "channel_device": "MESNAC27.MESNAC 2",
        "mch_code": "MES2",
        "plc_ip": "192.168.1.127",
        "tags": {
            "actual_weight":   "Global.Aux_ActualWeight_Online",  # Live scale (DINT /100 kg)
            "trigger":         "Global.C_MESRecord",              # PLC handshake pulse (Boolean)
            "stable_flag":     "Global.F_WeightStableOnline",     # Scale settled flag (Boolean)
            "barcode":         "Global.Data_GTLMOut.DATA",        # Tyre barcode (String)
            "machine_tag":     "Global.MCH_CODE.DATA",            # Machine Code (String)
        },
        "advanced_tag": "_AdvancedTags.MESNAC_Tyre_weight.MESNAC2_Weighing_Valid"
    }
}

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def format_weight_dint(raw_val):
    """Converts DINT raw units (0.01 kg) to kg float."""
    if isinstance(raw_val, (int, float)):
        return raw_val / 100.0
    return None

def ensure_csv_header(csv_file):
    if not os.path.exists(csv_file):
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Timestamp", "Machine", "Barcode", 
                "Settled_Weight_kg", "Peak_Weight_kg", "ActualWeight_Raw",
                "Duration_Sec", "SamplesCount"
            ])

def append_csv_event(csv_file, event):
    try:
        with open(csv_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                event["timestamp"],
                event["machine"],
                event["barcode"],
                f"{event['settled_weight_kg']:.2f}",
                f"{event['peak_weight_kg']:.2f}",
                event["peak_weight_raw"],
                f"{event['duration_sec']:.2f}",
                event["samples"]
            ])
    except Exception as e:
        print(f"[CSV ERROR] Could not append event: {e}")

class MachineTracker:
    def __init__(self, key, config, client):
        self.key = key
        self.config = config
        self.client = client
        self.nodes = {}
        self.channel_device = config["channel_device"]
        self.mch_code = config["mch_code"]
        self.plc_ip = config["plc_ip"]
        self.advanced_tag_path = config.get("advanced_tag")
        self.adv_node = None

        # Cycle State Variables
        self.prev_valid = False
        self.is_in_cycle = False
        self.cycle_start_time = 0.0
        self.cycle_samples = 0
        self.settled_weight_kg = None
        self.peak_actual_raw = -999999
        self.peak_actual_kg = -9999.0
        self.current_barcode = "UNKNOWN"

        self.resolve_nodes()

    def resolve_nodes(self):
        print(f"      Mapping OPC UA nodes for {self.channel_device}...")
        for tag_alias, tag_rel_path in self.config["tags"].items():
            node_id = f"ns={OPC_NAMESPACE};s={self.channel_device}.{tag_rel_path}"
            try:
                self.nodes[tag_alias] = self.client.get_node(node_id)
            except Exception as e:
                print(f"      [WARN] Could not resolve node {node_id}: {e}")
                self.nodes[tag_alias] = None

        # Resolve Kepware Advanced Tag
        if self.advanced_tag_path:
            adv_nid = f"ns={OPC_NAMESPACE};s={self.advanced_tag_path}"
            try:
                self.adv_node = self.client.get_node(adv_nid)
                # Test read
                _ = self.adv_node.get_value()
                print(f"      [OK] Advanced Tag mapped: {self.advanced_tag_path}")
            except Exception:
                print(f"      [INFO] Advanced Tag {self.advanced_tag_path} not found in Kepware; using software evaluation.")
                self.adv_node = None

    def read_val(self, alias, default=None):
        node = self.nodes.get(alias)
        if node is None:
            return default
        try:
            val = node.get_value()
            if isinstance(val, str):
                return val.strip('\x00').strip()
            return val
        except Exception:
            return default

    def sample(self):
        """Reads tags and tracks valid weighing cycles."""
        trig_val    = bool(self.read_val("trigger", False))
        stable_val  = bool(self.read_val("stable_flag", False))
        act_raw     = self.read_val("actual_weight", 0)
        barcode_val = self.read_val("barcode", "NO_READ")
        mch_tag     = self.read_val("machine_tag", self.mch_code)

        act_kg = format_weight_dint(act_raw) if act_raw is not None else None

        # Determine Weighing Valid State:
        # 1. Read directly from Kepware Advanced Tag if available
        # 2. Otherwise evaluate compound formula: (C_MESRecord == 1) AND (F_WeightStableOnline == 1)
        if self.adv_node is not None:
            try:
                valid_state = bool(self.adv_node.get_value())
            except Exception:
                valid_state = trig_val and stable_val
        else:
            valid_state = trig_val and stable_val

        now = time.time()
        completed_event = None

        # --- VALID WEIGHING RISING EDGE (0 -> 1): SCALE SETTLED WITH TYRE ---
        if valid_state and not self.prev_valid:
            self.is_in_cycle = True
            self.cycle_start_time = now
            self.cycle_samples = 1
            self.current_barcode = barcode_val if barcode_val else "NO_READ"
            self.settled_weight_kg = act_kg
            self.peak_actual_raw = act_raw if act_raw is not None else -999999
            self.peak_actual_kg = act_kg if act_kg is not None else -9999.0

        # --- WHILE WEIGHING IS VALID (1) ---
        elif valid_state and self.is_in_cycle:
            self.cycle_samples += 1
            if barcode_val and barcode_val != "NO_READ":
                self.current_barcode = barcode_val

            if act_raw is not None and act_raw > self.peak_actual_raw:
                self.peak_actual_raw = act_raw
                self.peak_actual_kg = act_kg

        # --- VALID WEIGHING FALLING EDGE (1 -> 0): TYRE REMOVED OR CYCLE END ---
        elif not valid_state and self.prev_valid and self.is_in_cycle:
            duration = now - self.cycle_start_time
            completed_event = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "machine": self.mch_code,
                "barcode": self.current_barcode,
                "settled_weight_kg": self.settled_weight_kg if self.settled_weight_kg is not None else self.peak_actual_kg,
                "peak_weight_kg": self.peak_actual_kg,
                "peak_weight_raw": self.peak_actual_raw,
                "duration_sec": duration,
                "samples": self.cycle_samples
            }
            self.is_in_cycle = False

        self.prev_valid = valid_state

        current_snapshot = {
            "machine": self.mch_code,
            "plc_ip": self.plc_ip,
            "trigger": trig_val,
            "stable": stable_val,
            "valid_state": valid_state,
            "adv_tag_online": self.adv_node is not None,
            "actual_raw": act_raw,
            "actual_kg": act_kg,
            "barcode": barcode_val,
            "is_in_cycle": self.is_in_cycle,
            "cycle_peak_kg": self.peak_actual_kg if self.is_in_cycle else None,
            "cycle_samples": self.cycle_samples if self.is_in_cycle else 0
        }

        return current_snapshot, completed_event

def parse_arguments():
    parser = argparse.ArgumentParser(description="MESNAC Tyre Weight Live OPC UA Monitor & Advanced Tag Validator")
    parser.add_argument("--server", type=str, default=DEFAULT_KEPWARE_URL, 
                        help=f"Kepware OPC UA Server URL (default: {DEFAULT_KEPWARE_URL})")
    parser.add_argument("--machine", type=str, choices=["1", "2", "both"], default="1",
                        help="Target machine: 1 (MESNAC 1), 2 (MESNAC 2), or both (default: 1)")
    parser.add_argument("--rate", type=int, default=DEFAULT_SCAN_MS,
                        help=f"Polling scan rate in milliseconds (default: {DEFAULT_SCAN_MS} ms)")
    parser.add_argument("--csv", type=str, default=CSV_FILENAME,
                        help=f"CSV file to log completed events (default: {CSV_FILENAME})")
    parser.add_argument("--log-only", action="store_true",
                        help="Disable full-screen redraw and output continuous scrolling log")
    return parser.parse_args()

def main():
    args = parse_arguments()
    scan_interval_sec = max(0.02, args.rate / 1000.0)

    print("=" * 78)
    print("   PROMETEON TYRE GROUP - MESNAC TYRE WEIGHT LIVE MONITOR & LOGGER")
    print(f"   Target Server : {args.server}")
    print(f"   Machine Target: {'MESNAC 1 & MESNAC 2' if args.machine == 'both' else 'MESNAC ' + args.machine}")
    print(f"   Scan Interval : {args.rate} ms ({scan_interval_sec:.2f}s)")
    print(f"   CSV Output    : {args.csv}")
    print("=" * 78)

    # 1. Verify opcua library
    try:
        from opcua import Client
    except ImportError:
        print("\n[ERROR] The 'opcua' Python library is not installed.")
        print("Please run: pip install opcua")
        input("\nPress Enter to exit...")
        return

    # 2. Connect to Kepware
    print(f"\n[1/3] Connecting to Kepware OPC UA at {args.server}...")
    client = Client(args.server)

    try:
        t0 = time.perf_counter()
        client.connect()
        conn_ms = (time.perf_counter() - t0) * 1000.0
        print(f"      [SUCCESS] Connected to Kepware OPC UA in {conn_ms:.1f} ms!")
    except Exception as e:
        print("\n" + "!" * 78)
        print(f" [CONNECTION FAILED] Could not connect to {args.server}")
        print(f" Error Details: {e}")
        print("!" * 78)
        input("\nPress Enter to exit...")
        return

    # 3. Setup Machine Trackers
    print("\n[2/3] Initializing Tag Nodes & Advanced Tags...")
    machines = []
    if args.machine in ["1", "both"]:
        machines.append(MachineTracker("MES1", TAG_DEFINITIONS["MES1"], client))
    if args.machine in ["2", "both"]:
        machines.append(MachineTracker("MES2", TAG_DEFINITIONS["MES2"], client))

    ensure_csv_header(args.csv)
    recent_events = []

    print("\n[3/3] Live Monitoring Active (Press Ctrl+C to stop)...")
    time.sleep(1.0)

    try:
        while True:
            t_loop_start = time.perf_counter()
            snapshots = []

            for m in machines:
                snap, evt = m.sample()
                snapshots.append(snap)
                if evt:
                    recent_events.append(evt)
                    if len(recent_events) > 12:
                        recent_events.pop(0)
                    append_csv_event(args.csv, evt)

                    if args.log_only:
                        print(f"\n[TYRE LOGGED] Time: {evt['timestamp']} | Machine: {evt['machine']} | "
                              f"Barcode: {evt['barcode']} | Settled: {evt['settled_weight_kg']:.2f} kg "
                              f"(Peak: {evt['peak_weight_kg']:.2f} kg) | "
                              f"Valid Pulse: {evt['duration_sec']:.1f}s ({evt['samples']} samples)")

            if not args.log_only:
                clear_screen()
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-4]
                print("=" * 80)
                print(f" PROMETEON TYRE GROUP - MESNAC WEIGHT OPC UA MONITOR  [{now_str}]")
                print(f" Server: {args.server} | Scan: {args.rate}ms | CSV: {args.csv}")
                print("=" * 80)

                for snap in snapshots:
                    mch = snap["machine"]
                    
                    if snap["valid_state"]:
                        status_box = "🟢 WEIGHING VALID: 1 (RECORDING SETTLED WEIGHT)"
                    elif snap["trigger"]:
                        status_box = "🟡 PLC TRIGGER: 1 (Scale settling / arm moving)"
                    else:
                        status_box = "⚪ SYSTEM IDLE: 0"

                    adv_source = "Kepware Derived Tag" if snap["adv_tag_online"] else "Software Logic"
                    cycle_status = ""
                    if snap["is_in_cycle"]:
                        cycle_status = f" | 🔥 Peak: {snap['cycle_peak_kg']:.2f} kg ({snap['cycle_samples']} spls)"

                    print(f"\n  [{mch}] PLC IP: {snap['plc_ip']}  |  {status_box}{cycle_status}")
                    print(f"  Barcode Scanned : {snap['barcode']}")
                    print("  " + "-" * 76)
                    print(f"  {'Signal / Tag Name':<38} | {'Raw Value':<14} | {'Status / Interpretation':<22}")
                    print("  " + "-" * 76)

                    # 1. Live Instantaneous Scale
                    act_kg_str = f"{snap['actual_kg']:7.2f} kg" if snap['actual_kg'] is not None else "N/A"
                    print(f"  {'Aux_ActualWeight_Online (Live Scale)':<38} | {str(snap['actual_raw']):<14} | {act_kg_str:<22}")

                    # 2. PLC Handshake Pulse
                    trig_str = "🟢 TRUE (Cycle Active)" if snap['trigger'] else "⚪ FALSE (Idle)"
                    print(f"  {'C_MESRecord (PLC Trigger)':<38} | {str(snap['trigger']):<14} | {trig_str:<22}")

                    # 3. Load Cell Stability
                    st_str = "🟢 TRUE (Settled)" if snap['stable'] else "⚪ FALSE (Moving/Empty)"
                    print(f"  {'F_WeightStableOnline (Scale Settled)':<38} | {str(snap['stable']):<14} | {st_str:<22}")

                    # 4. ⭐ Advanced Tag
                    valid_str = "🟢 TRUE (1)" if snap['valid_state'] else "⚪ FALSE (0)"
                    print(f"  {'Weighing_Valid (C_MESRecord AND Stable)':<38} | {valid_str:<14} | {adv_source:<22}")

                print("\n" + "=" * 80)
                print(" 📋 IN-TERMINAL LOGGER: COMPLETED SETTLED TYRES (Triggered on Weighing_Valid)")
                print("=" * 80)
                if not recent_events:
                    print("  [Waiting for next tyre... Event captures when Weighing_Valid: 1 -> 0]")
                else:
                    print(f"  {'TIME':<12} | {'MCH':<4} | {'BARCODE':<11} | {'SETTLED WEIGHT':<15} | {'PEAK WEIGHT':<12} | {'PULSE':<6}")
                    print("  " + "-" * 76)
                    for e in recent_events[-6:]:
                        print(f"  {e['timestamp'][-12:-3]:<12} | {e['machine']:<4} | {e['barcode']:<11} | "
                              f"{e['settled_weight_kg']:6.2f} kg       | {e['peak_weight_kg']:6.2f} kg   | {e['duration_sec']:3.1f}s")

                print("=" * 80)
                print("  [Scanning every 100ms | Press Ctrl+C to Stop & Close]")

            # Precise timing control for 100ms
            elapsed = time.perf_counter() - t_loop_start
            sleep_time = max(0.005, scan_interval_sec - elapsed)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n\n[STOPPED] Monitoring stopped by user.")
    except Exception as e:
        print(f"\n[UNEXPECTED ERROR] {e}")
    finally:
        client.disconnect()
        print("Disconnected cleanly from Kepware OPC UA server.")
        print(f"Logged events saved to: {os.path.abspath(args.csv)}")
        input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()

