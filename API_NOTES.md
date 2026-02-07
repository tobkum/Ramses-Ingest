# Ramses API Integration Notes

This document provides technical details on how Ramses-Ingest interacts with the Ramses API and the design decisions made for performance and stability.

## Communication Protocol

The Ramses API (located in `lib/ramses/`) communicates with the **Ramses Client** via a local TCP socket (default port 5555). 

- **Singleton Pattern**: The `RamDaemonInterface` is a singleton that manages the socket connection.
- **JSON-over-TCP**: All queries and replies are sent as JSON strings.

## Optimizations

### 1. Batch Optimized Metadata Caching
The `IngestEngine` and `Publisher` have been refactored for "Tier 1" performance. Instead of per-item API lookups, the tool now:
1.  **Pre-fetches** all sequence and shot objects once per batch execution.
2.  Passes these **Caches** into the thread pool.
3.  Performs database registration and status updates using local cache lookups.

This reduces socket overhead and avoids the $O(N 	imes M)$ bottleneck during the registration phase.

### 2. Parallel Media Probing
Media metadata extraction (Timecode, Resolution, FPS) via `ffprobe` is parallelized using a `ThreadPoolExecutor`. 
- **Scanning Performance**: The directory scanner uses `os.scandir` (recursive) for high-speed file discovery.
- **Concurrent Probing**: Multiple `ffprobe` instances are launched simultaneously, saturating CPU cores to minimize the "Probing..." wait time during delivery loads.

## Known Limitations & Considerations

### Socket Buffer Size
The vendored Ramses API uses a fixed buffer size of **65536 bytes** (64KB) for receiving data. 
- **Risk**: Projects with a very large number of sequences or shots (e.g., >1000) might return a JSON response exceeding this limit, causing `json.loads` to fail due to truncation.
- **Future Mitigation**: The API should be updated to read from the socket in a loop until the full message is received (e.g., using a delimiter or content-length header). *Note: Per current project constraints, the API files themselves are not modified.*

### Error Handling
The API calls are often "non-fatal". If the Ramses Daemon is offline or returns an error, the ingestion process continues by falling back to local path resolution. This ensures that files are still organized on disk even if the database registration fails.

### Data Fetching Cache
`RamDaemonInterface.getData` has a hardcoded **2-second cache**. 
- Repeated calls to the same object property within 2 seconds will return cached data.
- During long-running ingestions, if external changes occur in Ramses, the tool might see stale data for up to 2 seconds.

## Recommendations for Future Development
- **Parallel Probing**: Media probing via `ffprobe` is currently sequential. For large deliveries, this can be parallelized.
- **Direct UUID Lookups**: Instead of fetching all objects of a type, the API could be extended to support direct lookups by `shortName` if supported by the Ramses Daemon.

## Editorial & Performance

### 1. Timecode Support
The `Prober` now extracts the `start_timecode` from media metadata using `ffprobe`. This is stored in the `_ramses_data.json` sidecar for each version, allowing for downstream conformance with editorial timelines.

### 2. Parallel Ingest
The `Publisher` utilizes a `ThreadPoolExecutor` for file copying operations. This provides a significant speedup when ingesting large image sequences (EXR/DPX) by allowing multiple I/O operations to occur simultaneously, which is critical for saturating high-speed network storage (NAS/SAN).
