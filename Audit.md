# Ramses-Ingest Application Audit Report - Remaining Items

This report highlights the audit points that still need to be addressed in the application.

---

### **1. Architectural & Logic Shortcomings (Remaining)**

*   **Broad Exception Handling (Throughout `app.py`):** Many critical functions (`app.connect_ramses`, `publisher.execute` loops) still use broad `except Exception:` blocks without specific logging or handling.
*   **Hardcoded Configuration Values (Remaining):**
    *   **Project Standards:** (`app.py`) Defaults to 24fps, 1920x1080 on connection failure, risking incorrect processing.
*   **Stale Data Cache (`app.py`):** The `IngestEngine` fetches all project data from Ramses once upon connection. There is no mechanism to refresh this data (beyond manual UI refresh), meaning any changes made in Ramses during the session will not be recognized by the tool's engine.
*   **Inconsistent Path Handling in `load_delivery` (`app.py`):** The logic for consolidating file and directory paths can still be inefficient or problematic when mixing file and directory inputs.
*   **Disk Space Guardrail Estimation (`app.py`):** The "Disk Space Guard" uses rough, arbitrary estimates for required space, potentially blocking valid ingests or allowing ones that will fail.
*   **Sub-optimal Threading (`app.py`):** Using `os.cpu_count()` for I/O-bound work like file copying is not optimal and could be tuned for better performance.

---

### **2. UI/UX & Performance Issues (Remaining)**

*   **Confusing Override Workflow (`gui.py`):** While responsiveness is improved, the UI still presents two ways to edit a Shot ID (inline in the table and in the right-hand details panel), which can be confusing. The interaction flow for these should be clarified.
*   **Faulty Filter/Search Logic (`gui.py`):** The search function does not work on items that are currently hidden by status or type filters. A user must clear all filters to effectively search the entire batch.
*   **Complex Signal/Slot Management (`gui.py`):** While some aspects were improved by in-place table updates and debouncing, the underlying complexity of managing signals to prevent unintended interactions or infinite loops may still exist for other GUI components.

---

### **3. Minor Issues & Code Quality Notes (Remaining)**

*   **Silent `PermissionError` (`scanner.py`):** When scanning directories, `PermissionError` is caught and printed to `stdout`, but a proper GUI warning or log entry would be more appropriate for a GUI application.
*   **Cache is Unbounded and Persists Forever (`prober.py`):** The LRU pruning for the metadata cache only occurs when `flush_cache()` is called (at the end of an ingest). This means the in-memory cache can grow indefinitely during a long session, consuming excessive memory.
*   **Broad Exception Handling in Caching (`prober.py`):** `_load_cache()` still uses a broad `except Exception:` block to silently handle cache loading errors without specific logging.
*   **Fragile "Zombie Prevention" in Versioning (`publisher.py`):** While improved, the time-based heuristic for in-progress ingests still carries some inherent fragility.
